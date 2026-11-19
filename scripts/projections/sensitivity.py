"""Sensitivity of the per-model log-odds change to the SWE threshold and to day pooling.

Run inside the project env::

    uv run python scripts/projections/sensitivity.py [--gwl 2.0]

For every model and setting it computes the Christmas-Day log-odds change from the model
baseline to the model's warming-level window, with exactly the production computation
(``changes.window_change``: land mask included), and summarises it over "transition" land cells
(Northern Hemisphere 25-75 °N, baseline frequency between 10 and 90 %), cos-lat weighted:

- ``median_delta``: the typical change (should hardly depend on the threshold)
- ``spread``: the 10-90 % range of the change across models per cell, averaged over cells; a
  smaller spread with pooling means less sampling noise
- ``noise``: the cell-to-cell roughness of each model's change (mean absolute difference between
  neighbouring cells), a direct sampling-noise proxy on smooth large-scale fields

Writes ``interim/projections/validation/sensitivity.json``.
"""

from __future__ import annotations

import argparse
import json

import numpy as np

from whitexmas.paths import DataPaths
from whitexmas.projections.baseline import era5_window_frequency
from whitexmas.projections.changes import window_change
from whitexmas.projections.cmip6 import load_plan
from whitexmas.projections.ensemble import nan_percentiles
from whitexmas.projections.regrid import bilinear, fill_nearest
from whitexmas.projections.settings import ProjPaths, ProjSettings

SETTINGS = [(2.5, 0), (2.5, 3), (2.5, 7), (1.0, 7), (5.0, 7)]
GRID_LAT = np.arange(25.0, 75.01, 1.0)
GRID_LON = np.arange(-180.0, 180.0, 1.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gwl", type=float, default=2.0)
    ap.add_argument("--model", action="append")
    args = ap.parse_args()
    paths = DataPaths.from_env()
    pp = ProjPaths.from_data(paths)
    # ERA5-Land land mask, only for models without a usable sftlf (NESM3)
    f = era5_window_frequency(paths, "christmas_day", 1961, 1990)
    era5_land = None if f is None else np.isfinite(f)
    plan = load_plan(pp.cmip6)["models"]
    models = args.model or sorted(plan)
    w = np.cos(np.deg2rad(GRID_LAT))[:, None] * np.ones((1, len(GRID_LON)))
    out = {"gwl": args.gwl, "settings": [], "models": models}
    for thr, pool in SETTINGS:
        s = ProjSettings(threshold_kg_m2=thr, pool_days=pool, definitions=("christmas_day",))
        deltas, rough, base = [], [], []
        for m in models:
            win = plan[m]["windows"].get(str(args.gwl))
            if not win:
                continue
            try:
                ch = window_change(
                    pp,
                    m,
                    (s.baseline_experiment, *s.baseline),
                    (win["experiment"], win["start"], win["end"]),
                    s,
                    era5_land=era5_land,
                )
            except FileNotFoundError:
                continue
            lat, lon, d = ch["lat"], ch["lon"], ch["delta"][0]
            fb = np.where(ch["land"], ch["kb"][0] / np.maximum(ch["nb"][0], 1), np.nan)
            r = np.nanmean(np.abs(np.diff(d, axis=1)))
            rough.append(float(r))
            deltas.append(bilinear(fill_nearest(d), lat, lon, GRID_LAT, GRID_LON))
            base.append(bilinear(fill_nearest(fb), lat, lon, GRID_LAT, GRID_LON))
        dl = np.stack(deltas)
        fb = np.nanmedian(np.stack(base), axis=0)
        trans = (fb > 0.1) & (fb < 0.9)
        q = nan_percentiles(dl.reshape(len(dl), -1), (10, 50, 90)).reshape(3, *fb.shape)
        ww = w[trans]
        row = {
            "threshold_kg_m2": thr,
            "pool_days": pool,
            "n_models": len(dl),
            "median_delta": round(float(np.average(q[1][trans], weights=ww)), 3),
            "spread_p10_p90": round(float(np.average((q[2] - q[0])[trans], weights=ww)), 3),
            "noise_neighbour_diff": round(float(np.mean(rough)), 3),
        }
        out["settings"].append(row)
        print(json.dumps(row), flush=True)
    pp.validation.mkdir(parents=True, exist_ok=True)
    (pp.validation / "sensitivity.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
