"""Export step: web data per the web data contract, COGs and the data bundle.

Writes into ``web_out`` (normally ``web/static/data``):
manifest.json, tiles/<layer>.pmtiles, points/index.json + points/<tx>_<ty>.bin.gz,
places.json, regions.json. COGs go to ``$WHITEXMAS_DATA/products/cog/`` and the bundle
``whitexmas-web-data-<data_version>.tar.gz`` to ``$WHITEXMAS_DATA/products/``.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tarfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from ..config import Config
from ..paths import REPO_ROOT, DataPaths
from .colors import COLORMAPS

try:  # the projections package lives on its own branch until the two meet
    from ..projections.export import manifest_fragment
except ModuleNotFoundError as e:  # pragma: no cover - depends on which branch is checked out
    # Only "the projections package is absent" is expected; any other import failure inside it
    # (a missing optional dependency, a bug) must surface instead of silently dropping it.
    if e.name not in ("whitexmas.projections", "whitexmas.projections.export"):
        raise

    def manifest_fragment(paths: DataPaths, web_out: Path | None = None) -> dict | None:
        return None


log = logging.getLogger(__name__)
# Bump with every commit that changes what export writes, so fingerprints invalidate.
# 2: unique region keys, admin alt names filtered, threshold texts, station_equivalent_cm.
# 3: thresholds (contract v1.5): raw layers, p_*_raw in places/regions, per-threshold COGs.
EXPORT_VERSION = 3
SCHEMA_VERSION = 1

ATTRIBUTION = (
    "Contains modified Copernicus Climate Change Service information (ERA5-Land, {year}). "
    "Neither the European Commission nor ECMWF is responsible for any use that may be made "
    "of the Copernicus information or data it contains. Places: GeoNames (CC BY 4.0). "
    "Borders: Natural Earth."
)


# --------------------------------------------------------------------------- layers
def plan_layers(
    cfg: Config,
    decades_for_all: bool = True,
    threshold: dict | None = None,
    minimal: bool = False,
) -> list[dict]:
    """Layer specs of one threshold, in manifest order. ``src`` = (threshold id, array, d, w).

    ``minimal`` (contract v1.5 floor for a non-default threshold): christmas_day probability for
    the full period and the two normals, the change between the normals and the full-period
    trend.
    """
    t = threshold or cfg.default_threshold
    sfx, tid = t["suffix"], t["id"]
    maxz = int(cfg.export.get("tile_maxzoom", 6))
    defs = cfg.definition_ids
    wins = cfg.windows()
    a, b = cfg.change_pair
    full = cfg.full_window().id
    d_keep = [cfg.default_definition] if minimal else defs
    layers: list[dict] = []
    for di, d in enumerate(defs):
        if d not in d_keep:
            continue
        for wi, w in enumerate(wins):
            if minimal and w.kind not in ("full", "normal"):
                continue
            if w.kind == "decade" and not decades_for_all and d != cfg.default_definition:
                continue
            lid = f"prob__{d}__{w.id}{sfx}"
            layers.append({
                "id": lid, "kind": "probability", "definition": d, "window": w.id,
                "threshold": tid, "url": f"tiles/{lid}.pmtiles", "colormap": "probability",
                "minzoom": 0, "maxzoom": maxz,
                "src": (tid, "probability", di, wi),
            })  # fmt: skip
    for di, d in enumerate(defs):
        if d not in d_keep:
            continue
        lid = f"change__{d}__{a}__{b}{sfx}"
        layers.append({
            "id": lid, "kind": "change", "definition": d, "from": a, "to": b, "threshold": tid,
            "url": f"tiles/{lid}.pmtiles", "colormap": "change", "minzoom": 0, "maxzoom": maxz,
            "src": (tid, "change", di, None),
        })  # fmt: skip
    for di, d in enumerate(defs):
        if d not in d_keep:
            continue
        lid = f"trend__{d}__{full}{sfx}"
        layers.append({
            "id": lid, "kind": "trend", "definition": d, "window": full, "threshold": tid,
            "url": f"tiles/{lid}.pmtiles", "colormap": "trend", "hatch_insignificant": True,
            "minzoom": 0, "maxzoom": maxz,
            "src": (tid, "trend", di, None),
        })  # fmt: skip
    return layers


def plan_all_layers(
    cfg: Config, decades_for_all: bool = True, others_minimal: bool = False
) -> list[dict]:
    """Every threshold's layers: the default's full set first, then the other thresholds."""
    layers: list[dict] = []
    for t in cfg.thresholds:
        minimal = not t["default"] and (others_minimal or t["layers"] == "minimal")
        layers += plan_layers(cfg, decades_for_all, t, minimal)
    return layers


def _read_layer(ind_path: str, src: tuple, trend_p_alpha: float):
    import zarr

    z = zarr.open_group(ind_path, mode="r")
    _tid, name, di, wi = src
    values = z[name][di, wi] if wi is not None else z[name][di]
    glacier = z["glacier"][:]
    hatch = None
    if name == "trend":
        p = z["trend_p"][di]
        hatch = ~(p < trend_p_alpha)  # NaN p (no valid trend) also counts as insignificant
    return np.asarray(values), glacier, hatch


def _render_layer(
    ind_path: str, layer: dict, out: str, maxzoom: int, quality: int, alpha: float, lossless: bool
):
    from .tiles import LayerGrid, write_pmtiles

    values, glacier, hatch = _read_layer(ind_path, tuple(layer["src"]), alpha)
    grid = LayerGrid.build(values, layer["colormap"], glacier, hatch)
    meta = {k: v for k, v in layer.items() if k not in ("src", "url")}
    meta["attribution"] = "ERA5-Land (Copernicus C3S)"
    return write_pmtiles(
        Path(out), grid, maxzoom=maxzoom, quality=quality, metadata=meta, lossless=lossless
    )


# --------------------------------------------------------------------------- manifest
def manifest_thresholds(cfg: Config) -> list[dict]:
    out = []
    for t in cfg.thresholds:
        e: dict = {"id": t["id"], "cm": t["cm"]}
        if t["default"]:
            e["default"] = True
        if t["station_equivalent_cm"] is not None:
            e["station_equivalent_cm"] = t["station_equivalent_cm"]
        e["label"] = t["label"]
        e["description"] = t["description"]
        out.append(e)
    return out


def build_manifest(cfg: Config, layers: list[dict], frag: dict | None = None) -> dict:
    """manifest.json content (contract v1.5) for the given layers and projections fragment.

    Every layer carries a ``threshold``; projection layers, which exist only for the default
    threshold, get the default id when the fragment does not set one.
    """
    default_id = cfg.default_threshold["id"]
    out_layers = []
    for ly in layers:
        e = {k: v for k, v in ly.items() if k != "src"}
        e.setdefault("threshold", default_id)
        out_layers.append(e)
    m: dict = {
        "schema_version": SCHEMA_VERSION,
        "data_version": data_version(cfg),
        "built": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "build_hash": git_hash(),
        "years": {"first": cfg.first_year, "last": cfg.last_year},
        "threshold_cm": cfg.threshold_cm,
    }
    if cfg.station_equivalent_cm is not None:
        m["station_equivalent_cm"] = cfg.station_equivalent_cm
    m["thresholds"] = manifest_thresholds(cfg)
    m.update(
        {
            "attribution": ATTRIBUTION.format(year=datetime.now(UTC).year),
            "definitions": [
                {k: d[k] for k in ("id", "label", "short", "description", "default") if k in d}
                for d in cfg.definitions
            ],
            "windows": [w.as_dict() for w in cfg.windows()],
            "layers": out_layers,
            "colormaps": COLORMAPS,
            "glacier_style": "hatched",
            "points": {"index": "points/index.json", "tile_deg": 5, "format": "wx-points-v1"},
            "projections": frag["projections"] if frag else {"available": False},
            "places": "places.json",
            "regions": "regions.json",
        }
    )
    return m


# --------------------------------------------------------------------------- helpers
def git_hash() -> str:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"], cwd=REPO_ROOT, capture_output=True,
            text=True, check=True,
        ).stdout.strip()  # fmt: skip
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no", "--", "src", "config"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()  # fmt: skip
        return sha + ("-dirty" if dirty else "")
    except Exception:  # noqa: BLE001
        return "unknown"


def data_version(cfg: Config) -> str:
    return f"{cfg.last_year}.{int(cfg.export.get('build_counter', 1))}"


def _fingerprint(cfg: Config, ind_fp: str) -> str:
    import hashlib

    h = hashlib.sha256(ind_fp.encode())
    h.update(cfg.section_hash("export", "thresholds", "definitions").encode())
    h.update(json.dumps(COLORMAPS, sort_keys=True).encode())
    h.update(f"export{EXPORT_VERSION}".encode())
    return h.hexdigest()[:16]


def _sizes(root: Path) -> dict[str, int]:
    return {
        str(p.relative_to(root)).replace("\\", "/"): p.stat().st_size
        for p in root.rglob("*")
        if p.is_file() and not p.name.startswith(".")
    }


# --------------------------------------------------------------------------- main
def export_all(
    cfg: Config,
    paths: DataPaths,
    web_out: Path,
    force: bool = False,
    workers: int | None = None,
    cogs: bool = True,
    bundle: bool = True,
    max_layers: int | None = None,
) -> dict:
    import zarr

    web_out = Path(web_out)
    web_out.mkdir(parents=True, exist_ok=True)
    stores = {t["id"]: paths.indicators_for(t) for t in cfg.thresholds}
    for tid, sp in stores.items():
        if not sp.exists():
            raise FileNotFoundError(f"indicators for threshold {tid!r} missing: {sp}")
    inds = {tid: zarr.open_group(str(sp), mode="r") for tid, sp in stores.items()}
    t0 = cfg.default_threshold
    ind = inds[t0["id"]]
    cube_root = zarr.open_group(str(paths.cube), mode="r")
    fp = _fingerprint(
        cfg, ";".join(f"{tid}={inds[tid].attrs.get('fingerprint', '')}" for tid in inds)
    )
    state_path = web_out / ".export_state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() and not force else {}
    if state.get("fingerprint") != fp:
        state = {"fingerprint": fp, "layers": {}}
    ex = cfg.export
    maxz, quality = int(ex.get("tile_maxzoom", 6)), int(ex.get("webp_quality", 50))
    lossless = bool(ex.get("webp_lossless", True))
    alpha = cfg.trend_p
    defs = cfg.definition_ids
    wins = cfg.windows()
    wid = [w.id for w in wins]
    d0 = defs.index(cfg.default_definition)
    a, b = cfg.change_pair
    full = cfg.full_window().id

    # Projection layers (and the manifest's projections block) come from the projections
    # export. Given web_out, it stages its tiles and proj/ point files into that folder and
    # returns None if they are missing, so this export alone yields a complete bundle.
    frag = manifest_fragment(paths, web_out)

    # 1 · raster layers -------------------------------------------------------------
    decades_all = bool(ex.get("decades_for_all_definitions", True))
    layers = plan_all_layers(cfg, decades_for_all=decades_all)
    own_layers = layers
    if frag:
        layers = layers + frag["layers"]
    tiles_dir = web_out / "tiles"
    todo = [
        ly for ly in own_layers
        if not (tiles_dir / f"{ly['id']}.pmtiles").exists()
        or state["layers"].get(ly["id"]) != fp
    ]  # fmt: skip
    remaining = 0
    if max_layers is not None and len(todo) > max_layers:
        remaining = len(todo) - max_layers
        todo = todo[:max_layers]
    n_workers = workers or max(1, min(len(todo), (os.cpu_count() or 2) - 2, 8))
    log.info("export: %d layers (%d to render, %d workers)", len(layers), len(todo), n_workers)
    if todo:
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            futs = {
                pool.submit(
                    _render_layer, str(stores[ly["src"][0]]), ly,
                    str(tiles_dir / f"{ly['id']}.pmtiles"), maxz, quality, alpha, lossless,
                ): ly
                for ly in todo
            }  # fmt: skip
            for fut in as_completed(futs):
                ly = futs[fut]
                stats = fut.result()
                state["layers"][ly["id"]] = fp
                state_path.write_text(json.dumps(state, indent=1))
                log.info("tiles %s: %d tiles, %.1f MB", ly["id"], stats["tiles"],
                         stats["bytes"] / 1e6)  # fmt: skip

    if remaining:
        log.info("export paused: %d layers still to render; run export again to resume", remaining)
        return {"remaining_layers": remaining}

    # 2 · point tiles ---------------------------------------------------------------
    from .points import write_point_tiles

    glacier = ind["glacier"][:]
    land = ind["land"][:]
    years = [int(y) for y in cube_root["year"][:]]
    keep = [k for k, y in enumerate(years) if cfg.first_year <= y <= cfg.last_year]
    points_dir = web_out / "points"
    if state.get("points") != fp or not (points_dir / "index.json").exists():
        if points_dir.exists():
            shutil.rmtree(points_dir)

        class _Cube:  # restrict the cube to the configured years
            def __getitem__(self, key):
                return cube_root["snow_depth_cm"][key][keep[0] : keep[-1] + 1]

        pstats = write_point_tiles(
            points_dir, _Cube(), glacier, land, years[keep[0] : keep[-1] + 1]
        )
        state["points"] = fp
        state_path.write_text(json.dumps(state, indent=1))
        log.info("points: %d tiles, %.1f MB", pstats["tiles"], pstats["bytes"] / 1e6)

    # 3 · places and regions -----------------------------------------------------------
    from ..external import SOURCES, fetch
    from .places import build_places, write_json
    from .regions import build_regions

    for name in SOURCES:
        fetch(name, paths.external)
    prob = ind["probability"]
    p_full = prob[d0, wid.index(full)]
    p_then = prob[d0, wid.index(a)]
    p_now = prob[d0, wid.index(b)]
    win_map = {"p_full": full, "p_then": a, "p_now": b}
    # contract v1.5: optional p_then_<id> / p_now_<id> for the other thresholds
    extras = []
    for t in cfg.thresholds[1:]:
        pr = inds[t["id"]]["probability"]
        extras.append(
            (f"p_then_{t['id']}", f"p_now_{t['id']}", pr[d0, wid.index(a)], pr[d0, wid.index(b)])
        )
    if state.get("places") != fp or not (web_out / "places.json").exists():
        places = build_places(
            paths.external, p_full, p_then, p_now, ind["trend"][d0], ind["trend_p"][d0],
            win_map, cfg.default_definition, alpha, extras=extras,
        )  # fmt: skip
        places["threshold"] = t0["id"]
        write_json(web_out / "places.json", places)
        lat = np.asarray(ind["lat"][:])
        regions = build_regions(
            paths.external, p_then, p_now, glacier, lat, cfg.default_definition,
            {"p_then": a, "p_now": b}, extras=extras,
        )  # fmt: skip
        regions["threshold"] = t0["id"]
        write_json(web_out / "regions.json", regions)
        state["places"] = fp
        state_path.write_text(json.dumps(state, indent=1))

    # 4 · budget -------------------------------------------------------------------
    budget_total = float(ex.get("budget_total_mb", 400)) * 1e6
    budget_file = float(ex.get("budget_file_mb", 90)) * 1e6
    sizes = {k: v for k, v in _sizes(web_out).items() if k != "manifest.json"}
    if sum(sizes.values()) > budget_total:
        # 1st fallback: other thresholds get only the contract minimum; 2nd: decades only for
        # the default definition as well.
        planned = plan_all_layers(cfg, decades_all, others_minimal=True)
        keep_ids = {ly["id"] for ly in planned}
        dropped = sum(sizes.get(ly["url"], 0) for ly in layers if ly["id"] not in keep_ids)
        dec_all = decades_all and sum(sizes.values()) - dropped <= budget_total
        log.warning(
            "web data %.0f MB over budget: other thresholds minimal%s",
            sum(sizes.values()) / 1e6,
            "" if dec_all else "; decades for the default definition only",
        )
        layers = plan_all_layers(cfg, dec_all, others_minimal=True)
        if frag:
            layers += frag["layers"]
    keep_files = {ly["url"] for ly in layers}
    for p in tiles_dir.glob("*.pmtiles"):
        if f"tiles/{p.name}" not in keep_files:
            p.unlink()
    for p in tiles_dir.glob("*.tmp"):
        p.unlink()
    sizes = {k: v for k, v in _sizes(web_out).items() if k != "manifest.json"}
    total = sum(sizes.values())
    too_big = {k: v for k, v in sizes.items() if v > budget_file}
    if too_big:
        raise RuntimeError(f"files over {budget_file / 1e6:.0f} MB: {too_big}")
    if total > budget_total:
        raise RuntimeError(f"web data {total / 1e6:.0f} MB exceeds {budget_total / 1e6:.0f} MB")

    # 5 · manifest -------------------------------------------------------------------
    dv = data_version(cfg)
    manifest = build_manifest(cfg, layers, frag)
    write_json(web_out / "manifest.json", manifest)
    total += (web_out / "manifest.json").stat().st_size
    log.info("web data: %d files, %.1f MB (largest %s)", len(sizes) + 1, total / 1e6,
             max(sizes, key=sizes.get))  # fmt: skip

    # 6 · COGs ---------------------------------------------------------------------
    if cogs:
        from .cog import write_cog

        cog_dir = paths.cog
        cog_state = cog_dir / ".export_state.json"
        if not (cog_state.exists() and json.loads(cog_state.read_text()).get("fp") == fp):
            tags = {"source": "ERA5-Land (Copernicus C3S)", "data_version": dv,
                    "license": "CC BY 4.0"}  # fmt: skip
            for t in cfg.thresholds:
                zi, sfx = inds[t["id"]], t["suffix"]
                tt = {**tags, "threshold_cm": t["cm"], "threshold": t["id"]}
                pr = zi["probability"]
                for di, d in enumerate(defs):
                    for wi, w in enumerate(wins):
                        write_cog(
                            cog_dir / f"probability_pct__{d}__{w.id}{sfx}.tif",
                            pr[di, wi],
                            tags={**tt, "units": "%", "definition": d, "window": w.id},
                        )
                        if t["default"] and w.kind in ("full", "normal"):
                            n = zi["n_valid"][di, wi].astype("float32")
                            n[~land] = np.nan
                            write_cog(
                                cog_dir / f"valid_years__{d}__{w.id}.tif",
                                n,
                                tags={**tags, "units": "years", "definition": d},
                            )
                    write_cog(
                        cog_dir / f"change_pp__{d}__{a}__{b}{sfx}.tif",
                        zi["change"][di],
                        tags={**tt, "units": "pp", "definition": d},
                    )
                    write_cog(
                        cog_dir / f"trend_pp_per_decade__{d}__{full}{sfx}.tif",
                        zi["trend"][di],
                        tags={**tt, "units": "pp/decade", "definition": d},
                    )
                    write_cog(
                        cog_dir / f"trend_mk_pvalue__{d}__{full}{sfx}.tif",
                        zi["trend_p"][di],
                        tags={**tt, "units": "1", "definition": d},
                    )
            g = glacier.astype("float32")
            g[~land] = np.nan
            write_cog(cog_dir / "glacier_flag.tif", g, tags={**tags, "units": "1 = glacier"})
            cog_state.write_text(json.dumps({"fp": fp}))
            log.info("COGs written to %s", cog_dir)

    # 7 · bundle -------------------------------------------------------------------
    bundle_path = None
    if bundle:
        paths.products.mkdir(parents=True, exist_ok=True)
        bundle_path = paths.products / f"whitexmas-web-data-{dv}.tar.gz"
        with tarfile.open(bundle_path, "w:gz", compresslevel=6) as tar:
            for rel in sorted(_sizes(web_out)):
                tar.add(web_out / rel, arcname=rel)
        log.info("bundle %s (%.1f MB)", bundle_path, bundle_path.stat().st_size / 1e6)
    return {"total_bytes": total, "layers": len(layers), "bundle": str(bundle_path)}
