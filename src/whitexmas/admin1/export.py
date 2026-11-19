"""Web files for states and provinces (contract v1.6, format ``wx-admin1-v1``).

Writes into ``<out>/admin1/``:

- ``index.json``: one row per region with the headline numbers (default threshold and
  definition), for colouring the map, ranking and search.
- ``boundaries.json``: simplified outlines (GeoJSON), feature ``id`` = row in ``index.json``.
- ``c/<country>.json``: everything for the regions of one country (every threshold,
  definition and window, the yearly series, the spread inside the region, projections),
  loaded when a region of that country is opened.

The schema is documented in ``docs/admin1.md``. NaN never reaches the JSON: a value that cannot
be computed is ``null`` and the region's ``flags`` say why.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

FORMAT = "wx-admin1-v1"
CONTRACT = "1.6"
FLAG_DOCS = {
    "admin0": "no admin-1 subdivision in Natural Earth: the region is the whole admin-0 unit",
    "low_res": "fewer than {low_res_cells} land cells (0.1°): the value rests on very few cells",
    "nearest_cell": "no land cell inside: the value of the nearest land cell (within 2 cells)",
    "no_land": "no land cell inside or nearby: no values",
    "all_glacier": "every land cell is glacier: no values (glaciers are left out)",
}


def _r(v, nd: int = 1):
    if v is None:
        return None
    v = float(v)
    if not np.isfinite(v):
        return None
    out = round(v, nd)
    return int(out) if nd == 0 else out


def _rl(a, nd: int = 1) -> list:
    return [_r(v, nd) for v in np.asarray(a).ravel()]


def region_flags(s: dict, k: int, low_res_cells: float) -> list[str]:
    f = []
    if s["source"][k] == "ne_admin0":
        f.append("admin0")
    if s["fallback"][k]:
        f.append("nearest_cell")
    elif not s["has_land"][k]:
        f.append("no_land")
    elif not s["has_usable"][k]:
        f.append("all_glacier")
    if (s["has_usable"][k] or s["fallback"][k]) and s["cells"][k] < low_res_cells:
        f.append("low_res")
    return f


def header(info: dict) -> dict:
    return {
        "format": FORMAT,
        "contract": CONTRACT,
        "data_version": info["data_version"],
        "built": info["built"],
        "build_hash": info["build_hash"],
    }


def build_index(regions: list[dict], s: dict, info: dict) -> dict:
    """index.json: headline numbers for the default threshold and definition."""
    t0, d0 = 0, info["definitions"].index(info["default_definition"])
    wid = info["windows"]
    wf, wt, wn = (wid.index(info["window_ids"][k]) for k in ("full", "then", "now"))
    raw = [k for k, t in enumerate(info["thresholds"]) if k != t0]
    gwls = info.get("gwls") or []
    fields = ["id", "name", "country", "lon", "lat", "area_km2", "flags",
              "p_full", "p_then", "p_now", "change", "trend", "trend_p", "p_now_pop"]  # fmt: skip
    for k in raw:
        fields += [f"p_then_{info['thresholds'][k]}", f"p_now_{info['thresholds'][k]}"]
    fields += [f"p_gwl{g:.1f}" for g in gwls]
    rows = []
    for k, r in enumerate(regions):
        p = s["p"][t0, d0, :, k]
        row = [
            r["id"], r["name"], r["country"], _r(r["lon"], 3), _r(r["lat"], 3),
            _r(s["area_km2"][k], 0), region_flags(s, k, info["low_res_cells"]),
            _r(p[wf]), _r(p[wt]), _r(p[wn]), _r(p[wn] - p[wt]),
            _r(s["trend"][t0, d0, k], 2), _r(s["trend_p"][t0, d0, k], 4),
            _r(s["p_pop"][t0, d0, wn, k]),
        ]  # fmt: skip
        for t in raw:
            row += [_r(s["p"][t, d0, wt, k]), _r(s["p"][t, d0, wn, k])]
        if gwls:
            row += _rl(s["proj_p50"][:, k])
        rows.append(row)
    countries = {}
    for r in regions:
        c = countries.setdefault(r["country"], {"name": r["country_name"], "regions": 0})
        c["regions"] += 1
    return {
        **header(info),
        "threshold": info["thresholds"][t0],
        "definition": info["default_definition"],
        "windows": {"p_full": wid[wf], "p_then": wid[wt], "p_now": wid[wn]},
        "trend_alpha": info["trend_alpha"],
        "headline": "area",
        "fields": fields,
        "rows": rows,
        "countries": dict(sorted(countries.items())),
        "flags": {k: v.format(**info) for k, v in FLAG_DOCS.items()},
        "attribution": "Borders: Natural Earth (public domain). Places: GeoNames (CC BY 4.0).",
    }


def build_country(country: str, members: list[int], regions: list[dict], s: dict, info: dict):
    """c/<country>.json: full statistics for the regions of one country."""
    T, D = info["thresholds"], info["definitions"]
    gwls = info.get("gwls") or []
    out_regions = []
    for k in members:
        r = regions[k]
        stats: dict = {}
        for ti, t in enumerate(T):
            stats[t] = {}
            for di, d in enumerate(D):
                p = s["p"][ti, di, :, k]
                pp = s["p_pop"][ti, di, :, k]
                wt, wn = info["w_then"], info["w_now"]
                stats[t][d] = {
                    "p": _rl(p),
                    "p_pop": _rl(pp),
                    "share50": _rl(s["share50"][ti, di, :, k]),
                    "p5": _rl(s["p5"][ti, di, :, k]),
                    "p95": _rl(s["p95"][ti, di, :, k]),
                    "change": _r(p[wn] - p[wt]),
                    "change_pop": _r(pp[wn] - pp[wt]),
                    "trend": _r(s["trend"][ti, di, k], 2),
                    "trend_p": _r(s["trend_p"][ti, di, k], 4),
                    "series": _rl(s["series"][ti, di, k]),
                }
        proj = None
        if gwls and np.isfinite(s["proj_baseline"][k]):
            proj = {
                "baseline": _r(s["proj_baseline"][k]),
                "p10": _rl(s["proj_p10"][:, k]),
                "p50": _rl(s["proj_p50"][:, k]),
                "p90": _rl(s["proj_p90"][:, k]),
                "change": _rl(s["proj_change"][:, k]),
                "agree": [bool(v) for v in s["proj_agree"][:, k]],
                "n_models": int(s["proj_n"][:, k].max()),
                "p50_pop": _rl(s["proj_p50_pop"][:, k]),
            }
        out_regions.append({
            "id": r["id"], "name": r["name"], "name_local": r["name_local"], "type": r["type"],
            "flags": region_flags(s, k, info["low_res_cells"]),
            "lon": _r(r["lon"], 3), "lat": _r(r["lat"], 3), "bbox": _rl(r["bbox"], 2),
            "area_km2": _r(s["area_km2"][k], 0), "land_km2": _r(s["land_km2"][k], 0),
            "cells": _r(s["cells"][k], 1), "glacier_pct": _r(s["glacier_pct"][k], 1),
            "elev_m": [_r(s["elev_min"][k], 0), _r(s["elev_mean"][k], 0),
                       _r(s["elev_max"][k], 0)],
            "places": int(s["n_places"][k]), "places_pop": int(s["places_pop"][k]),
            "stats": stats, "proj": proj,
        })  # fmt: skip
    return {
        **header(info),
        "country": country,
        "country_name": regions[members[0]]["country_name"],
        "years": [info["years"][0], info["years"][-1]],
        "thresholds": T,
        "definitions": D,
        "windows": info["windows"],
        "windows_then_now": [info["windows"][info["w_then"]], info["windows"][info["w_now"]]],
        "trend_alpha": info["trend_alpha"],
        "spread_share_pct": info["spread_share_pct"],
        "projections": {
            "threshold": T[0],
            "definition": info["proj_definition"],
            "gwls": gwls,
            "baseline_window": info["proj_baseline_window"],
            "models": info["proj_models"],
        }
        if gwls
        else None,  # fmt: skip
        "regions": out_regions,
    }


def write_json(path: Path, obj) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    path.write_text(data, encoding="utf-8")
    return path.stat().st_size


def write_web(out: Path, regions: list[dict], s: dict, boundaries: dict, info: dict) -> dict:
    """Write ``<out>/admin1/`` (replacing it) and return {relative path: bytes}."""
    root = Path(out) / "admin1"
    tmp = root.with_name("admin1.tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    sizes = {}
    sizes["admin1/index.json"] = write_json(tmp / "index.json", build_index(regions, s, info))
    sizes["admin1/boundaries.json"] = write_json(tmp / "boundaries.json", boundaries)
    by_country: dict[str, list[int]] = {}
    for k, r in enumerate(regions):
        by_country.setdefault(r["country"], []).append(k)
    for c, members in sorted(by_country.items()):
        sizes[f"admin1/c/{c}.json"] = write_json(
            tmp / "c" / f"{c}.json", build_country(c, members, regions, s, info)
        )
    if root.exists():
        shutil.rmtree(root)
    tmp.rename(root)
    return sizes


def manifest_block(info: dict) -> dict:
    """The ``admin1`` block of manifest.json (contract v1.6)."""
    return {
        "available": True,
        "format": FORMAT,
        "index": "admin1/index.json",
        "boundaries": "admin1/boundaries.json",
        "country": "admin1/c/{country}.json",
        "data_version": info["data_version"],
        "built": info["built"],
        "build_hash": info["build_hash"],
    }


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def stage(products_dir: Path, web_out: Path) -> dict | None:
    """Copy a complete admin-1 build from ``products_dir`` into ``web_out/admin1`` and return
    the manifest block; None (nothing copied) when the build is missing or incomplete."""
    frag_path = products_dir / "manifest_fragment.json"
    src = products_dir / "web" / "admin1"
    if not frag_path.exists() or not (src / "index.json").exists():
        return None
    frag = json.loads(frag_path.read_text(encoding="utf-8"))
    files = frag.get("files") or {}
    for rel, meta in files.items():
        p = products_dir / "web" / rel
        if not p.exists() or p.stat().st_size != meta["bytes"]:
            log.warning("admin1: %s missing or changed; not staging admin1", rel)
            return None
    dst = Path(web_out) / "admin1"
    if dst.exists():
        shutil.rmtree(dst)
    for rel in files:
        target = Path(web_out) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(products_dir / "web" / rel, target)
    log.info("admin1: staged %d files into %s", len(files), dst)
    return frag["admin1"]
