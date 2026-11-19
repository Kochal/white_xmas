"""Sanity section for states and provinces: well-known regions against their main city.

For each region: the area-weighted and population-weighted 1996-2025 probability, the spread
(p5-p95, share >= 50 %), the trend, and the value of the main city's cell (the same rule as
places.json and the city table). Expectations: the city lies inside the region's p5-p95; the
population-weighted value is near the cities' values; a mountain region's area value is above
its valley city's, a flat region's close to it.
"""

from __future__ import annotations

import html
import json

import numpy as np

# (region id, region, city, lat, lon)
REGIONS = [
    ("DE-BY", "Bavaria", "Munich", 48.137, 11.575),
    ("US-MN", "Minnesota", "Minneapolis", 44.978, -93.265),
    ("CA-ON", "Ontario", "Toronto", 43.653, -79.383),
    ("JP-01", "Hokkaido", "Sapporo", 43.062, 141.354),
    ("AT-7", "Tyrol", "Innsbruck", 47.269, 11.404),
    ("FI-10", "Lapland", "Rovaniemi", 66.503, 25.729),
    ("IT-25", "Lombardy", "Milan", 45.464, 9.190),
]


def admin1_section(cfg, paths, inds: dict) -> dict | None:
    """Rows for the sanity report, or None when ``whitexmas admin1 stats`` has not run."""
    from ..export.places import cell_index, nearest_valid
    from .build import Admin1Paths, load_stats

    ap = Admin1Paths(paths)
    if not ap.stats.exists() or not ap.regions.exists():
        return None
    regions = json.loads(ap.regions.read_text(encoding="utf-8"))
    s, meta = load_stats(ap)
    pos = {r["id"]: k for k, r in enumerate(regions)}
    W = meta["windows"]
    a, b = cfg.change_pair
    wn, wt, wf = W.index(b), W.index(a), W.index(cfg.full_window().id)
    T = meta["thresholds"]
    d0 = meta["definitions"].index(cfg.default_definition)
    ind0 = inds[T[0]]
    land = np.asarray(ind0["land"][:], dtype=bool)
    rows = []
    for rid, label, city, lat, lon in REGIONS:
        k = pos.get(rid)
        if k is None:
            rows.append({"id": rid, "region": label, "missing": True})
            continue
        j, i = nearest_valid(land, *cell_index(lat, lon)) or cell_index(lat, lon)
        row = {
            "id": rid, "region": label, "name": regions[k]["name"], "city": city,
            "cells": float(s["cells"][k]), "elev_m": [float(s["elev_min"][k]),
            float(s["elev_mean"][k]), float(s["elev_max"][k])], "values": {},
        }  # fmt: skip
        for ti, t in enumerate(T):
            p_city = float(inds[t]["probability"][d0, wn, j, i])
            p5, p95 = float(s["p5"][ti, d0, wn, k]), float(s["p95"][ti, d0, wn, k])
            row["values"][t] = {
                "p_full": float(s["p"][ti, d0, wf, k]),
                "p_then": float(s["p"][ti, d0, wt, k]),
                "p_now": float(s["p"][ti, d0, wn, k]),
                "p_now_pop": float(s["p_pop"][ti, d0, wn, k]),
                "p5": p5, "p95": p95,
                "share50": float(s["share50"][ti, d0, wn, k]),
                "trend": float(s["trend"][ti, d0, k]),
                "trend_p": float(s["trend_p"][ti, d0, k]),
                "city_p_now": p_city,
                "city_in_p5_p95": bool(p5 - 1e-6 <= p_city <= p95 + 1e-6),
            }  # fmt: skip
        if "proj_p50" in s:
            row["proj_p50"] = [float(v) for v in s["proj_p50"][:, k]]
            row["proj_baseline"] = float(s["proj_baseline"][k])
        rows.append(row)
    return {
        "definition": cfg.default_definition,
        "window": b,
        "thresholds": T,
        "gwls": (meta.get("projections") or {}).get("gwls") or [],
        "rows": rows,
        "n_regions": len(regions),
    }


def _f(v, nd=1) -> str:
    return "–" if v is None or not np.isfinite(v) else f"{v:.{nd}f}"


def admin1_html(sec: dict) -> str:
    out = [
        f"<h2>States and provinces: well-known regions ({sec['definition']}, {sec['window']})</h2>"
        f"<p>{sec['n_regions']:,} regions (docs/admin1.md). Area = area-weighted mean over the "
        "region's land cells (glaciers excluded); pop = weighted by GeoNames places; p5–p95 = "
        "spread of the cell values (area-weighted); city = the main city's cell, as in the city "
        "table. Expect the city inside p5–p95.</p>"
    ]
    for t in sec["thresholds"]:
        rows = []
        for r in sec["rows"]:
            if r.get("missing"):
                rows.append(
                    f"<tr><td>{html.escape(r['region'])}</td><td colspan=10>missing</td></tr>"
                )
                continue
            v = r["values"][t]
            ok = "yes" if v["city_in_p5_p95"] else "<b>no</b>"
            rows.append(
                f"<tr><td>{html.escape(r['region'])} ({r['id']})</td><td>{_f(r['cells'], 0)}</td>"
                f"<td>{_f(r['elev_m'][0], 0)}–{_f(r['elev_m'][2], 0)}</td>"
                f"<td>{_f(v['p_then'])}</td><td>{_f(v['p_now'])}</td><td>{_f(v['p_now_pop'])}</td>"
                f"<td>{_f(v['p5'])}–{_f(v['p95'])}</td><td>{_f(v['share50'])}</td>"
                f"<td>{_f(v['trend'], 2)} (p {_f(v['trend_p'], 3)})</td>"
                f"<td>{html.escape(r['city'])} {_f(v['city_p_now'])}</td><td>{ok}</td></tr>"
            )
        out.append(
            f"<h3>Threshold {html.escape(t)}</h3><table><tr><th>region</th><th>cells</th>"
            "<th>elevation m</th><th>then</th><th>now (area)</th><th>now (pop)</th><th>p5–p95</th>"
            "<th>share ≥ 50 %</th><th>trend pp/dec</th><th>city now</th><th>city in p5–p95</th>"
            f"</tr>{''.join(rows)}</table>"
        )
    if sec["gwls"]:
        rows = "".join(
            f"<tr><td>{html.escape(r['region'])}</td><td>{_f(r.get('proj_baseline'))}</td>"
            + "".join(f"<td>{_f(p)}</td>" for p in r.get("proj_p50", []))
            + "</tr>"
            for r in sec["rows"]
            if not r.get("missing")
        )
        heads = "".join(f"<th>+{g} °C</th>" for g in sec["gwls"])
        out.append(
            "<h3>Projections (median of the models' regional means, calibrated)</h3>"
            f"<table><tr><th>region</th><th>today</th>{heads}</tr>{rows}</table>"
        )
    return "\n".join(out)
