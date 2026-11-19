"""places.json: GeoNames cities15000 with precomputed values for the default definition."""

from __future__ import annotations

import csv
import io
import json
import logging
import unicodedata
import zipfile
from collections.abc import Iterable
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

# GeoNames "isolanguage" values that are codes, not languages
NOT_LANGUAGES = {"", "link", "wkdt", "post", "iata", "icao", "faac", "abbr", "unlc", "fr_1793"}
EXTRA_LANGS = ["en", "de", "fr", "es"]
MAX_ALT = 5
MAX_ALT_CHARS = 80
SEARCH_RADIUS = 2  # cells

# Administrative words that turn a place name into the name of a municipality or district
# ("Municipio Naucalpan de Juárez", "Municipalité de Bălţi", "Stadt Zürich", "City of London").
ADMIN_WORDS = (
    "municipio", "municipalidad", "municipalité", "municipality", "municipiul", "municipiu",
    "município", "comune", "comuna", "commune", "gemeinde", "stadt", "landkreis", "kreis",
    "city of", "town of", "borough of", "county", "district", "prefecture", "province",
    "provincia", "département", "departamento", "distrito", "okrug", "rayon", "raion",
    "oblast", "gmina", "obshtina", "kommune", "kommun", "kunta", "shi",
)  # fmt: skip


def cell_index(lat: float, lon: float, res: float = 0.1, nx: int = 3600) -> tuple[int, int]:
    """Contract: i = round((lon + 180) / 0.1) mod 3600, j = round((90 - lat) / 0.1)."""
    return int(round((90.0 - lat) / res)), int(round((lon + 180.0) / res)) % nx


def nearest_valid(valid: np.ndarray, j: int, i: int, radius: int = SEARCH_RADIUS):
    """The cell itself if valid, else the nearest valid cell within ``radius`` cells."""
    ny, nx = valid.shape
    if 0 <= j < ny and valid[j, i]:
        return j, i
    best, best_d = None, None
    for dj in range(-radius, radius + 1):
        for di in range(-radius, radius + 1):
            jj, ii = j + dj, (i + di) % nx
            if not (0 <= jj < ny) or not valid[jj, ii]:
                continue
            d = dj * dj + di * di
            if d <= radius * radius and (best_d is None or d < best_d):
                best, best_d = (jj, ii), d
    return best


def read_cities(zip_path: Path) -> list[dict]:
    rows = []
    with zipfile.ZipFile(zip_path) as z, z.open("cities15000.txt") as f:
        text = io.TextIOWrapper(f, "utf-8")
        for r in csv.reader(text, delimiter="\t", quoting=csv.QUOTE_NONE):
            rows.append(
                {
                    "id": int(r[0]),
                    "name": r[1],
                    "ascii": r[2],
                    "lat": float(r[4]),
                    "lon": float(r[5]),
                    "country": r[8],
                    "admin1_code": r[10],
                    "pop": int(r[14] or 0),
                }
            )
    return rows


def read_admin1(path: Path) -> dict[str, str]:
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2:
                out[parts[0]] = parts[1]
    return out


def read_country_languages(path: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            p = line.rstrip("\n").split("\t")
            if len(p) > 15:
                langs: list[str] = []
                for code in p[15].split(","):
                    code = code.strip().split("-")[0]
                    if code and code not in langs:
                        langs.append(code)
                out[p[0]] = langs
    return out


def read_alternate_names(zip_path: Path, ids: set[int]) -> dict[int, list[tuple]]:
    """{geonameid: [(lang, name, preferred, short)]}; colloquial and historic names dropped."""
    out: dict[int, list[tuple]] = {}
    with zipfile.ZipFile(zip_path) as z, z.open("alternateNamesV2.txt") as f:
        for raw in io.TextIOWrapper(f, "utf-8"):
            p = raw.rstrip("\n").split("\t")
            if len(p) < 8:
                continue
            gid = int(p[1])
            if gid not in ids or p[2] in NOT_LANGUAGES:
                continue
            if p[6] == "1" or p[7] == "1":
                continue
            out.setdefault(gid, []).append((p[2], p[3], p[4] == "1", p[5] == "1"))
    return out


def is_admin_name(alt: str, name: str, ascii_name: str = "") -> bool:
    """True for administrative-unit names: they start with an administrative word, or contain
    the place name together with one ("Stadt Zürich", "Zürich District", "Sapporo-shi")."""
    a = unicodedata.normalize("NFC", alt).casefold()
    words = [w.strip() for w in ADMIN_WORDS]
    if any(a.startswith(w + " ") or a.startswith(w + "-") for w in words if w):
        return True
    bases = {unicodedata.normalize("NFC", x).casefold() for x in (name, ascii_name) if x}
    if any(b and b in a and a != b for b in bases):
        rest = a
        for b in bases:
            rest = rest.replace(b, " ")
        for ch in "-,()[]/":
            rest = rest.replace(ch, " ")
        tokens = rest.split()
        joined = " ".join(tokens)
        return any(w in tokens or (" " in w and w in joined) for w in words)
    return False


def pick_alt(name: str, ascii_name: str, langs: list[str], alts: Iterable[tuple]) -> str:
    """Up to 5 alternate names (main official language, en/de/fr/es, other official ones).

    One name per language (the preferred one if flagged), skipping duplicates of the name.
    """

    def key(x: str) -> str:
        return unicodedata.normalize("NFC", x).casefold()

    by_lang: dict[str, list[tuple]] = {}
    for lang, n, pref, short in alts:
        n = unicodedata.normalize("NFC", n.strip())
        by_lang.setdefault(lang, []).append((not pref, short, n))
    seen = {key(name), key(ascii_name)}
    chosen: list[str] = []
    # main official language, then the common exonyms, then other official languages
    order: list[str] = []
    for lang in [*langs[:1], *EXTRA_LANGS, *langs[1:]]:
        if lang not in order:
            order.append(lang)
    for lang in order:
        if len(chosen) >= MAX_ALT:
            break
        for _, _, n in sorted(by_lang.get(lang, [])):
            if not n or key(n) in seen or "|" in n or is_admin_name(n, name, ascii_name):
                continue
            if len("|".join([*chosen, n])) > MAX_ALT_CHARS:
                continue
            chosen.append(n)
            seen.add(key(n))
            break
    return "|".join(chosen)


def _r1(v) -> float | None:
    return None if not np.isfinite(v) else round(float(v), 1)


def build_places(
    ext_dir: Path,
    p_full: np.ndarray,
    p_then: np.ndarray,
    p_now: np.ndarray,
    trend: np.ndarray,
    trend_p: np.ndarray,
    windows: dict[str, str],
    definition: str,
    trend_alpha: float = 0.1,
    with_alt: bool = True,
    extras: list[tuple[str, str, np.ndarray, np.ndarray]] | None = None,
) -> dict:
    """``extras``: (then field, now field, p_then, p_now) for other thresholds (contract v1.5,
    e.g. ``p_then_raw``/``p_now_raw``), appended after ``trend`` from the same cell."""
    extras = extras or []
    cities = read_cities(ext_dir / "cities15000.zip")
    admin1 = read_admin1(ext_dir / "admin1CodesASCII.txt")
    langs = read_country_languages(ext_dir / "countryInfo.txt")
    alt_src = ext_dir / "alternateNamesV2.zip"
    alts: dict[int, list[tuple]] = {}
    if with_alt and alt_src.exists():
        alts = read_alternate_names(alt_src, {c["id"] for c in cities})
    valid = np.isfinite(p_full)

    rows, dropped = [], 0
    for c in sorted(cities, key=lambda c: -c["pop"]):
        j, i = cell_index(c["lat"], c["lon"])
        cell = nearest_valid(valid, j, i)
        if cell is None:
            dropped += 1
            continue
        sig = bool(np.isfinite(trend_p[cell]) and trend_p[cell] < trend_alpha)
        row: list = [
            c["name"],
            c["ascii"],
            c["country"],
            admin1.get(f"{c['country']}.{c['admin1_code']}", ""),
        ]
        if with_alt:
            country_langs = langs.get(c["country"], [])
            row.append(pick_alt(c["name"], c["ascii"], country_langs, alts.get(c["id"], [])))
        row += [
            round(c["lat"], 4),
            round(c["lon"], 4),
            c["pop"],
            _r1(p_full[cell]),
            _r1(p_then[cell]),
            _r1(p_now[cell]),
            _r1(trend[cell]) if sig else None,
        ]
        for _, _, e_then, e_now in extras:
            row += [_r1(e_then[cell]), _r1(e_now[cell])]
        rows.append(row)
    log.info("places: %d kept, %d dropped (no land cell within 2 cells)", len(rows), dropped)
    fields = ["name", "ascii", "country", "admin1"]
    if with_alt:
        fields.append("alt")
    fields += ["lat", "lon", "pop", "p_full", "p_then", "p_now", "trend"]
    for f_then, f_now, _, _ in extras:
        fields += [f_then, f_now]
    return {
        "fields": fields,
        "definition": definition,
        "windows": windows,
        "attribution": "Places: GeoNames (geonames.org), CC BY 4.0",
        "rows": rows,
    }


def write_json(path: Path, obj) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    path.write_text(data, encoding="utf-8")
    return path.stat().st_size
