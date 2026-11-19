"""Sensitivity of the per-model log-odds change to the SWE threshold and to day pooling.

Run inside the project env::

    uv run python scripts/projections/sensitivity.py [--gwl 2.0]

For every model and setting it computes the Christmas-Day log-odds change from the 1995-2014
baseline to the model's warming-level window, and summarises it over "transition" land cells
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
from whitexmas.projections.changes import counts_for_window, model_land_pct
from whitexmas.projections.cmip6 import load_plan
from whitexmas.projections.ensemble import nan_percentiles
from whitexmas.projections.regrid import bilinear, fill_nearest
from whitexmas.projections.settings import ProjPaths, ProjSettings
from whitexmas.projections.transfer import logodds_change

SETTINGS = [(2.5, 0), (2.5, 3), (2.5, 7), (1.0, 7), (5.0, 7)]
GRID_LAT = np.arange(25.0, 75.01, 1.0)
GRID_LON = np.arange(-180.0, 180.0, 1.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gwl", type=float, default=2.0)
    ap.add_argument("--model", action="append")
    args = ap.parse_args()
    pp = ProjPaths.from_data(DataPaths.from_env())
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
                kb, nb, lat, lon = counts_for_window(pp.cmip6, m, "historical", 1995, 2014, s)
                kf, nf, *_ = counts_for_window(
                    pp.cmip6, m, win["experiment"], win["start"], win["end"], s
                )
            except FileNotFoundError:
                continue
            pct = model_land_pct(pp, m, lat, lon, None)
            land = np.isfinite(kb[0]) & (nb[0] > 0)
            if pct is not None:
                land &= pct >= 50
            d = np.where(land, logodds_change(kb[0], nb[0], kf[0], nf[0]), np.nan)
            fb = np.where(land, kb[0] / np.maximum(nb[0], 1), np.nan)
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
