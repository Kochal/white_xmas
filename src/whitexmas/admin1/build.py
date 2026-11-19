"""``whitexmas admin1``: statistics for states and provinces, in three resumable steps.

1. ``weights``: regions from Natural Earth, cell-fraction weights, population weights from
   GeoNames places, simplified outlines → ``interim/admin1/{regions.json, weights.npz,
   boundaries.json}``.
2. ``stats``: regional means of the indicators (every threshold, definition and window), the
   spread inside each region, the yearly series from one pass over the snow cube, trend and
   Mann-Kendall p of that series, projections per model → ``interim/admin1/stats.npz``.
3. ``export``: web files (contract v1.6) and a CSV → ``products/admin1/``.

Each step records a fingerprint of its inputs and skips work that is up to date.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from scipy import sparse

from ..config import Config
from ..paths import DataPaths
from . import stats as st
from .weights import NX, NY, area_weights, cell_area_km2, fractions, nearest_fallback

log = logging.getLogger(__name__)
ADMIN1_VERSION = 1


# --------------------------------------------------------------------------- paths
class Admin1Paths:
    def __init__(self, paths: DataPaths):
        self.interim = paths.interim / "admin1"
        self.products = paths.products / "admin1"

    @property
    def regions(self) -> Path:
        return self.interim / "regions.json"

    @property
    def weights(self) -> Path:
        return self.interim / "weights.npz"

    @property
    def boundaries(self) -> Path:
        return self.interim / "boundaries.json"

    @property
    def stats(self) -> Path:
        return self.interim / "stats.npz"

    @property
    def state(self) -> Path:
        return self.interim / "state.json"


def _state(ap: Admin1Paths) -> dict:
    return json.loads(ap.state.read_text()) if ap.state.exists() else {}


def _save_state(ap: Admin1Paths, **kv) -> None:
    s = _state(ap)
    s.update(kv)
    ap.interim.mkdir(parents=True, exist_ok=True)
    ap.state.write_text(json.dumps(s, indent=1))


def _hash(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(json.dumps(p, sort_keys=True, default=str).encode())
    return h.hexdigest()[:16]


def _ext_sha(paths: DataPaths, name: str) -> str:
    man = paths.external / "manifest.json"
    return json.loads(man.read_text()).get(name, {}).get("sha256", "") if man.exists() else ""


# --------------------------------------------------------------------------- step 1: weights
def step_weights(cfg: Config, paths: DataPaths, force: bool = False) -> dict:
    import shapely
    import zarr

    from ..export.places import read_cities
    from ..external import fetch
    from .boundaries import load_regions
    from .geometry import boundaries_geojson, simplify_regions
    from .weights import population_weights

    a1 = cfg.raw.get("admin1") or {}
    ap = Admin1Paths(paths)
    src = a1.get("source", "ne_10m_admin_1_states_provinces.zip")
    for name in (src, "ne_10m_admin_0_countries.zip", "cities15000.zip"):
        fetch(name, paths.external)
    ind = zarr.open_group(str(paths.indicators), mode="r")
    fp = _hash(
        "weights", ADMIN1_VERSION, a1, ind.attrs.get("fingerprint", ""),
        [_ext_sha(paths, n) for n in (src, "ne_10m_admin_0_countries.zip", "cities15000.zip")],
    )  # fmt: skip
    if not force and _state(ap).get("weights") == fp and ap.weights.exists():
        log.info("admin1 weights up to date (%s); skipping", fp)
        return {"skipped": True}

    t0 = time.time()
    regions = load_regions(paths.external, a1)
    t_load = time.time() - t0
    frac = fractions(
        regions,
        exact_max_cells=int(a1.get("exact_max_cells", 400)),
        k=int(a1.get("supersample", 10)),
        k_big=int(a1.get("supersample_big", 4)),
        big_cells=int(a1.get("supersample_big_cells", 1_000_000)),
    )
    t_frac = time.time() - t0 - t_load
    land = np.asarray(ind["land"][:], dtype=bool)
    glacier = np.asarray(ind["glacier"][:], dtype=bool)
    usable = land & ~glacier
    radius = int(a1.get("nearest_radius", 2))
    has_land = frac @ land.reshape(-1).astype("float64") > 0
    # fallback only for regions without any land cell (an all-glacier region stays empty)
    extra, picked = nearest_fallback(frac, regions, usable, radius)
    keep = np.array([not has_land[r] for r in range(len(regions))])
    extra = sparse.csr_matrix(extra.multiply(keep[:, None]))
    picked = {r: c for r, c in picked.items() if keep[r]}
    places = read_cities(paths.external / "cities15000.zip")
    pop, n_places, pop_sum = population_weights(regions, places, usable, radius)
    t_pop = time.time() - t0 - t_load - t_frac

    geoms = simplify_regions(
        regions, float(a1.get("simplify_deg", 0.03)), float(a1.get("min_part_km2", 30))
    )
    gj = boundaries_geojson(regions, geoms, int(a1.get("coord_decimals", 3)))
    meta = []
    for r in regions:
        p = shapely.point_on_surface(r["geom"])
        meta.append({
            **{k: r[k] for k in ("id", "name", "name_local", "type", "country", "country_name",
                                 "adm0_a3", "source", "n_features")},
            "lon": p.x, "lat": p.y, "bbox": list(r["geom"].bounds),
        })  # fmt: skip
    ap.interim.mkdir(parents=True, exist_ok=True)
    ap.regions.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    ap.boundaries.write_text(
        json.dumps(gj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    sparse.save_npz(ap.interim / "frac.npz", frac)
    sparse.save_npz(ap.interim / "fallback.npz", extra)
    sparse.save_npz(ap.interim / "pop.npz", pop)
    np.savez(ap.weights, n_places=n_places, places_pop=pop_sum, has_land=has_land)
    timings = {"load_s": round(t_load, 1), "fractions_s": round(t_frac, 1),
               "population_s": round(t_pop, 1), "total_s": round(time.time() - t0, 1)}  # fmt: skip
    _save_state(ap, weights=fp, weights_timings=timings, stats=None)
    log.info(
        "admin1 weights: %d regions, %d cell entries, %d nearest-cell fallbacks, %s",
        len(regions), frac.nnz, len(picked), timings,
    )  # fmt: skip
    return {"regions": len(regions), "nnz": int(frac.nnz), "fallbacks": len(picked), **timings}


def load_weights(ap: Admin1Paths):
    regions = json.loads(ap.regions.read_text(encoding="utf-8"))
    frac = sparse.load_npz(ap.interim / "frac.npz").tocsr()
    extra = sparse.load_npz(ap.interim / "fallback.npz").tocsr()
    pop = sparse.load_npz(ap.interim / "pop.npz").tocsr()
    w = np.load(ap.weights)
    return regions, frac, extra, pop, {k: w[k] for k in w.files}


# --------------------------------------------------------------------------- step 2: stats
def _projection_inputs(paths: DataPaths):
    """(model files, gwls, settings attrs) of the shipped ensemble, or None."""
    from ..projections.settings import ProjPaths

    pp = ProjPaths.from_data(paths)
    if not pp.ensemble.exists():
        return None
    import zarr

    z = zarr.open_group(str(pp.ensemble), mode="r")
    if z.attrs.get("placeholder"):
        return None
    models = json.loads(z.attrs["models"])
    settings = json.loads(z.attrs["settings"])
    gwls = [float(g) for g in z["gwl"][:]]
    defs = [str(d) for d in z["definition"][:]]
    files = [pp.models / f"{m}.nc" for m in models]
    missing = [f.name for f in files if not f.exists()]
    if missing:
        log.warning("admin1: projection model files missing (%s); no projections", missing)
        return None
    return {"models": models, "files": files, "gwls": gwls, "settings": settings,
            "definitions": defs, "attrs": dict(z.attrs)}  # fmt: skip


def regional_projections(
    paths: DataPaths, w_area, w_pop, usable_flat: np.ndarray, definition: str, proj: dict,
    zero_pp: float,
) -> dict:  # fmt: skip
    """Method B per region: each model's projected probability (the map's own transfer, from
    ``projections.ensemble.project_model``) is averaged over the region, then the ensemble
    statistics are taken across the models' regional means."""
    import xarray as xr

    from ..projections.baseline import load_baseline
    from ..projections.ensemble import project_model

    b = load_baseline(paths, definition, proj["settings"]["obs_window"])
    cells = np.nonzero(np.isfinite(b.p) & (b.n > 0))
    flat_cells = cells[0] * NX + cells[1]
    base_flat = np.full(NY * NX, np.nan)
    base_flat[flat_cells] = b.p[cells]
    ok = usable_flat & np.isfinite(base_flat)
    baseline = st.weighted_mean(w_area, base_flat, ok)
    nm, ng, nr = len(proj["files"]), len(proj["gwls"]), w_area.shape[0]
    area_m = np.full((ng, nm, nr), np.nan)
    pop_m = np.full((ng, nm, nr), np.nan)
    vals = np.full(NY * NX, np.nan)
    for mi, f in enumerate(proj["files"]):
        with xr.open_dataset(f) as ds:
            if definition not in ds["definition"].values:
                continue
            lat, lon = ds["lat"].values, ds["lon"].values
            deltas = {g: ds["delta"].sel(gwl=g, definition=definition).values
                      for g in proj["gwls"]}  # fmt: skip
        for gi, g in enumerate(proj["gwls"]):
            if not np.isfinite(deltas[g]).any():
                continue
            _, pj = project_model(deltas[g], lat, lon, b.p, b.n, cells)
            vals[:] = np.nan
            vals[flat_cells] = pj
            area_m[gi, mi] = st.weighted_mean(w_area, vals, ok)
            pop_m[gi, mi] = st.weighted_mean(w_pop, vals, ok)
        log.info("admin1 projections: model %d of %d (%s)", mi + 1, nm, f.stem)
    base_pop = st.weighted_mean(w_pop, base_flat, ok)
    out = {"proj_baseline": baseline, "proj_baseline_pop": base_pop}
    keys = ("p10", "p50", "p90", "change", "agree", "n_models")
    res = {k: np.full((ng, nr), np.nan) for k in keys}
    p50_pop = np.full((ng, nr), np.nan)
    for gi in range(ng):
        e = st.ensemble_summary(area_m[gi], baseline, zero_pp)
        for k in keys:
            res[k][gi] = e[k]
        p50_pop[gi] = st.ensemble_summary(pop_m[gi], base_pop, zero_pp)["p50"]
    for k in ("p10", "p50", "p90", "change"):
        out[f"proj_{k}"] = res[k]
    out["proj_agree"] = res["agree"].astype(bool)
    out["proj_n"] = res["n_models"].astype("int16")
    out["proj_p50_pop"] = p50_pop
    out["proj_models_area"] = area_m
    return out


def step_stats(cfg: Config, paths: DataPaths, force: bool = False, band: int = 50) -> dict:
    import zarr

    from ..definitions import white

    a1 = cfg.raw.get("admin1") or {}
    ap = Admin1Paths(paths)
    st_ = _state(ap)
    if not st_.get("weights") or not ap.weights.exists():
        raise FileNotFoundError("run `whitexmas admin1 weights` first")
    inds = {t["id"]: zarr.open_group(str(paths.indicators_for(t)), mode="r")
            for t in cfg.thresholds}  # fmt: skip
    cube_root = zarr.open_group(str(paths.cube), mode="r")
    proj = _projection_inputs(paths)
    fp = _hash(
        "stats", ADMIN1_VERSION, st_["weights"], a1,
        {k: z.attrs.get("fingerprint", "") for k, z in inds.items()},
        cube_root.attrs.get("input_fingerprint", ""),
        proj and {k: proj["attrs"].get(k) for k in ("models", "settings", "baseline_threshold")},
        cfg.section_hash("years", "windows", "definitions", "thresholds", "trend"),
    )  # fmt: skip
    if not force and st_.get("stats") == fp and ap.stats.exists():
        log.info("admin1 stats up to date (%s); skipping", fp)
        return {"skipped": True}

    t0 = time.time()
    regions, frac, extra, pop, wmeta = load_weights(ap)
    nr = len(regions)
    ind0 = inds[cfg.default_threshold["id"]]
    lat = np.asarray(ind0["lat"][:], dtype="float64")
    land = np.asarray(ind0["land"][:], dtype=bool).reshape(-1)
    glacier = np.asarray(ind0["glacier"][:], dtype=bool).reshape(-1)
    usable = land & ~glacier
    area = area_weights(frac, lat)
    has_usable = frac @ usable.astype("float64") > 0
    fallback = np.asarray(extra.sum(axis=1)).ravel() > 0
    w_area = sparse.csr_matrix(area + extra)
    w_pop = pop
    frac_used = sparse.csr_matrix(frac + extra)
    cell_km2 = np.repeat(cell_area_km2(lat), NX)
    out: dict = {
        "area_km2": frac @ cell_km2,
        "land_km2": frac @ (cell_km2 * usable),
        "cells": frac_used @ usable.astype("float64"),
        "glacier_pct": 100 * st.weighted_mean(area, glacier.astype("float64"), land),
        "has_land": wmeta["has_land"],
        "has_usable": has_usable,
        "fallback": fallback,
        "n_places": wmeta["n_places"],
        "places_pop": wmeta["places_pop"],
    }
    orog = np.asarray(cube_root["orography_m"][:], dtype="float64").reshape(-1)
    out["elev_mean"] = st.weighted_mean(w_area, orog, usable)
    out["elev_min"], out["elev_max"] = st.weighted_extremes(frac_used, orog, usable)

    T = [t["id"] for t in cfg.thresholds]
    D = cfg.definition_ids
    wins = cfg.windows()
    W = [w.id for w in wins]
    share_pct = float(a1.get("spread_share_pct", 50))
    shape = (len(T), len(D), len(W), nr)
    for k in ("p", "p_pop", "share50", "p5", "p95"):
        out[k] = np.full(shape, np.nan)
    t1 = time.time()
    for ti, tid in enumerate(T):
        prob = inds[tid]["probability"]
        for di in range(len(D)):
            for wi in range(len(W)):
                v = np.asarray(prob[di, wi], dtype="float64").reshape(-1)
                out["p"][ti, di, wi] = st.weighted_mean(w_area, v, usable)
                out["p_pop"][ti, di, wi] = st.weighted_mean(w_pop, v, usable)
                ge = np.where(np.isfinite(v), (v >= share_pct).astype("float64"), np.nan)
                out["share50"][ti, di, wi] = 100 * st.weighted_mean(w_area, ge, usable)
                q = st.weighted_percentiles(w_area, v, usable, (5, 95))
                out["p5"][ti, di, wi], out["p95"][ti, di, wi] = q
        log.info("admin1 stats: windows of threshold %s done", tid)
    t_windows = time.time() - t1

    # yearly series: one pass over the cube in latitude bands
    t1 = time.time()
    years = np.asarray(cube_root["year"][:])
    keep = (years >= cfg.first_year) & (years <= cfg.last_year)
    yrs = years[keep]
    cube = cube_root["snow_depth_cm"]
    num = np.zeros((len(T), len(D), nr, len(yrs)))
    den = np.zeros_like(num)
    w_csc = w_area.tocsc()
    for j0 in range(0, NY, band):
        j1 = min(NY, j0 + band)
        c0, c1 = j0 * NX, j1 * NX
        wb = w_csc[:, c0:c1]
        if wb.nnz == 0:
            continue
        block = np.asarray(cube[:, :, j0:j1, :])[keep]
        ub = usable[c0:c1]
        for ti, t in enumerate(cfg.thresholds):
            for di, d in enumerate(D):
                wht = white(block, d, t["cm"]).reshape(len(yrs), -1)
                a, b_ = st.weighted_means_2d(wb, 100.0 * wht, ub)
                num[ti, di] += a
                den[ti, di] += b_
        log.info("admin1 series: rows %d-%d of %d", j0, j1, NY)
    with np.errstate(invalid="ignore", divide="ignore"):
        out["series"] = np.where(den > 0, num / den, np.nan)
    t_series = time.time() - t1
    out["trend"] = np.full((len(T), len(D), nr), np.nan)
    out["trend_p"] = np.full_like(out["trend"], np.nan)
    for ti in range(len(T)):
        for di in range(len(D)):
            out["trend"][ti, di] = st.ols_slope_per_decade(out["series"][ti, di], yrs)
            out["trend_p"][ti, di] = st.mann_kendall_p(out["series"][ti, di])

    t1 = time.time()
    pinfo = {}
    if proj:
        pdef = cfg.default_definition if cfg.default_definition in proj["definitions"] else (
            proj["definitions"][0])  # fmt: skip
        res = regional_projections(
            paths, w_area, w_pop, usable, pdef, proj, float(a1.get("proj_zero_pp", 0.05))
        )
        out.update(res)
        pinfo = {"gwls": proj["gwls"], "models": proj["models"], "definition": pdef,
                 "baseline_window": proj["settings"]["obs_window"]}  # fmt: skip
    t_proj = time.time() - t1

    meta = {
        "thresholds": T, "definitions": D, "windows": W, "years": [int(y) for y in yrs],
        "window_kinds": [w.kind for w in wins], "projections": pinfo,
    }  # fmt: skip
    np.savez_compressed(ap.stats, meta=json.dumps(meta), **out)
    timings = {
        "windows_s": round(t_windows, 1),
        "series_s": round(t_series, 1),
        "projections_s": round(t_proj, 1),
        "total_s": round(time.time() - t0, 1),
    }
    _save_state(ap, stats=fp, stats_timings=timings)
    log.info("admin1 stats written (%s)", timings)
    return timings


# --------------------------------------------------------------------------- step 3: export
def load_stats(ap: Admin1Paths) -> tuple[dict, dict]:
    z = np.load(ap.stats, allow_pickle=False)
    meta = json.loads(str(z["meta"]))
    return {k: z[k] for k in z.files if k != "meta"}, meta


def export_info(cfg: Config, meta: dict) -> dict:
    from ..export import data_version, git_hash

    a1 = cfg.raw.get("admin1") or {}
    a, b = cfg.change_pair
    W = meta["windows"]
    p = meta.get("projections") or {}
    return {
        "data_version": data_version(cfg),
        "built": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "build_hash": git_hash(),
        "thresholds": meta["thresholds"],
        "definitions": meta["definitions"],
        "default_definition": cfg.default_definition,
        "windows": W,
        "years": meta["years"],
        "window_ids": {"full": cfg.full_window().id, "then": a, "now": b},
        "w_then": W.index(a),
        "w_now": W.index(b),
        "trend_alpha": cfg.trend_p,
        "low_res_cells": a1.get("low_res_cells", 3),
        "spread_share_pct": float(a1.get("spread_share_pct", 50)),
        "gwls": p.get("gwls") or [],
        "proj_models": p.get("models") or [],
        "proj_definition": p.get("definition"),
        "proj_baseline_window": p.get("baseline_window"),
    }


def write_csv(path: Path, regions: list[dict], s: dict, info: dict) -> int:
    """One row per region, threshold and definition: every window, change, trend, spread
    (for the "now" window) and, for the default threshold and definition, projections."""
    from .export import region_flags

    W = info["windows"]
    wn = info["w_now"]
    d0 = info["definitions"].index(info["default_definition"])
    gwls = info["gwls"]
    head = ["id", "name", "country", "threshold", "definition", "flags", "area_km2",
            "land_km2", "cells", "glacier_pct", "elev_min_m", "elev_mean_m", "elev_max_m",
            "places", "places_pop"]  # fmt: skip
    head += [f"p_{w}" for w in W] + [f"p_pop_{w}" for w in W]
    head += ["change", "trend_pp_per_decade", "trend_mk_p",
             f"share50_{W[wn]}", f"p5_{W[wn]}", f"p95_{W[wn]}"]  # fmt: skip
    for g in gwls:
        head += [f"proj_p10_gwl{g}", f"proj_p50_gwl{g}", f"proj_p90_gwl{g}", f"proj_agree_gwl{g}"]

    def f(v, nd=1):
        return "" if v is None or not np.isfinite(v) else f"{float(v):.{nd}f}"

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(head)
        for k, r in enumerate(regions):
            for ti, t in enumerate(info["thresholds"]):
                for di, d in enumerate(info["definitions"]):
                    p = s["p"][ti, di, :, k]
                    row = [r["id"], r["name"], r["country"], t, d,
                           " ".join(region_flags(s, k, info["low_res_cells"])),
                           f(s["area_km2"][k], 0), f(s["land_km2"][k], 0), f(s["cells"][k]),
                           f(s["glacier_pct"][k]), f(s["elev_min"][k], 0),
                           f(s["elev_mean"][k], 0), f(s["elev_max"][k], 0),
                           int(s["n_places"][k]), int(s["places_pop"][k])]  # fmt: skip
                    row += [f(v) for v in p] + [f(v) for v in s["p_pop"][ti, di, :, k]]
                    row += [f(p[wn] - p[info["w_then"]]), f(s["trend"][ti, di, k], 2),
                            f(s["trend_p"][ti, di, k], 4), f(s["share50"][ti, di, wn, k]),
                            f(s["p5"][ti, di, wn, k]), f(s["p95"][ti, di, wn, k])]  # fmt: skip
                    for gi in range(len(gwls)):
                        if ti == 0 and di == d0:
                            agree = int(bool(s["proj_agree"][gi, k]))
                            row += [f(s["proj_p10"][gi, k]), f(s["proj_p50"][gi, k]),
                                    f(s["proj_p90"][gi, k]), agree]  # fmt: skip
                        else:
                            row += ["", "", "", ""]
                    wr.writerow(row)
    return path.stat().st_size


def step_export(cfg: Config, paths: DataPaths, out: Path | None = None) -> dict:
    import gzip

    from .export import manifest_block, write_web

    ap = Admin1Paths(paths)
    if not ap.stats.exists():
        raise FileNotFoundError("run `whitexmas admin1 stats` first")
    t0 = time.time()
    regions = json.loads(ap.regions.read_text(encoding="utf-8"))
    s, meta = load_stats(ap)
    s["source"] = np.array([r["source"] for r in regions])
    info = export_info(cfg, meta)
    boundaries = json.loads(ap.boundaries.read_text(encoding="utf-8"))
    prod = Path(out) if out else ap.products
    web = prod / "web"
    sizes = write_web(web, regions, s, boundaries, info)
    gz = {
        rel: len(gzip.compress((web / rel).read_bytes(), 9))
        for rel in sizes
    }  # fmt: skip
    files = {
        rel: {"bytes": b, "gzip_bytes": gz[rel],
              "sha256": hashlib.sha256((web / rel).read_bytes()).hexdigest()}
        for rel, b in sizes.items()
    }  # fmt: skip
    csv_bytes = write_csv(prod / "admin1_stats.csv", regions, s, info)
    frag = {"admin1": manifest_block(info), "files": files}
    (prod / "manifest_fragment.json").write_text(json.dumps(frag, indent=1), encoding="utf-8")
    summary = {
        "regions": len(regions),
        "countries": len({r["country"] for r in regions}),
        "files": len(sizes),
        "bytes": sum(sizes.values()),
        "gzip_bytes": sum(gz.values()),
        "index_gzip": gz["admin1/index.json"],
        "boundaries_gzip": gz["admin1/boundaries.json"],
        "largest_country": max(
            (k for k in sizes if k.startswith("admin1/c/")), key=lambda k: sizes[k]
        ),
        "csv_bytes": csv_bytes,
        "seconds": round(time.time() - t0, 1),
    }
    summary["largest_country_gzip"] = gz[summary["largest_country"]]
    (prod / "build_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    log.info("admin1 export: %s", summary)
    return summary
