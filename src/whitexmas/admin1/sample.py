"""A small, clearly fake ``wx-admin1-v1`` dataset for building and testing the website.

Real Natural Earth outlines for a few countries, written by the real writer
(:func:`whitexmas.admin1.export.write_web`), with made-up values: a smooth function of
latitude and elevation-free noise. ``data_version`` is ``"sample"`` and every number is fake.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

SAMPLE_COUNTRIES = ("AUT", "CNM", "DEU", "FIN", "ITA", "LIE")


def fake_stats(regions: list[dict], info: dict, seed: int = 1) -> dict:
    rng = np.random.default_rng(seed)
    nr = len(regions)
    T, D, W = len(info["thresholds"]), len(info["definitions"]), len(info["windows"])
    Y = len(info["years"])
    lat = np.array([r["lat"] for r in regions])
    base = np.clip((lat - 38.0) * 3.0, 0, 95)  # fake: snowier to the north
    t_off = np.array([0.0, 25.0, 0, 0][:T])[:, None, None, None]
    d_off = np.array([0.0, -8.0, 6.0][:D])[None, :, None, None]
    w_off = np.linspace(4, -6, W)[None, None, :, None]
    p = np.clip(base[None, None, None, :] + t_off + d_off + w_off, 0, 100)
    s: dict = {
        "p": p,
        "p_pop": np.clip(p - 5, 0, 100),
        "share50": np.clip((p - 30) * 2, 0, 100),
        "p5": np.clip(p - 20, 0, 100),
        "p95": np.clip(p + 20, 0, 100),
    }
    yrs = np.arange(Y)
    s["series"] = np.clip(
        p[:, :, :1, :].transpose(0, 1, 3, 2) + 5 - 0.12 * yrs + rng.normal(0, 12, (T, D, nr, Y)),
        0, 100,
    )  # fmt: skip
    s["trend"] = np.full((T, D, nr), -0.9)
    s["trend_p"] = np.full((T, D, nr), 0.04)
    area = np.array([max(r.get("area_hint", 1000.0), 1.0) for r in regions])
    s["area_km2"] = area
    s["land_km2"] = area * 0.97
    s["cells"] = area / 85.0
    s["glacier_pct"] = np.zeros(nr)
    s["elev_min"], s["elev_mean"], s["elev_max"] = (np.full(nr, 200.0), np.full(nr, 600.0),
                                                     np.full(nr, 1800.0))  # fmt: skip
    s["n_places"] = np.full(nr, 3)
    s["places_pop"] = np.full(nr, 250000)
    s["has_land"] = np.ones(nr, bool)
    s["has_usable"] = np.ones(nr, bool)
    s["fallback"] = np.zeros(nr, bool)
    s["source"] = np.array([r["source"] for r in regions])
    for k, r in enumerate(regions):
        if r["country"] == "CNM":  # show the flags: a buffer zone with no land cell of its own
            s["has_land"][k] = False
            s["has_usable"][k] = False
            s["cells"][k] = 0
            s["p"][..., k] = np.nan
            s["p_pop"][..., k] = np.nan
            s["series"][..., k, :] = np.nan
            s["trend"][..., k] = np.nan
            s["trend_p"][..., k] = np.nan
    g = len(info["gwls"])
    now = s["p"][0, 0, info["w_now"]]
    drop = np.array([0.88, 0.78, 0.6][:g])[:, None]
    s["proj_baseline"] = now
    s["proj_p50"] = now[None, :] * drop
    s["proj_p10"] = s["proj_p50"] * 0.7
    s["proj_p90"] = np.minimum(s["proj_p50"] * 1.2, 100)
    s["proj_change"] = s["proj_p50"] - now[None, :]
    s["proj_agree"] = np.ones((g, nr), bool)
    s["proj_n"] = np.full((g, nr), 19)
    s["proj_p50_pop"] = s["proj_p50"] * 0.95
    return s


def make_sample(ext_dir: Path, cfg, out: Path, countries=SAMPLE_COUNTRIES) -> dict:
    import shapely

    from .boundaries import load_regions
    from .build import export_info
    from .export import write_web
    from .geometry import approx_km2, boundaries_geojson, simplify_regions, wrapped_bounds

    a1 = cfg.raw.get("admin1") or {}
    allr = load_regions(ext_dir, a1)
    regions = [r for r in allr if r["country"] in countries]
    geoms = simplify_regions(regions, 0.05, 50.0)
    gj = boundaries_geojson(regions, geoms, 3)
    meta = []
    for r in regions:
        p = shapely.point_on_surface(r["geom"])
        meta.append({
            **{k: r[k] for k in ("id", "name", "name_local", "type", "country", "country_name",
                                 "adm0_a3", "source", "n_features")},
            "lon": p.x, "lat": p.y, "bbox": wrapped_bounds(r["geom"]),
            "area_hint": approx_km2(r["geom"]),
        })  # fmt: skip
    windows = [w.id for w in cfg.windows()]
    a, b = cfg.change_pair
    smeta = {
        "thresholds": [t["id"] for t in cfg.thresholds], "definitions": cfg.definition_ids,
        "windows": windows, "years": cfg.years,
        "projections": {"gwls": [1.5, 2.0, 3.0], "models": ["FAKE-MODEL-1", "FAKE-MODEL-2"],
                        "definition": cfg.default_definition, "baseline_window": b},
    }  # fmt: skip
    info = export_info(cfg, smeta)
    info.update({"data_version": "sample", "build_hash": "sample", "built": "2026-11-19T00:00:00Z"})
    s = fake_stats(meta, info)
    for m in meta:
        m.pop("area_hint")
    return write_web(out, meta, s, gj, info)
