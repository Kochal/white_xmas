"""GHCN-Daily access: bulk metadata, cached per-station files, and a compact station record.

Only what the station check needs is read from a station file (``by_station/<ID>.csv.gz``,
columns ID, DATE, ELEMENT, VALUE, MFLAG, QFLAG, SFLAG, OBS-TIME):

- snow depth (SNWD, mm) on 24, 25 and 26 December of every year;
- per December, the days with a valid SNWD value and the days with a valid "core" observation
  (PRCP, TMAX, TMIN or TAVG), to test whether snow depth was reported every day the station
  reported anything else (stations that report snow depth only when snow lies leave the snow-free
  days blank);
- the number of December SNWD values and of those equal to 0, the days with SNWD > 0 and the
  December snowfall total (SNOW, mm) per year, to catch records that fill snow depth with zeros;
- monthly mean temperature in December, January and July (from TMAX/TMIN, else TAVG), for a
  simple climate class.

Values with a quality flag (QFLAG not blank) are dropped everywhere.
"""

from __future__ import annotations

import gzip
import logging
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

GHCN = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/"
USER_AGENT = "whitexmas-pipeline/0.2 (+https://github.com/Kochal/white_xmas)"
CORE = frozenset({"PRCP", "TMAX", "TMIN", "TAVG"})
MAX_CONCURRENCY = 4  # be polite to NCEI


@dataclass
class StationMeta:
    id: str
    name: str
    lat: float
    lon: float
    elev: float  # m; -999.9 in the file means unknown -> nan
    state: str = ""

    @property
    def country(self) -> str:
        return self.id[:2]


def read_stations(path: Path) -> dict[str, StationMeta]:
    """``ghcnd-stations.txt`` (fixed width) -> {id: StationMeta}."""
    out = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if len(line) < 41:
                continue
            elev = float(line[31:37])
            out[line[:11]] = StationMeta(
                id=line[:11],
                lat=float(line[12:20]),
                lon=float(line[21:30]),
                elev=float("nan") if elev < -998 else elev,
                state=line[38:40].strip(),
                name=line[41:71].strip(),
            )
    return out


def read_inventory(path: Path, element: str = "SNWD") -> dict[str, tuple[int, int]]:
    """``ghcnd-inventory.txt`` -> {id: (first year, last year)} for one element."""
    out = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line[31:35] == element:
                out[line[:11]] = (int(line[36:40]), int(line[41:45]))
    return out


def read_countries(path: Path) -> dict[str, str]:
    with open(path, encoding="utf-8", errors="replace") as f:
        return {line[:2]: line[3:].strip() for line in f if len(line) > 3}


def get(url: str, target: Path, retries: int = 4) -> Path | None:
    """Download ``url`` to ``target`` once (cached; atomic). None if the server has no such file."""
    if target.exists() and target.stat().st_size > 0:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = r.read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                log.warning("not on the server: %s", url)
                return None
            err = e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            err = e
        time.sleep(5 * (attempt + 1))
    else:
        raise RuntimeError(f"download failed after {retries} attempts: {url}: {err}")
    tmp = target.with_suffix(target.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(target)
    return target


def metadata(ghcn_dir: Path) -> tuple[Path, Path, Path]:
    """The three bulk metadata files, downloaded once into ``ghcn_dir``."""
    names = ("ghcnd-stations.txt", "ghcnd-inventory.txt", "ghcnd-countries.txt")
    return tuple(get(GHCN + n, ghcn_dir / n) for n in names)  # type: ignore[return-value]


def station_path(ghcn_dir: Path, sid: str) -> Path:
    return ghcn_dir / f"{sid}.csv.gz"


def fetch_stations(ids: list[str], ghcn_dir: Path, concurrency: int = MAX_CONCURRENCY) -> int:
    """Download the per-station files not yet cached; returns how many were downloaded."""
    todo = [s for s in ids if not station_path(ghcn_dir, s).exists()]
    if not todo:
        return 0
    log.info("downloading %d GHCN-Daily station files (%d cached)", len(todo), len(ids) - len(todo))
    n = min(max(1, int(concurrency)), MAX_CONCURRENCY)
    done = 0
    with ThreadPoolExecutor(n) as ex:
        for k, _ in enumerate(
            ex.map(lambda s: get(f"{GHCN}by_station/{s}.csv.gz", station_path(ghcn_dir, s)), todo)
        ):
            done += 1
            if (k + 1) % 250 == 0:
                log.info("  %d / %d", k + 1, len(todo))
    return done


@dataclass
class StationRecord:
    """What the station check needs from one GHCN-Daily file (SNWD in mm, temperatures in °C)."""

    snwd: dict[int, dict[int, int]] = field(default_factory=dict)  # year -> {24|25|26: mm}
    dec_snwd_days: dict[int, int] = field(default_factory=dict)  # year -> days with SNWD
    dec_core_days: dict[int, int] = field(default_factory=dict)  # year -> days with PRCP/T
    dec_both_days: dict[int, int] = field(default_factory=dict)  # year -> days with both
    dec_snow_mm: dict[int, int] = field(default_factory=dict)  # year -> December snowfall
    dec_snwd_pos: dict[int, int] = field(default_factory=dict)  # year -> days with SNWD > 0
    dec_snwd_n: int = 0
    dec_snwd_zero: int = 0
    qflag_dropped: int = 0
    tmean: dict[int, float] = field(default_factory=dict)  # month -> mean °C (12, 1, 7)

    def snowfall_without_depth(self, year: int, min_snow_mm: int = 200) -> bool | None:
        """≥ ``min_snow_mm`` December snowfall but no December day with snow depth > 0.

        None when the year has too little snowfall (or no SNWD) to tell.
        """
        if self.dec_snow_mm.get(year, 0) < min_snow_mm or not self.dec_snwd_days.get(year):
            return None
        return self.dec_snwd_pos.get(year, 0) == 0

    def dec_completeness(self, year: int) -> float:
        """Share of the December days with a core observation that also have SNWD (nan if none)."""
        core = self.dec_core_days.get(year, 0)
        return self.dec_both_days.get(year, 0) / core if core else float("nan")

    @property
    def dec_zero_share(self) -> float:
        return self.dec_snwd_zero / self.dec_snwd_n if self.dec_snwd_n else float("nan")


PARSER_VERSION = 2


def read_station_cached(path: Path, first: int = 1950, last: int = 2025) -> StationRecord:
    """:func:`read_station`, memoised in ``<dir>/parsed/`` (keyed by file size, mtime, period)."""
    import pickle

    st = path.stat()
    key = f"{PARSER_VERSION}-{first}-{last}-{st.st_size}-{int(st.st_mtime)}"
    cache = path.parent / "parsed" / (path.name.split(".")[0] + ".pkl")
    if cache.exists():
        try:
            with open(cache, "rb") as f:
                k, rec = pickle.load(f)
            if k == key:
                return rec
        except Exception:  # unreadable cache: parse again
            pass
    rec = read_station(path, first, last)
    cache.parent.mkdir(exist_ok=True)
    tmp = cache.with_suffix(".part")
    with open(tmp, "wb") as f:
        pickle.dump((key, rec), f)
    tmp.replace(cache)
    return rec


def read_station(path: Path, first: int = 1950, last: int = 2025) -> StationRecord:
    """Parse a ``by_station`` CSV (gzip) into a :class:`StationRecord` for ``first..last``."""
    rec = StationRecord()
    snwd_days: dict[int, set[int]] = defaultdict(set)
    core_days: dict[int, set[int]] = defaultdict(set)
    tx: dict[tuple[int, int, int], float] = {}
    tn: dict[tuple[int, int, int], float] = {}
    ta: dict[tuple[int, int, int], float] = {}
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            # DATE is the second field (YYYYMMDD) right after the 11-character ID.
            mm = line[16:18]
            if mm not in ("12", "01", "07"):
                continue
            p = line.rstrip("\n").split(",")
            if len(p) < 6:
                continue
            el = p[2]
            if el != "SNWD" and el != "SNOW" and el not in CORE:
                continue
            date = p[1]
            year = int(date[:4])
            if not first <= year <= last:
                continue
            if p[5] != "":
                if el == "SNWD":
                    rec.qflag_dropped += 1
                continue
            try:
                v = int(p[3])
            except ValueError:
                continue
            day = int(date[6:8])
            if el == "SNOW":
                if mm == "12" and v >= 0:
                    rec.dec_snow_mm[year] = rec.dec_snow_mm.get(year, 0) + v
                continue
            if el == "SNWD":
                if mm != "12" or v < 0:
                    continue
                snwd_days[year].add(day)
                rec.dec_snwd_n += 1
                rec.dec_snwd_zero += v == 0
                if v > 0:
                    rec.dec_snwd_pos[year] = rec.dec_snwd_pos.get(year, 0) + 1
                if 24 <= day <= 26:
                    rec.snwd.setdefault(year, {})[day] = v
                continue
            if mm == "12":
                core_days[year].add(day)
            if el in ("TMAX", "TMIN", "TAVG"):
                key = (year, int(mm), day)
                {"TMAX": tx, "TMIN": tn, "TAVG": ta}[el][key] = v / 10.0
    for y in set(snwd_days) | set(core_days):
        rec.dec_snwd_days[y] = len(snwd_days.get(y, ()))
        rec.dec_core_days[y] = len(core_days.get(y, ()))
        rec.dec_both_days[y] = len(snwd_days.get(y, set()) & core_days.get(y, set()))
    sums: dict[int, list[float]] = defaultdict(list)
    for k in set(tx) | set(ta):
        if k in tx and k in tn:
            sums[k[1]].append((tx[k] + tn[k]) / 2)
        elif k in ta:
            sums[k[1]].append(ta[k])
    for m, vals in sums.items():
        if len(vals) >= 150:  # about five months of data
            rec.tmean[m] = sum(vals) / len(vals)
    return rec
