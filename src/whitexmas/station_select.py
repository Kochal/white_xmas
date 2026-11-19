"""Which GHCN-Daily stations the station check uses, and the quality rules applied to each.

Two modes (``stations.mode`` in ``config/pipeline.yaml``):

- ``list``: the hand-picked ``stations.list`` (the D-17 calibration set), kept reproducible.
- ``auto``: a systematic, global selection from NOAA's bulk metadata:

  1. every Northern-Hemisphere station whose inventory lists SNWD with at least ``min_years``
     years inside the configured period (``ghcnd-inventory.txt`` first/last year);
  2. whose ERA5-Land cell (contract rounding, or the nearest land cell within 2 cells) exists;
  3. thinned to the stations in each ``box_deg`` × ``box_deg`` latitude/longitude box, ranked by
     SNWD span inside the period (longest first), then network (first-order/WMO before
     co-operative), then the smallest station-vs-cell elevation difference, then id;
  4. the first-ranked station of each box is downloaded and checked; if it fails a data-quality
     rule (too few usable years, patchy record, snow depth missing on observing days), the next
     one in the box is tried, up to ``max_tries`` per box.

Quality rules, per station and station-year (``evaluate_station``):

- quality-flagged values are dropped (``ghcn.read_station``);
- a station-year is usable when SNWD on 25 December exists, the ERA5-Land value exists, and the
  station's December is *complete*: SNWD was reported on at least ``min_dec_completeness`` of the
  December days on which the station reported precipitation or temperature (a station without
  either element must report SNWD on at least 28 December days). Stations that report snow depth
  only when snow lies (common in SYNOP/GSOD-derived records) leave snow-free days blank, so their
  green Decembers fail this test and their white ones pass: such a station has many incomplete
  years: when more than ``max_incomplete_share`` of its years with a 25 December value have an
  incomplete December, it is excluded ("zeros not reported" when < 2 % of its December values are
  0, else "snow depth missing on observing days"), instead of being counted as "always white";
- coverage: usable years / (last − first + 1) ≥ ``min_coverage``, and usable years ≥ ``min_years``;
- zero-filled snow depth: among usable years with ≥ ``min_snowfall_mm`` of December snowfall
  (the station's own SNOW element), more than ``max_snowfall_without_depth_share`` (and at least
  two) have no December day with snow depth above 0: the record fills snow depth with zeros;
- the station is *separated* (kept in the table, left out of the calibration statistics) when it
  is observed white in ≥ ``always_white_pct`` % of years, when both the station and ERA5-Land at
  1 cm are white in < ``never_white_pct`` % (no information about the threshold), or when the
  station and its cell differ by more than ``max_elev_diff_m`` in elevation;
- flags (kept in the calibration): US whole-inch reporting, coastal (nearest land cell used),
  high mountain (station or cell ≥ ``high_mountain_m``), lake (cell lake cover >
  ``lake_cover``), GSOD-sourced (more than ``gsod_share`` of December snow depths carry GHCN
  source flag S, a source that omits zero depths).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import ghcn

log = logging.getLogger(__name__)

# Network preference inside a box (third character of the GHCN id): first-order and WMO stations
# keep longer, better-documented records than co-operative or volunteer networks.
NETWORK_RANK = {"W": 0, "M": 1, "E": 2, "0": 3, "N": 4, "C": 5, "S": 6, "1": 7}

# --------------------------------------------------------------------------- regions
# Ordered: the first match wins. Boxes are (lat_min, lat_max, lon_min, lon_max); cell_elev is the
# ERA5-Land cell's mean elevation (m), which describes the terrain the cell represents.
AMERICAS = {"US", "CA"}
NORDIC = {"NO", "SW", "FI", "DA", "IC"}
CENTRAL_ASIA = {"KZ", "UZ", "TX", "TI", "KG", "AF"}
ARCTIC = {"GL", "SV", "JN"}


def region_of(lat: float, lon: float, cell_elev: float, country: str) -> str:
    """A named region for grouping (deterministic; documented in docs/methodology.md)."""
    ce = cell_elev if np.isfinite(cell_elev) else 0.0
    if 26 <= lat <= 40 and 73 <= lon <= 105 and ce >= 2500:
        return "Tibetan Plateau"
    if country in ARCTIC or lat >= 72:
        return "Arctic islands"
    if country == "JA":
        return "Japan"
    if country in ("KS", "KN"):
        return "Korea"
    if 43.5 <= lat <= 48.5 and 5 <= lon <= 17 and ce >= 700:
        return "Alps"
    if country in AMERICAS or (lat >= 24 and -170 <= lon <= -50):
        if lat >= 60:
            return "Alaska & northern Canada"
        if lon <= -103 and ce >= 1200:
            return "Rocky Mountains & Intermountain West"
        if lon <= -117:
            return "Pacific North America"
        if lon <= -95:
            return "Great Plains & Prairies"
        return "Eastern North America"
    if country in NORDIC:
        return "Nordic countries"
    if country == "RS":
        return "European Russia" if lon < 60 else "Siberia & Russian Far East"
    if country in CENTRAL_ASIA:
        return "Central Asia"
    if country in ("CH", "MG"):
        return "China & Mongolia"
    if 25 <= lat <= 45 and 26 <= lon <= 63:
        return "Turkey, Caucasus & Middle East"
    if 35 <= lat < 72 and -25 <= lon < 16:
        return "Western & Central Europe"
    if 35 <= lat < 72 and 16 <= lon < 60:
        return "Eastern Europe"
    return "Other (subtropics)"


def climate_class(dec_tmean: float) -> str:
    """December mean temperature at the station (°C), a simple proxy for how marginal snow is."""
    if not np.isfinite(dec_tmean):
        return "unknown"
    if dec_tmean < -10:
        return "< −10 °C"
    if dec_tmean < -5:
        return "−10 to −5 °C"
    if dec_tmean < 0:
        return "−5 to 0 °C"
    if dec_tmean < 3:
        return "0 to 3 °C"
    return "≥ 3 °C"


# --------------------------------------------------------------------------- settings
@dataclass(frozen=True)
class Rules:
    obs_threshold_mm: int = 10
    min_years: int = 15
    min_coverage: float = 0.8
    min_dec_completeness: float = 0.9
    max_incomplete_share: float = 0.2
    min_snowfall_mm: int = 200
    max_snowfall_without_depth_share: float = 0.2
    always_white_pct: float = 95
    always_white_model_cm: int | None = None  # also require ERA5-Land ≥ T white (sensitivity)
    never_white_pct: float = 5
    max_elev_diff_m: float = 200
    high_mountain_m: float = 1500
    lake_cover: float = 0.3
    gsod_share: float = 0.5
    thresholds_cm: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8)

    @classmethod
    def from_config(cls, sc: dict) -> Rules:
        kw = {k: sc[k] for k in cls.__dataclass_fields__ if k in sc}
        if "thresholds_cm" in kw:
            kw["thresholds_cm"] = tuple(int(t) for t in kw["thresholds_cm"])
        return cls(**kw)


@dataclass(frozen=True)
class AutoSettings:
    min_lat: float = 0.0
    box_deg: float = 1.0
    max_tries: int = 6
    concurrency: int = 4
    pin: str | None = None  # a stations.json whose examined ids limit the candidates

    @classmethod
    def from_config(cls, sc: dict) -> AutoSettings:
        a = sc.get("auto") or {}
        return cls(**{k: a[k] for k in cls.__dataclass_fields__ if k in a})


# --------------------------------------------------------------------------- candidates
def span_in(first_last: tuple[int, int], first: int, last: int) -> int:
    a, b = max(first_last[0], first), min(first_last[1], last)
    return max(0, b - a + 1)


def box_key(lat: float, lon: float, box_deg: float) -> tuple[int, int]:
    return math.floor(lat / box_deg), math.floor(lon / box_deg)


def rank_key(meta: ghcn.StationMeta, span: int, elev_diff: float) -> tuple:
    dz = abs(elev_diff) if np.isfinite(elev_diff) else 1e9
    return (-span, NETWORK_RANK.get(meta.id[2], 9), dz, meta.id)


def candidate_boxes(
    stations: dict[str, ghcn.StationMeta],
    inventory: dict[str, tuple[int, int]],
    first: int,
    last: int,
    rules: Rules,
    auto: AutoSettings,
    cell_of=None,
) -> dict[tuple[int, int], list[str]]:
    """{box: [station ids, best first]} for the auto mode (steps 1-3 of the module doc).

    ``cell_of(meta) -> (cell, cell_elev_m) | None`` maps a station to its ERA5-Land land cell;
    stations without one are dropped. Without ``cell_of`` every station is kept (tests).
    """
    boxes: dict[tuple[int, int], list[tuple[tuple, str]]] = {}
    for sid, fl in inventory.items():
        m = stations.get(sid)
        if m is None or m.lat <= auto.min_lat:
            continue
        span = span_in(fl, first, last)
        if span < rules.min_years:
            continue
        dz = float("nan")
        if cell_of is not None:
            c = cell_of(m)
            if c is None:
                continue
            dz = c[1] - m.elev
        boxes.setdefault(box_key(m.lat, m.lon, auto.box_deg), []).append(
            (rank_key(m, span, dz), sid)
        )
    return {b: [sid for _, sid in sorted(v)] for b, v in sorted(boxes.items())}


# --------------------------------------------------------------------------- evaluation
def usable_years(
    rec: ghcn.StationRecord, model_ok: dict[int, bool], rules: Rules
) -> tuple[list[int], list[int]]:
    """(usable years, years with a 25 December value whose December was incomplete)."""
    used, incomplete = [], []
    for y in sorted(rec.snwd):
        if 25 not in rec.snwd[y] or not model_ok.get(y, False):
            continue
        comp = rec.dec_completeness(y)
        ok = (
            comp >= rules.min_dec_completeness
            if np.isfinite(comp)
            else rec.dec_snwd_days.get(y, 0) >= 28
        )
        (used if ok else incomplete).append(y)
    return used, incomplete


def evaluate_station(
    meta: ghcn.StationMeta,
    rec: ghcn.StationRecord,
    model: np.ndarray,
    model_years: list[int],
    cell: tuple[int, int],
    cell_offset: tuple[int, int],
    cell_elev: float,
    rules: Rules,
    cell_lake: float = 0.0,
) -> dict:
    """One station's row: observed and ERA5-Land frequencies, contingency, flags and status.

    ``model`` is the cube column ``snow_depth_cm[year, day(24,25,26)]`` at the station's cell
    (whole cm, −1 = nodata) for ``model_years``.
    """
    yidx = {y: k for k, y in enumerate(model_years)}
    model_ok = {y: model[k, 1] >= 0 for y, k in yidx.items()}
    used, incomplete = usable_years(rec, model_ok, rules)
    with_value = len(used) + len(incomplete)
    dz = cell_elev - meta.elev if np.isfinite(meta.elev) else float("nan")
    row: dict = {
        "id": meta.id, "name": meta.name, "lat": meta.lat, "lon": meta.lon,
        "elev_m": meta.elev, "country": meta.country, "state": meta.state,
        "cell": [int(cell[0]), int(cell[1])],
        "cell_offset": [int(cell_offset[0]), int(cell_offset[1])],
        "cell_elev_m": float(cell_elev), "elev_diff_m": float(dz),
        "region": region_of(meta.lat, meta.lon, cell_elev, meta.country),
        "us_inches": meta.id.startswith("US"),
        "years": len(used), "years_with_value": with_value,
        "incomplete_years": len(incomplete),
        "first": used[0] if used else None, "last": used[-1] if used else None,
        "coverage": len(used) / (used[-1] - used[0] + 1) if used else 0.0,
        "dec_zero_share": rec.dec_zero_share,
        "dec_gsod_share": rec.dec_gsod_share,
        "cell_lake_cover": float(cell_lake),
        "dec_tmean_c": rec.tmean.get(12, float("nan")),
        "continentality_c": rec.tmean.get(7, float("nan")) - rec.tmean.get(1, float("nan")),
    }  # fmt: skip
    row["climate"] = climate_class(row["dec_tmean_c"])
    tests = [rec.snowfall_without_depth(y, rules.min_snowfall_mm) for y in used]
    tests = [x for x in tests if x is not None]
    row["snowy_decembers"] = len(tests)
    row["snowfall_without_depth"] = int(sum(tests))
    flags = []
    if row["us_inches"]:
        flags.append("us_inches")
    if tuple(cell_offset) != (0, 0):
        flags.append("coastal")
    hi = max(meta.elev if np.isfinite(meta.elev) else 0, cell_elev if np.isfinite(cell_elev) else 0)
    if hi >= rules.high_mountain_m:
        flags.append("high_mountain")
    if np.isfinite(dz) and abs(dz) > rules.max_elev_diff_m:
        flags.append("elev_mismatch")
    if np.isfinite(cell_lake) and cell_lake > rules.lake_cover:
        flags.append("lake")
    gs = rec.dec_gsod_share
    if np.isfinite(gs) and gs > rules.gsod_share:
        flags.append("gsod_sourced")
    row["flags"] = flags

    if used:
        thr = rules.obs_threshold_mm
        o = np.array([rec.snwd[y][25] >= thr for y in used])
        m = np.array([model[yidx[y], 1] for y in used])
        row["obs_pct"] = 100 * float(o.mean())
        row["model_pct"] = {t: 100 * float((m >= t).mean()) for t in rules.thresholds_cm}
        row["agree_pct"] = {t: 100 * float(((m >= t) == o).mean()) for t in rules.thresholds_cm}
        row["yearly"] = {"years": used, "obs": o.astype(int).tolist(), "model": m.tolist()}
        row["table"] = {
            t: [
                int(((m >= t) & o).sum()),
                int(((m < t) & o).sum()),
                int(((m >= t) & ~o).sum()),
                int(((m < t) & ~o).sum()),
            ]
            for t in rules.thresholds_cm
        }  # fmt: skip  [hits, misses, false alarms, correct negatives]
        # 24-26 December, "white on any of the three days", where all three days are usable.
        y3 = [
            y for y in used
            if all(d in rec.snwd[y] for d in (24, 25, 26)) and (model[yidx[y]] >= 0).all()
        ]  # fmt: skip
        row["any3_years"] = len(y3)
        if y3:
            o3 = np.array([max(rec.snwd[y][d] for d in (24, 25, 26)) >= thr for y in y3])
            m3 = np.array([model[yidx[y]].max() for y in y3])
            row["any3_obs_pct"] = 100 * float(o3.mean())
            row["any3_model_pct"] = {t: 100 * float((m3 >= t).mean()) for t in rules.thresholds_cm}
    row["status"], row["reason"] = classify(row, rules)
    return row


def classify(row: dict, rules: Rules) -> tuple[str, str]:
    """("used" | "separated" | "excluded", reason). Data-quality reasons come first."""
    n, inc = row["years"], row["incomplete_years"]
    if row["years_with_value"] == 0:
        return "excluded", "no 25 December snow depth in the period"
    if inc > 0 and inc / row["years_with_value"] > rules.max_incomplete_share:
        zs = row["dec_zero_share"]
        if np.isfinite(zs) and zs < 0.02:
            return "excluded", "zeros not reported (snow depth only when snow lies)"
        return "excluded", "snow depth missing on observing days"
    if n < rules.min_years:
        return "excluded", f"only {n} usable years"
    swd, snowy = row.get("snowfall_without_depth", 0), row.get("snowy_decembers", 0)
    if swd >= 2 and swd / snowy > rules.max_snowfall_without_depth_share:
        return "excluded", f"zero snow depth despite snowfall ({swd} of {snowy} snowy Decembers)"
    if row["coverage"] < rules.min_coverage:
        return "excluded", f"patchy record ({row['coverage']:.0%} of years)"
    mcm = rules.always_white_model_cm
    if row["obs_pct"] >= rules.always_white_pct and (
        mcm is None or row["model_pct"].get(mcm, 0.0) >= rules.always_white_pct
    ):
        return "separated", "always white"
    if row["obs_pct"] < rules.never_white_pct and row["model_pct"][1] < rules.never_white_pct:
        return "separated", "almost never white"
    dz = row["elev_diff_m"]
    if np.isfinite(dz) and abs(dz) > rules.max_elev_diff_m:
        return "separated", f"cell {dz:+.0f} m vs station"
    return "used", ""


def data_quality_failed(row: dict) -> bool:
    """True when the auto mode should try the next station in the box."""
    return row["status"] == "excluded"


def list_ids(sc: dict) -> list[tuple[str, str]]:
    return [(str(i), str(n)) for i, n in sc.get("list", [])]


def snapshot_info(ghcn_dir: Path) -> dict:
    """When the cached bulk metadata was downloaded (GHCN-Daily changes daily)."""
    from datetime import UTC, datetime

    out = {}
    for n in ("ghcnd-stations.txt", "ghcnd-inventory.txt"):
        p = ghcn_dir / n
        if p.exists():
            out[n] = datetime.fromtimestamp(p.stat().st_mtime, UTC).strftime("%Y-%m-%d")
    return out
