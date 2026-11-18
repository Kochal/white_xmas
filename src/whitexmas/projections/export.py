"""Web and open-data products for the projections (web data contract, ``wx-proj-v1``).

Writes, from ``interim/projections/projections.zarr``:

- ``<web_out>/tiles/proj__<def>__gwl<g>.pmtiles``: median projected probability (colormap
  ``probability``), and ``projchange__<def>__gwl<g>.pmtiles``: median change against the
  1996-2025 baseline in percentage points (colormap ``change``), hatched where fewer than two
  thirds of the models agree on the direction. Rendered with the pipeline's tile code so colours
  and glacier hatching match the historical layers.
- ``<web_out>/proj/<tx>_<ty>.bin.gz`` (+ ``proj/index.json``): ``wx-proj-v1`` point tiles.
- ``$WHITEXMAS_DATA/products/projections/manifest_fragment.json``: the manifest ``layers``
  entries and the ``projections`` block; :func:`manifest_fragment` returns it so the pipeline's
  manifest writer can merge it, and :func:`patch_manifest` merges it into an existing
  ``manifest.json`` directly.
- ``$WHITEXMAS_DATA/products/projections/cog/*.tif``: COGs of p10, p50, p90 and change.

``wx-proj-v1`` (little-endian, gzip): header 16 B = b"WXQ1", uint8 n_levels, uint8 n_stats (3),
uint16 n_cells_x, uint16 n_cells_y, 6 reserved bytes; body uint8[ny][nx][n_levels][n_stats]
(p10, median, p90 in whole %, 255 = nodata); then one agreement bitmask per level,
uint8[ceil(nx*ny/8)], bit k (LSB first) = cell k in row-major order.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import struct
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..paths import DataPaths
from .settings import ProjPaths

log = logging.getLogger(__name__)

MAGIC = b"WXQ1"
HEADER = struct.Struct("<4sBBHH6x")
CELLS = 50
NODATA = 255

WARMING_LEVELS = {
    1.5: {"gwl": 1.5, "label": "+1.5 °C", "approx": "around the 2030s"},
    2.0: {"gwl": 2.0, "label": "+2 °C", "approx": "around the 2050s"},
    3.0: {"gwl": 3.0, "label": "+3 °C", "approx": "around the 2080s (SSP2-4.5 median)"},
}


def gwl_id(g: float) -> str:
    return f"gwl{float(g):.1f}"


# --------------------------------------------------------------------------- point tiles
def encode_proj_tile(stats: np.ndarray, agree: np.ndarray) -> bytes:
    """stats: float % (ny, nx, n_levels, 3) with NaN = nodata; agree: bool (n_levels, ny, nx)."""
    ny, nx, nl, ns = stats.shape
    body = np.where(np.isfinite(stats), np.clip(np.round(stats), 0, 100), NODATA).astype("uint8")
    raw = HEADER.pack(MAGIC, nl, ns, nx, ny) + np.ascontiguousarray(body).tobytes()
    for li in range(nl):
        raw += np.packbits(agree[li].reshape(-1).astype("uint8"), bitorder="little").tobytes()
    return gzip.compress(raw, compresslevel=9, mtime=0)


@dataclass
class ProjTile:
    stats: np.ndarray  # (ny, nx, n_levels, n_stats) uint8
    agree: np.ndarray  # (n_levels, ny, nx) bool


def decode_proj_tile(data: bytes) -> ProjTile:
    raw = gzip.decompress(data)
    magic, nl, ns, nx, ny = HEADER.unpack_from(raw, 0)
    if magic != MAGIC:
        raise ValueError(f"bad magic {magic!r}")
    n = ny * nx * nl * ns
    body = np.frombuffer(raw, dtype="uint8", count=n, offset=HEADER.size).reshape(ny, nx, nl, ns)
    nbits = (nx * ny + 7) // 8
    if len(raw) != HEADER.size + n + nl * nbits:
        raise ValueError("unexpected tile length")
    masks = []
    for li in range(nl):
        b = np.frombuffer(raw, dtype="uint8", count=nbits, offset=HEADER.size + n + li * nbits)
        masks.append(np.unpackbits(b, bitorder="little")[: nx * ny].astype(bool).reshape(ny, nx))
    return ProjTile(body, np.stack(masks))


def write_proj_tiles(
    out_dir: Path, p10: np.ndarray, p50: np.ndarray, p90: np.ndarray, agree: np.ndarray
) -> dict:
    """Arrays shaped (n_levels, NY, NX). Writes tiles with at least one cell with data."""
    out_dir.mkdir(parents=True, exist_ok=True)
    nl, ny, nx = p50.shape
    has = np.isfinite(p50).any(axis=0)
    names, total = [], 0
    for ty in range((ny + CELLS - 1) // CELLS):
        j0, j1 = ty * CELLS, min(ny, (ty + 1) * CELLS)
        if not has[j0:j1].any():
            continue
        for tx in range(nx // CELLS):
            i0, i1 = tx * CELLS, (tx + 1) * CELLS
            if not has[j0:j1, i0:i1].any():
                continue
            st = np.full((CELLS, CELLS, nl, 3), np.nan, dtype="float32")
            for k, arr in enumerate((p10, p50, p90)):
                st[: j1 - j0, :, :, k] = arr[:, j0:j1, i0:i1].transpose(1, 2, 0)
            ag = np.zeros((nl, CELLS, CELLS), bool)
            ag[:, : j1 - j0] = agree[:, j0:j1, i0:i1] & np.isfinite(p50[:, j0:j1, i0:i1])
            data = encode_proj_tile(st, ag)
            name = f"{tx}_{ty}"
            (out_dir / f"{name}.bin.gz").write_bytes(data)
            names.append(name)
            total += len(data)
    index = {"format": "wx-proj-v1", "tile_deg": 5, "tiles": names}
    (out_dir / "index.json").write_text(json.dumps(index, separators=(",", ":")))
    return {"tiles": len(names), "bytes": total}


# --------------------------------------------------------------------------- manifest
def plan_layers(definitions: list[str], gwls: list[float], maxzoom: int = 6) -> list[dict]:
    layers = []
    for d in definitions:
        for g in gwls:
            lid = f"proj__{d}__{gwl_id(g)}"
            layers.append(
                {
                    "id": lid,
                    "kind": "projection",
                    "definition": d,
                    "warming_level": float(g),
                    "url": f"tiles/{lid}.pmtiles",
                    "colormap": "probability",
                    "minzoom": 0,
                    "maxzoom": maxzoom,
                }
            )
    for d in definitions:
        for g in gwls:
            lid = f"projchange__{d}__{gwl_id(g)}"
            layers.append(
                {
                    "id": lid,
                    "kind": "projection_change",
                    "definition": d,
                    "warming_level": float(g),
                    "from": "1996_2025",
                    "url": f"tiles/{lid}.pmtiles",
                    "colormap": "change",
                    "hatch_low_agreement": True,
                    "minzoom": 0,
                    "maxzoom": maxzoom,
                }
            )
    return layers


def projections_block(models: list[str], gwls: list[float], baseline_window: str) -> dict:
    return {
        "available": True,
        "warming_levels": [WARMING_LEVELS[float(g)] for g in gwls],
        "baseline_window": baseline_window,
        "points": {"tile_deg": 5, "format": "wx-proj-v1", "path": "proj/{tx}_{ty}.bin.gz"},
        "models": models,
    }


def manifest_fragment(paths: DataPaths) -> dict | None:
    """``{"layers": [...], "projections": {...}}`` for the pipeline's manifest, or None when
    the projections have not been exported (or were built on the placeholder baseline)."""
    f = ProjPaths.from_data(paths).products / "manifest_fragment.json"
    if not f.exists():
        return None
    frag = json.loads(f.read_text())
    if frag.get("placeholder"):
        return None
    return {"layers": frag["layers"], "projections": frag["projections"]}


def patch_manifest(manifest_path: Path, fragment: dict) -> None:
    m = json.loads(manifest_path.read_text())
    ids = {ly["id"] for ly in fragment["layers"]}
    m["layers"] = [ly for ly in m.get("layers", []) if ly["id"] not in ids] + fragment["layers"]
    m["projections"] = fragment["projections"]
    manifest_path.write_text(json.dumps(m, ensure_ascii=False, separators=(",", ":")))


# --------------------------------------------------------------------------- export
def _render_layer(
    store: str,
    lid: str,
    d: str,
    g: float,
    var: str,
    cmap: str,
    out: str,
    maxzoom: int,
    quality: int,
) -> dict:
    import xarray as xr

    from ..export.tiles import LayerGrid, write_pmtiles

    ds = xr.open_zarr(store)
    vals = ds[var].sel(definition=d, gwl=g).values
    hatch = ~ds["agree"].sel(definition=d, gwl=g).values if var == "change" else None
    grid = LayerGrid.build(vals, cmap, ds["glacier"].values, hatch)
    meta = {"id": lid, "attribution": "CMIP6 models (ESGF) + ERA5-Land (Copernicus C3S)"}
    return write_pmtiles(Path(out), grid, maxzoom=maxzoom, quality=quality, metadata=meta)


def export_projections(
    paths: DataPaths,
    web_out: Path,
    maxzoom: int = 6,
    quality: int = 90,
    cogs: bool = True,
    allow_placeholder: bool = False,
) -> dict:
    import xarray as xr

    pp = ProjPaths.from_data(paths)
    ds = xr.open_zarr(pp.ensemble)
    placeholder = bool(ds.attrs.get("placeholder"))
    if placeholder and not allow_placeholder:
        raise RuntimeError(
            "projections were built on the PLACEHOLDER baseline; rebuild them once the "
            "pipeline's indicators exist, or pass allow_placeholder for a local preview"
        )
    defs = [str(d) for d in ds["definition"].values]
    gwls = [float(g) for g in ds["gwl"].values]
    models = json.loads(ds.attrs["models"])
    settings = json.loads(ds.attrs["settings"])
    web_out = Path(web_out)
    jobs = [
        (lid, d, g, var, cmap)
        for d in defs
        for g in gwls
        for lid, var, cmap in (
            (f"proj__{d}__{gwl_id(g)}", "p50", "probability"),
            (f"projchange__{d}__{gwl_id(g)}", "change", "change"),
        )
    ]
    stats = {}
    workers = max(1, min(len(jobs), (os.cpu_count() or 2) - 2, 8))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futs = {
            pool.submit(
                _render_layer,
                str(pp.ensemble),
                lid,
                d,
                g,
                var,
                cmap,
                str(web_out / "tiles" / f"{lid}.pmtiles"),
                maxzoom,
                quality,
            ): lid
            for lid, d, g, var, cmap in jobs
        }
        for fut in as_completed(futs):
            lid = futs[fut]
            stats[lid] = st = fut.result()
            log.info("tiles %s: %d tiles, %.1f MB", lid, st["tiles"], st["bytes"] / 1e6)
    d0 = "christmas_day" if "christmas_day" in defs else defs[0]
    sel = ds.sel(definition=d0)
    pts = write_proj_tiles(
        web_out / "proj",
        sel["p10"].values,
        sel["p50"].values,
        sel["p90"].values,
        sel["agree"].values,
    )
    log.info("wx-proj-v1: %d tiles, %.1f MB", pts["tiles"], pts["bytes"] / 1e6)
    frag = {
        "placeholder": placeholder,
        "layers": plan_layers(defs, gwls, maxzoom),
        "projections": projections_block(models, gwls, settings.get("obs_window", "1996_2025")),
    }
    pp.products.mkdir(parents=True, exist_ok=True)
    (pp.products / "manifest_fragment.json").write_text(json.dumps(frag, indent=1))
    if (web_out / "manifest.json").exists():
        patch_manifest(web_out / "manifest.json", frag)
        log.info("merged projections into %s", web_out / "manifest.json")
    if cogs:
        from ..export.cog import write_cog

        tags = {
            "source": "CMIP6 (ESGF) change applied to ERA5-Land (Copernicus C3S)",
            "models": ",".join(models),
            "license": "CC BY 4.0",
        }
        for d in defs:
            for g in gwls:
                for k, unit in (("p10", "%"), ("p50", "%"), ("p90", "%"), ("change", "pp")):
                    write_cog(
                        pp.products / "cog" / f"proj_{k}__{d}__{gwl_id(g)}.tif",
                        ds[k].sel(definition=d, gwl=g).values,
                        tags={**tags, "units": unit, "definition": d, "warming_level": g},
                    )
    return {"layers": stats, "points": pts, "placeholder": placeholder}
