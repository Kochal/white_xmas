"""Sanity report: city values and a comparison with the legacy GeoTIFF.

The legacy map used the *hourly maximum* snow depth over Dec 24-26 (any hour >= 1 cm); the new
``any_day`` rule uses *daily means*, so the new probabilities should be lower or equal. We report
correlation and bias on land cells, not an exact match.
"""

from __future__ import annotations

import html
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .config import Config
from .definitions import white
from .indicators import probability
from .paths import DataPaths

log = logging.getLogger(__name__)

# The legacy map was built with a fixed 1 cm threshold (on hourly maxima), so the comparison
# always uses 1 cm, whatever threshold the site uses.
LEGACY_THRESHOLD_CM = 1

CITIES = [
    ("Munich", 48.137, 11.575),
    ("Oslo", 59.913, 10.739),
    ("Chicago", 41.878, -87.630),
    ("Toronto", 43.653, -79.383),
    ("Moscow", 55.756, 37.617),
    ("Sapporo", 43.062, 141.354),
    ("Zurich", 47.377, 8.540),
    ("London", 51.507, -0.128),
]


def _cell(lat: float, lon: float) -> tuple[int, int]:
    return int(round((90 - lat) / 0.1)), int(round((lon + 180) / 0.1)) % 3600


def compare_legacy(new: np.ndarray, legacy: np.ndarray, land: np.ndarray, glacier: np.ndarray):
    """Stats over cells that are land in the new data, finite in both, optionally non-glacier."""
    out = {}
    for name, mask in [("land", land), ("land_no_glacier", land & ~glacier)]:
        ok = mask & np.isfinite(new) & np.isfinite(legacy)
        a, b = new[ok].astype("float64"), legacy[ok].astype("float64")
        d = a - b
        out[name] = {
            "cells": int(ok.sum()),
            "pearson_r": float(np.corrcoef(a, b)[0, 1]) if ok.sum() > 2 else float("nan"),
            "bias_pp": float(d.mean()),
            "mean_abs_diff_pp": float(np.abs(d).mean()),
            "median_diff_pp": float(np.median(d)),
            "share_new_le_legacy": float((a <= b + 1e-6).mean()),
            "share_within_5pp": float((np.abs(d) <= 5).mean()),
            "mean_new": float(a.mean()),
            "mean_legacy": float(b.mean()),
        }
    return out


def build_report(cfg: Config, paths: DataPaths, legacy_tif: Path | None, out_dir: Path) -> dict:
    import zarr

    inds = {t["id"]: zarr.open_group(str(paths.indicators_for(t)), mode="r")
            for t in cfg.thresholds}  # fmt: skip
    ind = inds[cfg.default_threshold["id"]]
    cube = zarr.open_group(str(paths.cube), mode="r")
    years = np.asarray(cube["year"][:])
    wins = cfg.windows()
    wid = [w.id for w in wins]
    defs = cfg.definition_ids
    a, b = cfg.change_pair
    full = cfg.full_window().id

    cities = []
    for name, lat, lon in CITIES:
        j, i = _cell(lat, lon)
        row = {"name": name, "lat": lat, "lon": lon, "cell": [j, i],
               "glacier": bool(ind["glacier"][j, i]), "values": {}}  # fmt: skip
        for tid, z in inds.items():
            row["values"][tid] = {}
            for di, d in enumerate(defs):
                p = z["probability"][di, :, j, i]
                row["values"][tid][d] = {
                    "p_full": float(p[wid.index(full)]),
                    "p_then": float(p[wid.index(a)]),
                    "p_now": float(p[wid.index(b)]),
                    "change": float(z["change"][di, j, i]),
                    "trend": float(z["trend"][di, j, i]),
                    "trend_p": float(z["trend_p"][di, j, i]),
                    "decades": {
                        w.id: float(p[k]) for k, w in enumerate(wins) if w.kind == "decade"
                    },
                }
        series = cube["snow_depth_cm"][:, 1, j, i]
        row["mean_depth_dec25_cm"] = float(series[series >= 0].mean())
        cities.append(row)

    report: dict = {
        "built": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cities": cities,
        "windows": {"full": full, "then": a, "now": b},
        "threshold_cm": cfg.threshold_cm,
        "station_equivalent_cm": cfg.station_equivalent_cm,
        "thresholds": [{k: t[k] for k in ("id", "cm", "default", "label")} for t in cfg.thresholds],
        "legacy_threshold_cm": LEGACY_THRESHOLD_CM,
    }
    st = paths.products / "sanity" / "stations.json"
    if st.exists():
        sres = json.loads(st.read_text())
        cal = sres["calibration"]
        report["stations"] = {
            "n_stations": len(sres["stations"]),
            "n_calibration": cal["n_calibration"],
            "best_cm": cal["best_cm"],
            "stats": {int(k): v for k, v in cal["stats"].items()},
        }

    if legacy_tif and legacy_tif.exists():
        import rasterio

        with rasterio.open(legacy_tif) as src:
            legacy = src.read(1).astype("float32")
            t = src.transform
        if abs(t.c + 180.05) > 1e-6 or abs(t.f - 90.05) > 1e-6:
            raise ValueError(f"unexpected legacy grid {t}")
        rows = legacy.shape[0]
        sel = (years >= 1980) & (years <= 2024)
        block = cube["snow_depth_cm"][sel, :, :rows, :]
        w = white(block, "any_day", LEGACY_THRESHOLD_CM)
        new, _ = probability(w, min_valid=int(np.ceil(0.8 * sel.sum())))
        land = ind["land"][:rows]
        glac = ind["glacier"][:rows]
        stats = compare_legacy(new, legacy, land, glac)
        report["legacy"] = {"file": legacy_tif.name, "window": "1980_2024",
                            "definition": "any_day", "stats": stats}  # fmt: skip
        legacy_ocean = (~land) & (legacy == 0)
        report["legacy"]["ocean_cells_shown_as_0pct_in_legacy"] = int(legacy_ocean.sum())
        for c in cities:
            j, i = c["cell"]
            if j < rows:
                c["legacy_any_day_1980_2024"] = float(legacy[j, i])
                c["new_any_day_1980_2024"] = float(new[j, i])
        _diff_png(new, legacy, land, out_dir / "legacy_diff.png")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "sanity_report.json").write_text(json.dumps(report, indent=1, allow_nan=True))
    (out_dir / "sanity_report.html").write_text(_html(report, defs), encoding="utf-8")
    log.info("sanity report written to %s", out_dir)
    return report


def _diff_png(new, legacy, land, path: Path) -> None:
    from PIL import Image

    from .export.colors import apply_colormap

    d = np.where(land, new - legacy, np.nan)
    rgba = apply_colormap(np.clip(d, -50, 50), "change")
    rgba[~land] = (40, 40, 60, 255)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba[::2, ::2]).save(path)


def _fmt(v, nd=1) -> str:
    return "–" if v is None or not np.isfinite(v) else f"{v:.{nd}f}"


def _html(r: dict, defs: list[str]) -> str:
    w = r["windows"]
    eq = (
        f" (calibrated to ≈ {r['station_equivalent_cm']} cm at weather stations)"
        if r.get("station_equivalent_cm") is not None
        else ""
    )
    city_tables = ""
    for t in r["thresholds"]:
        rows = []
        for c in r["cities"]:
            for d in defs:
                v = c["values"][t["id"]][d]
                rows.append(
                    f"<tr><td>{html.escape(c['name'])}</td><td>{d}</td>"
                    f"<td>{_fmt(v['p_full'])}</td><td>{_fmt(v['p_then'])}</td>"
                    f"<td>{_fmt(v['p_now'])}</td><td>{_fmt(v['change'])}</td>"
                    f"<td>{_fmt(v['trend'])}</td><td>{_fmt(v['trend_p'], 3)}</td></tr>"
                )
        city_tables += (
            f"<h2>Cities: {html.escape(t['label'])} (≥ {t['cm']} cm"
            f"{', default' if t.get('default') else ''})</h2>"
            f"<table><tr><th>city</th><th>definition</th><th>{w['full']}</th>"
            f"<th>{w['then']}</th><th>{w['now']}</th><th>change</th><th>trend</th><th>p</th>"
            f"</tr>{''.join(rows)}</table>"
        )
    stations = ""
    if "stations" in r:
        s_ = r["stations"]
        srows = "".join(
            f"<tr><td>≥ {k} cm</td><td>{v['bias_pp']:+.1f}</td><td>{v['mae_pp']:.1f}</td>"
            f"<td>{v['agree_pct']:.1f}</td></tr>"
            for k, v in sorted(s_["stats"].items())
        )
        stations = (
            f"<h2>Station check</h2><p>{s_['n_stations']} GHCN-Daily stations, "
            f"{s_['n_calibration']} after quality filters (see snow_variable_check.html). Best "
            f"whole-cm threshold: {s_['best_cm']} cm.</p><table><tr><th>ERA5-Land rule</th>"
            f"<th>mean bias (pp)</th><th>MAE (pp)</th><th>agreement (%)</th></tr>{srows}</table>"
        )
    leg = ""
    if "legacy" in r:
        s = r["legacy"]["stats"]
        lr = "".join(
            f"<tr><td>{k}</td><td>{v['cells']:,}</td><td>{v['pearson_r']:.3f}</td>"
            f"<td>{v['bias_pp']:+.1f}</td><td>{v['mean_abs_diff_pp']:.1f}</td>"
            f"<td>{v['share_new_le_legacy'] * 100:.1f}%</td><td>{v['mean_new']:.1f}</td>"
            f"<td>{v['mean_legacy']:.1f}</td></tr>"
            for k, v in s.items()
        )
        cl = "".join(
            f"<tr><td>{html.escape(c['name'])}</td><td>{_fmt(c.get('new_any_day_1980_2024'))}</td>"
            f"<td>{_fmt(c.get('legacy_any_day_1980_2024'))}</td></tr>"
            for c in r["cities"]
        )
        leg = f"""<h2>Legacy comparison: any_day, 1980–2024, land cells</h2>
<p>Both sides use {r["legacy_threshold_cm"]} cm, whatever the threshold in use: new =
daily-mean snow depth ≥ {r["legacy_threshold_cm"]} cm on any of Dec 24–26; legacy = hourly
maximum ≥ {r["legacy_threshold_cm"]} cm (and oceans counted as 0 %). Expect new ≤ legacy.</p>
<table><tr><th>cells</th><th>n</th><th>Pearson r</th><th>bias (new − legacy, pp)</th>
<th>mean |diff|</th><th>new ≤ legacy</th><th>mean new</th><th>mean legacy</th></tr>{lr}</table>
<p>Ocean cells shown as 0 % in the legacy map:
{r["legacy"]["ocean_cells_shown_as_0pct_in_legacy"]:,}.</p>
<table><tr><th>city</th><th>new %</th><th>legacy %</th></tr>{cl}</table>
<p><img src="legacy_diff.png" alt="new minus legacy" style="max-width:100%"></p>"""
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Sanity report</title>
<style>body{{font:14px system-ui;margin:2em;max-width:1100px}}table{{border-collapse:collapse;
margin:1em 0}}td,th{{border:1px solid #ccc;padding:3px 8px;text-align:right}}
td:first-child{{text-align:left}}</style></head><body>
<h1>White Christmas: sanity report</h1><p>Built {r["built"]}. <b>Default threshold:
daily-mean snow depth ≥ {r["threshold_cm"]} cm</b>{eq}; thresholds offered:
{", ".join(f"{t['id']} ≥ {t['cm']} cm" for t in r["thresholds"])}. Probabilities in %, change in
pp ({w["then"]} → {w["now"]}), trend in pp/decade over {w["full"]} with Mann-Kendall p.</p>
{city_tables}
{stations}
{leg}</body></html>"""
