"""States and provinces from Natural Earth 10m admin-1 (public domain).

Rules (docs/admin1.md):

- One region per admin-1 feature, except for the countries listed under ``admin1.dissolve`` in
  the config, which Natural Earth splits below their first level (Italian provinces, French
  départements, Spanish provinces, UK local authorities, Slovenian municipalities): their
  features are dissolved by a column of the source (region, geonunit).
- Region id: ISO 3166-2 when Natural Earth's code is well formed (``CC-XXX``) and unique, else
  Natural Earth's ``adm1_code`` with anything but letters, digits and ``-`` removed. Dissolved
  groups take their id from the config (or a source column), else ``<ADM0>-<SLUG>``.
- Country: the same key as ``regions.json`` (ISO 3166-1 alpha-3, see ``export/regions.py``).
- Admin-0 units with no admin-1 feature (reefs, Bir Tawil, the Cyprus buffer zone, the
  Brazilian Island, the Southern Patagonian Ice Field) become one region each, id = Natural
  Earth's ``ADM0_A3``, source ``ne_admin0`` (flagged ``admin0`` in the export).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path

log = logging.getLogger(__name__)

NE_ADMIN1_ZIP = "ne_10m_admin_1_states_provinces.zip"
NE_ADMIN1_SHP = "ne_10m_admin_1_states_provinces.shp"
ISO_RE = re.compile(r"^[A-Z]{2}-[A-Z0-9]{1,3}$")
ADMIN1_COLUMNS = [
    "adm1_code", "iso_3166_2", "name", "name_en", "type_en", "adm0_a3", "admin",
    "region", "region_cod", "geonunit",
]  # fmt: skip


def _clean(v) -> str:
    """Natural Earth strings: None/NaN to '', stray whitespace (``"FR-IDF\\t"``) stripped."""
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none") else s


def slug(s: str) -> str:
    a = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", "-", a.upper()).strip("-")


def safe_id(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9-]", "", s)


def read_admin1_features(zip_path: Path) -> list[dict]:
    import pyogrio
    import shapely

    src = f"/vsizip/{Path(zip_path).as_posix()}/{NE_ADMIN1_SHP}"
    meta, _, geoms, fields = pyogrio.raw.read(src, columns=ADMIN1_COLUMNS, encoding="utf-8")
    cols = dict(zip(meta["fields"], fields, strict=True))
    out = []
    for k, wkb in enumerate(geoms):
        rec = {c: _clean(cols[c][k]) for c in ADMIN1_COLUMNS}
        rec["geom"] = shapely.from_wkb(wkb) if wkb is not None else None
        out.append(rec)
    return out


def country_keys(countries: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    """``(adm0_a3 → key, key → name)`` from the admin-0 table of ``export/regions.py``."""
    to_key, names = {}, {}
    for c in countries:
        to_key[c["adm0_a3"]] = c["iso_a3"]
        names.setdefault(c["iso_a3"], c["name"])
    return to_key, names


def build_regions(admin1: list[dict], countries: list[dict], dissolve: dict) -> list[dict]:
    """Region records: ``id, name, name_local, type, country, country_name, adm0_a3, source,
    n_features, geom``, sorted by country and id."""
    import shapely

    to_key, cnames = country_keys(countries)
    # a well-formed ISO code is used only if no other feature carries it
    iso_count: dict[str, int] = {}
    for f in admin1:
        iso_count[f["iso_3166_2"]] = iso_count.get(f["iso_3166_2"], 0) + 1

    regions: list[dict] = []
    groups: dict[tuple[str, str], list[dict]] = {}
    for f in admin1:
        if f["geom"] is None or f["geom"].is_empty:
            continue
        a3 = f["adm0_a3"]
        key = to_key.get(a3, a3)
        rule = dissolve.get(a3)
        if rule:
            g = f[rule["by"]] or f["name"] or f["adm1_code"]
            groups.setdefault((a3, g), []).append(f)
            continue
        iso = f["iso_3166_2"]
        rid = iso if ISO_RE.match(iso) and iso_count[iso] == 1 else safe_id(f["adm1_code"])
        name = f["name_en"] or f["name"] or cnames.get(key, key)
        local = f["name"] if f["name"] and f["name"] != name else ""
        regions.append({
            "id": rid, "name": name, "name_local": local, "type": f["type_en"],
            "country": key, "country_name": cnames.get(key, f["admin"]), "adm0_a3": a3,
            "source": "ne_admin1", "n_features": 1, "geom": f["geom"],
        })  # fmt: skip

    for (a3, g), feats in groups.items():
        rule = dissolve[a3]
        key = to_key.get(a3, a3)
        ids = rule.get("ids") or {}
        names = rule.get("names") or {}
        if g in ids:
            rid = ids[g]
        elif rule.get("id_from") and feats[0][rule["id_from"]]:
            rid = safe_id(feats[0][rule["id_from"]])
        else:
            rid = f"{a3}-{slug(g)}"
        name = names.get(g, g)
        regions.append({
            "id": rid, "name": name, "name_local": g if g != name else "",
            "type": "Region", "country": key, "country_name": cnames.get(key, key),
            "adm0_a3": a3, "source": "ne_admin1_dissolved", "n_features": len(feats),
            "geom": shapely.make_valid(shapely.union_all([f["geom"] for f in feats])),
        })  # fmt: skip

    have = {r["adm0_a3"] for r in regions}
    for c in countries:
        if c["adm0_a3"] in have or c["geom"] is None:
            continue
        regions.append({
            "id": safe_id(c["adm0_a3"]), "name": c["name"], "name_local": "", "type": "Country",
            "country": c["iso_a3"], "country_name": cnames.get(c["iso_a3"], c["name"]),
            "adm0_a3": c["adm0_a3"], "source": "ne_admin0", "n_features": 1, "geom": c["geom"],
        })  # fmt: skip

    # ids must be unique; a clash (none in Natural Earth 5.1) gets a numeric suffix
    seen: dict[str, int] = {}
    for r in sorted(regions, key=lambda r: (r["country"], r["id"])):
        n = seen.get(r["id"], 0)
        seen[r["id"]] = n + 1
        if n:
            log.warning("admin1: duplicate id %s; renamed %s-%d", r["id"], r["id"], n + 1)
            r["id"] = f"{r['id']}-{n + 1}"
    regions.sort(key=lambda r: (r["country"], r["id"]))
    log.info(
        "admin1: %d regions in %d countries (%d dissolved groups, %d whole countries)",
        len(regions), len({r["country"] for r in regions}), len(groups),
        sum(r["source"] == "ne_admin0" for r in regions),
    )  # fmt: skip
    return regions


def read_countries_with_a3(zip_path: Path) -> list[dict]:
    """Admin-0 features with the regions.json key, name and Natural Earth ``ADM0_A3``."""
    import pyogrio
    import shapely

    src = f"/vsizip/{Path(zip_path).as_posix()}/ne_10m_admin_0_countries.shp"
    meta, _, geoms, fields = pyogrio.raw.read(
        src, columns=["ISO_A3", "ISO_A3_EH", "ADM0_A3", "NAME"], encoding="utf-8"
    )
    cols = dict(zip(meta["fields"], fields, strict=True))
    out = []
    for k, wkb in enumerate(geoms):
        iso = _clean(cols["ISO_A3"][k])
        if not iso or iso == "-99":
            iso = _clean(cols["ISO_A3_EH"][k])
        if not iso or iso == "-99":
            iso = _clean(cols["ADM0_A3"][k])
        out.append({
            "iso_a3": iso, "adm0_a3": _clean(cols["ADM0_A3"][k]), "name": _clean(cols["NAME"][k]),
            "geom": shapely.from_wkb(wkb) if wkb is not None else None,
        })  # fmt: skip
    return out


def load_regions(ext_dir: Path, cfg_admin1: dict) -> list[dict]:
    admin1 = read_admin1_features(ext_dir / cfg_admin1.get("source", NE_ADMIN1_ZIP))
    countries = read_countries_with_a3(ext_dir / "ne_10m_admin_0_countries.zip")
    return build_regions(admin1, countries, cfg_admin1.get("dissolve") or {})
