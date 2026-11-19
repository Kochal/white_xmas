"""Global station assessment (``whitexmas stations`` with ``stations.mode: auto``).

Selects GHCN-Daily stations systematically (``station_select``), compares each with the
pipeline's snow cube, and writes under ``products/stations/``:

- ``stations_global.csv``: one row per examined station (schema in docs/methodology.md);
- ``stations_global.json``: a compact columnar copy for web use (``wx-stations-v1``);
- ``stations.json``: every station row and all statistics (input to the report and ``sanity``);
- ``snow_variable_check.html``: the report.

Nothing here changes the shipped threshold or any data product: the report recommends, the
person decides.
"""

from __future__ import annotations

import csv
import json
import logging
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from . import ghcn
from . import station_select as sel
from . import station_stats as ss
from .config import Config
from .paths import DataPaths

log = logging.getLogger(__name__)

FOCUS_CM = 5  # the shipped calibrated threshold (D-17); only used to label the report
MIN_GROUP = 8  # stations a group needs before its own threshold is reported


class CubeColumns:
    """Per-cell reads of ``snow_depth_cm[year, day, lat, lon]`` with a small chunk cache."""

    def __init__(self, cube_path: Path):
        import zarr

        self.g = zarr.open_group(str(cube_path), mode="r")
        self.arr = self.g["snow_depth_cm"]
        self.years = [int(y) for y in self.g["year"][:]]
        self.land = self.g["land"][:]
        self.oro = self.g["orography_m"][:] if "orography_m" in self.g else None
        self.lake = self.g["lake_cover"][:] if "lake_cover" in self.g else None
        self.cj, self.ci = self.arr.chunks[2], self.arr.chunks[3]
        self._cache: dict[tuple[int, int], np.ndarray] = {}

    def column(self, j: int, i: int) -> np.ndarray:
        key = (j // self.cj, i // self.ci)
        if key not in self._cache:
            if len(self._cache) > 128:
                self._cache.clear()
            j0, i0 = key[0] * self.cj, key[1] * self.ci
            self._cache[key] = self.arr[:, :, j0 : j0 + self.cj, i0 : i0 + self.ci]
        j0, i0 = key[0] * self.cj, key[1] * self.ci
        return self._cache[key][:, :, j - j0, i - i0]

    def cell_elev(self, cell: tuple[int, int]) -> float:
        return float(self.oro[cell]) if self.oro is not None else float("nan")

    def cell_lake(self, cell: tuple[int, int]) -> float:
        return float(self.lake[cell]) if self.lake is not None else 0.0

    def cell_of(self, m: ghcn.StationMeta):
        """(land cell, its offset from the station's own cell, cell elevation) or None."""
        from .export.places import cell_index, nearest_valid

        j, i = cell_index(m.lat, m.lon)
        cell = nearest_valid(self.land, j, i)
        if cell is None:
            return None
        return cell, (cell[0] - j, cell[1] - i), self.cell_elev(cell)


def examine(
    sid: str,
    metas: dict[str, ghcn.StationMeta],
    cube: CubeColumns,
    ghcn_dir: Path,
    rules: sel.Rules,
    first: int,
    last: int,
) -> dict | None:
    m = metas.get(sid)
    p = ghcn.station_path(ghcn_dir, sid)
    if m is None or not p.exists():
        return None
    c = cube.cell_of(m)
    if c is None:
        return None
    cell, off, ce = c
    rec = ghcn.read_station_cached(p, first, last)
    col = cube.column(*cell)
    yrs = [y for y in cube.years if first <= y <= last]
    model = np.stack([col[cube.years.index(y)] for y in yrs])
    lake = cube.cell_lake(cell) if hasattr(cube, "cell_lake") else 0.0
    return sel.evaluate_station(m, rec, model, yrs, cell, off, ce, rules, lake)


def select_and_examine(cfg: Config, paths: DataPaths, cube: CubeColumns) -> tuple[list, dict]:
    sc = cfg.raw["stations"]
    rules = sel.Rules.from_config(sc)
    auto = sel.AutoSettings.from_config(sc)
    gdir = paths.external / "ghcn"
    st_txt, inv_txt, _ = ghcn.metadata(gdir)
    metas = ghcn.read_stations(st_txt)
    inv = ghcn.read_inventory(inv_txt)
    first, last = cfg.first_year, cfg.last_year

    def cell_of(m):
        c = cube.cell_of(m)
        return None if c is None else (c[0], c[2])

    boxes = sel.candidate_boxes(metas, inv, first, last, rules, auto, cell_of)
    n_inv = sum(1 for s, fl in inv.items() if s in metas and metas[s].lat > auto.min_lat)
    n_span = sum(
        1
        for s, fl in inv.items()
        if s in metas
        and metas[s].lat > auto.min_lat
        and sel.span_in(fl, first, last) >= rules.min_years
    )
    log.info("auto: %d candidate stations in %d boxes", sum(map(len, boxes.values())), len(boxes))
    rows: list[dict] = []
    tries = dict.fromkeys(boxes, 0)
    open_boxes = list(boxes)
    for rnd in range(auto.max_tries):
        want = {b: boxes[b][tries[b]] for b in open_boxes if tries[b] < len(boxes[b])}
        if not want:
            break
        ghcn.fetch_stations(sorted(want.values()), gdir, auto.concurrency)
        still = []
        for b, sid in sorted(want.items(), key=lambda kv: kv[1]):
            row = examine(sid, metas, cube, gdir, rules, first, last)
            tries[b] += 1
            if row is None:
                still.append(b)
                continue
            row["box"] = list(b)
            row["rank_in_box"] = tries[b]
            row["candidates_in_box"] = len(boxes[b])
            rows.append(row)
            if sel.data_quality_failed(row):
                still.append(b)
        log.info("auto round %d: %d stations examined, %d boxes still open", rnd + 1, len(want),
                 len(still))  # fmt: skip
        open_boxes = still
    info = {
        "inventory_snwd_stations": n_inv,
        "with_min_span": n_span,
        "candidates_with_land_cell": sum(map(len, boxes.values())),
        "boxes": len(boxes),
        "box_deg": auto.box_deg,
        "max_tries": auto.max_tries,
        "boxes_with_usable_station": len(
            {tuple(r["box"]) for r in rows if not sel.data_quality_failed(r)}
        ),
        "boxes_without_usable_station": len(boxes)
        - len({tuple(r["box"]) for r in rows if not sel.data_quality_failed(r)}),
        "boxes_stopped_at_max_tries": sum(1 for b in open_boxes if tries[b] < len(boxes[b])),
        "snapshot": sel.snapshot_info(gdir),
    }
    return rows, info


def list_set(cfg: Config, paths: DataPaths, cube: CubeColumns) -> list[dict]:
    """The D-17 hand-picked stations under the new rules (for comparison in the report)."""
    sc = cfg.raw["stations"]
    rules = sel.Rules.from_config(sc)
    gdir = paths.external / "ghcn"
    metas = ghcn.read_stations(gdir / "ghcnd-stations.txt")
    ids = [i for i, _ in sel.list_ids(sc)]
    ghcn.fetch_stations(ids, gdir)
    rows = []
    for sid in ids:
        r = examine(sid, metas, cube, gdir, rules, cfg.first_year, cfg.last_year)
        if r is not None:
            rows.append(r)
    return rows


def assess(
    rows: list[dict], thresholds: list[int], n_boot: int = 1000, rules: sel.Rules | None = None
) -> dict:
    used = [r for r in rows if r["status"] == "used"]
    ok = [r for r in rows if r["status"] != "excluded"]
    if not used:
        return {"n_used": 0}
    groups = {}
    for dim, key in ss.DIMENSIONS.items():
        groups[dim] = {
            label: ss.summarize(sub, thresholds, FOCUS_CM, n_boot)
            for label, sub in sorted(ss.group_by(used, key).items())
        }
    # Elevation effect over every station that passed the data-quality rules and is neither
    # always nor almost never white: those separated only for elevation are the interesting ones.
    elev_rows = [r for r in ok if r["status"] == "used" or "elev_mismatch" in r["flags"]]
    elev_rows = [r for r in elev_rows if r["reason"] in ("",) or r["reason"].startswith("cell")]
    return {
        "n_used": len(used),
        "overall": ss.summarize(used, thresholds, FOCUS_CM, n_boot),
        "ci_methods": ss.ci_methods(used, FOCUS_CM, n_boot),
        "region_balanced": ss.region_balanced(used, thresholds, MIN_GROUP, n_boot=n_boot),
        "groups": groups,
        "loro": ss.leave_one_region_out(used, thresholds, MIN_GROUP, FOCUS_CM),
        "cv": ss.blocked_cv(used, thresholds, MIN_GROUP, FOCUS_CM),
        "elevation": ss.elevation_effect(elev_rows, FOCUS_CM, n_boot),
        "elevation_separated": ss.summarize(
            [r for r in elev_rows if r["status"] == "separated"], thresholds, FOCUS_CM, n_boot
        ),
        "elevation_within_region": ss.within_region_slope(used, FOCUS_CM, n_boot),
        "flat": _flat(used, thresholds, n_boot),
        "high_mountain": ss.summarize(
            [r for r in used if "high_mountain" in r["flags"]], thresholds, FOCUS_CM, n_boot
        ),
        "any3": _any3(used, thresholds),
        "sensitivity": sensitivity(rows, rules, thresholds, n_boot) if rules else [],
    }


def sensitivity(rows: list[dict], rules: sel.Rules, thresholds: list[int], n_boot: int) -> list:
    """The headline numbers under alternative rules (one station per box throughout)."""
    import dataclasses

    def per_box(variant: sel.Rules) -> list[dict]:
        best: dict[tuple, dict] = {}
        for r in sorted(rows, key=lambda r: (tuple(r["box"]), r["rank_in_box"])):
            b = tuple(r["box"])
            if b in best:
                continue
            st, reason = sel.classify(r, variant)
            if st != "excluded":
                best[b] = {**r, "status": st, "reason": reason}
        return [r for r in best.values() if r["status"] == "used"]

    used = [r for r in rows if r["status"] == "used"]
    loose_cov = dataclasses.replace(rules, min_coverage=0.5, min_years=10)
    no_elev = dataclasses.replace(rules, max_elev_diff_m=float("inf"))
    variants = [
        ("main rules", used),
        ("coverage ≥ 50 %, ≥ 10 years", per_box(loose_cov)),
        ("elevation mismatch not separated", per_box(no_elev)),
        ("only stations within 50 m of their cell's elevation", [r for r in used if is_flat(r)]),
        (
            "only stations within 100 m of their cell's elevation",
            [r for r in used if abs(r["elev_diff_m"]) < 100],
        ),
        ("only stations with ≥ 30 years", [r for r in used if r["years"] >= 30]),
        ("only records starting in 1981 or later", [r for r in used if (r["first"] or 0) >= 1981]),
        ("without US stations (whole inches)", [r for r in used if not r["us_inches"]]),
        ("only US stations", [r for r in used if r["us_inches"]]),
        ("without coastal stations", [r for r in used if "coastal" not in r["flags"]]),
        ("without high-mountain stations", [r for r in used if "high_mountain" not in r["flags"]]),
        ("without lake stations (lake cover > 0.3)", [r for r in used if "lake" not in r["flags"]]),
    ]
    out = []
    for name, rs in variants:
        if len(rs) < 3:
            out.append({"variant": name, "n": len(rs)})
            continue
        s = ss.summarize(rs, thresholds, FOCUS_CM, n_boot)
        rb = ss.region_balanced(rs, thresholds, MIN_GROUP, n_boot=n_boot)
        out.append({
            "variant": name, "n": s["n"], "bias_pp": s["bias_pp"], "bias_ci": s["bias_ci"],
            "mae_pp": s["mae_pp"], "best_whole_cm": s["best_whole_cm"],
            "t_star_cm": s["t_star_cm"], "t_star_ci": s["t_star_ci"],
            "region_balanced_bias_pp": rb.get("bias_pp", {}),
        })  # fmt: skip
    return out


FLAT_M = 50  # "at its cell's elevation": |cell − station| < 50 m


def is_flat(r: dict) -> bool:
    return bool(np.isfinite(r["elev_diff_m"]) and abs(r["elev_diff_m"]) < FLAT_M)


def _flat(used: list[dict], thresholds: list[int], n_boot: int) -> dict:
    """The same statistics for stations within 50 m of their cell's mean elevation."""
    flat = [r for r in used if is_flat(r)]
    if len(flat) < 3:
        return {"n": len(flat)}
    return {
        "max_elev_diff_m": FLAT_M,
        "overall": ss.summarize(flat, thresholds, FOCUS_CM, n_boot),
        "region_balanced": ss.region_balanced(flat, thresholds, MIN_GROUP, n_boot=n_boot),
        "regions": {
            k: ss.summarize(v, thresholds, FOCUS_CM, n_boot)
            for k, v in sorted(ss.group_by(flat, lambda r: r["region"]).items())
        },
        "cv": ss.blocked_cv(flat, thresholds, MIN_GROUP, FOCUS_CM),
    }


def _any3(used: list[dict], thresholds: list[int]) -> dict:
    rs = [r for r in used if r.get("any3_years", 0) >= 10]
    if not rs:
        return {}
    obs = np.array([r["any3_obs_pct"] for r in rs])
    return {
        "n": len(rs),
        "obs_pct": float(obs.mean()),
        "bias_pp": {
            t: float(np.mean([r["any3_model_pct"][t] for r in rs]) - obs.mean()) for t in thresholds
        },
        "mae_pp": {
            t: float(np.mean(np.abs([r["any3_model_pct"][t] for r in rs] - obs)))
            for t in thresholds
        },
    }


# --------------------------------------------------------------------------- outputs
CSV_FIELDS = [
    "id", "name", "lat", "lon", "elev_m", "country", "country_name", "state", "region",
    "cell_j", "cell_i", "cell_offset_j", "cell_offset_i", "cell_elev_m", "elev_diff_m",
    "years", "first", "last", "coverage", "years_with_value", "incomplete_years",
    "dec_zero_share", "dec_gsod_share", "cell_lake_cover", "dec_tmean_c", "continentality_c",
    "climate", "obs_pct",
]  # fmt: skip


def write_csv(path: Path, rows: list[dict], thresholds: list[int], countries: dict) -> None:
    cols = CSV_FIELDS + [f"era5_ge_{t}cm_pct" for t in thresholds] + [
        f"bias_{FOCUS_CM}cm_pp", f"hits_{FOCUS_CM}cm", f"misses_{FOCUS_CM}cm",
        f"false_alarms_{FOCUS_CM}cm", f"correct_neg_{FOCUS_CM}cm", f"mcnemar_p_{FOCUS_CM}cm",
        "any3_years", "any3_obs_pct", f"any3_era5_ge_{FOCUS_CM}cm_pct",
        "status", "reason", "flags",
    ]  # fmt: skip
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in sorted(rows, key=lambda r: r["id"]):
            has = "model_pct" in r
            vals = [
                r["id"], r["name"], r["lat"], r["lon"], _r(r["elev_m"], 1), r["country"],
                countries.get(r["country"], ""), r["state"], r["region"], r["cell"][0],
                r["cell"][1], r["cell_offset"][0], r["cell_offset"][1], _r(r["cell_elev_m"], 1),
                _r(r["elev_diff_m"], 1), r["years"], r["first"] or "", r["last"] or "",
                _r(r["coverage"], 3), r["years_with_value"], r["incomplete_years"],
                _r(r["dec_zero_share"], 3), _r(r.get("dec_gsod_share"), 3),
                _r(r.get("cell_lake_cover"), 3), _r(r["dec_tmean_c"], 1),
                _r(r["continentality_c"], 1),
                r["climate"], _r(r.get("obs_pct"), 1),
            ]  # fmt: skip
            vals += [_r(r["model_pct"][t], 1) if has else "" for t in thresholds]
            if has:
                h, mi, fa, cn = r["table"][FOCUS_CM]
                vals += [_r(ss.bias(r, FOCUS_CM), 1), h, mi, fa, cn,
                         _r(ss.mcnemar_p(r, FOCUS_CM), 4)]  # fmt: skip
            else:
                vals += [""] * 6
            vals += [r.get("any3_years", ""), _r(r.get("any3_obs_pct"), 1),
                     _r(r.get("any3_model_pct", {}).get(FOCUS_CM), 1)]  # fmt: skip
            vals += [r["status"], r["reason"], "|".join(r["flags"])]
            w.writerow(vals)


WEB_FIELDS = ["id", "name", "lat", "lon", "elev_m", "country", "region", "years", "first",
              "last", "obs_pct", "era5_1cm_pct", "era5_5cm_pct", "status", "flags"]  # fmt: skip


def web_json(rows: list[dict], meta: dict) -> dict:
    """Compact columnar station list (schema ``wx-stations-v1``, documented in methodology.md)."""
    out_rows = []
    for r in sorted(rows, key=lambda r: r["id"]):
        if r["status"] == "excluded":
            continue  # web shows only stations with a trustworthy record
        if r["status"] == "separated" and "gsod_sourced" in r["flags"]:
            continue  # "always white" from a source that omits zeros: unverifiable
        mp = r.get("model_pct", {})
        out_rows.append([
            r["id"], r["name"], round(r["lat"], 4), round(r["lon"], 4), _r(r["elev_m"], 0, None),
            r["country"], r["region"], r["years"], r["first"], r["last"],
            _r(r.get("obs_pct"), 1, None), _r(mp.get(1), 1, None), _r(mp.get(5), 1, None),
            r["status"], r["flags"],
        ])  # fmt: skip
    return {"schema": "wx-stations-v1", **meta, "fields": WEB_FIELDS, "rows": out_rows}


def _r(v, nd: int, empty=""):
    if v is None:
        return empty
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    if not math.isfinite(f):
        return empty
    return round(f, nd) if nd else int(round(f))


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return str(o)


def _clean(o):
    """JSON-safe: ±inf/nan -> None, tuple keys stringified."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, float | np.floating):
        f = float(o)
        if math.isfinite(f):
            return f
        return "inf" if f > 0 else "-inf" if f < 0 else None
    return o


def run(cfg: Config, paths: DataPaths, out_dir: Path | None = None, n_boot: int = 1000) -> dict:
    from .station_report import render

    sc = cfg.raw["stations"]
    thresholds = [int(t) for t in sc["thresholds_cm"]]
    cube = CubeColumns(paths.cube)
    rows, info = select_and_examine(cfg, paths, cube)
    countries = ghcn.read_countries(paths.external / "ghcn" / "ghcnd-countries.txt")
    for r in rows:
        r["country_name"] = countries.get(r["country"], r["country"])
    stats = assess(rows, thresholds, n_boot, sel.Rules.from_config(sc))
    d17 = list_set(cfg, paths, cube)
    d17_used = [r for r in d17 if r["status"] == "used"]
    result = {
        "built": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "auto",
        "threshold_cm_in_use": cfg.threshold_cm,
        "focus_cm": FOCUS_CM,
        "years": [cfg.first_year, cfg.last_year],
        "thresholds_cm": thresholds,
        "rules": sel.Rules.from_config(sc).__dict__,
        "selection": info,
        "stats": stats,
        "d17_list": {
            "n": len(d17),
            "n_used": len(d17_used),
            "summary": ss.summarize(d17_used, thresholds, FOCUS_CM, n_boot) if d17_used else {},
            "rows": [{k: r[k] for k in ("id", "name", "status", "reason")} for r in d17],
        },
        "stations": rows,
    }
    # Compatibility with `whitexmas sanity` (reads calibration.n_calibration/best_cm/stats).
    ov = stats.get("overall", {})
    if ov.get("n"):
        result["calibration"] = {
            "n_calibration": ov["n"],
            "n_excluded": len(rows) - ov["n"],
            "best_cm": ov["best_whole_cm"],
            "stats": {
                t: {
                    "bias_pp": ov["bias_pp"][t],
                    "mae_pp": ov["mae_pp"][t],
                    "r": _corr(stats, rows, t),
                    "agree_pct": _agree(rows, t),
                }
                for t in thresholds
            },  # fmt: skip
        }
    out_dir = out_dir or paths.products / "stations"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "stations.json").write_text(
        json.dumps(_clean(result), indent=1, default=_json_default), encoding="utf-8"
    )
    write_csv(out_dir / "stations_global.csv", rows, thresholds, countries)
    meta = {
        "built": result["built"],
        "years": result["years"],
        "obs_threshold_mm": result["rules"]["obs_threshold_mm"],
        "threshold_cm_in_use": cfg.threshold_cm,
        "source": "NOAA NCEI GHCN-Daily (Menne et al.), element SNWD, 25 December",
        "ghcn_snapshot": info["snapshot"],
    }
    (out_dir / "stations_global.json").write_text(
        json.dumps(_clean(web_json(rows, meta)), separators=(",", ":"), default=_json_default),
        encoding="utf-8",
    )
    (out_dir / "snow_variable_check.html").write_text(render(result, paths), encoding="utf-8")
    log.info("stations (auto): %d examined, %d used; written to %s", len(rows),
             stats.get("n_used", 0), out_dir)  # fmt: skip
    return result


def _used(rows):
    return [r for r in rows if r["status"] == "used"]


def _corr(stats, rows, t):
    u = _used(rows)
    if len(u) < 3:
        return float("nan")
    return float(np.corrcoef([r["model_pct"][t] for r in u], [r["obs_pct"] for r in u])[0, 1])


def _agree(rows, t):
    u = _used(rows)
    return float(np.mean([r["agree_pct"][t] for r in u])) if u else float("nan")
