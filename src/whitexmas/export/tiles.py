"""Pre-coloured raster map layers as PMTiles (WebP tiles, Web Mercator, XYZ z0..maxzoom).

A layer is a 0.1° global grid of values. Every output pixel takes the colour of the ERA5-Land
cell under its centre (nearest neighbour). At zooms coarser than the grid (z < 4) each pixel
averages a k × k block of sub-samples, so low zooms are smooth rather than aliased.

Hatching is drawn in screen space (diagonal lines, continuous across tiles):
- glacier cells: light grey with darker grey lines, in every layer;
- insignificant trend cells (``hatch`` mask): the trend colour with dark lines over it.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .colors import (
    GLACIER_FILL,
    GLACIER_LINE,
    HATCH_LINE,
    HATCH_SPACING,
    HATCH_WIDTH,
    apply_colormap,
)

TILE = 256
NATIVE_ZOOM = 4  # 256 * 2^4 = 4096 px around the world ≈ 3600 cells
NONE, GLACIER, INSIGNIFICANT = 0, 1, 2


@dataclass
class LayerGrid:
    """Colours and hatch state on the cell grid, ready for lookups."""

    rgba: np.ndarray  # (ny, nx, 4) uint8
    state: np.ndarray  # (ny, nx) uint8: NONE | GLACIER | INSIGNIFICANT

    @classmethod
    def build(
        cls,
        values: np.ndarray,
        colormap: str,
        glacier: np.ndarray | None = None,
        hatch: np.ndarray | None = None,
    ) -> LayerGrid:
        rgba = apply_colormap(values, colormap)
        state = np.zeros(values.shape, dtype="uint8")
        if hatch is not None:
            state[hatch & np.isfinite(values)] = INSIGNIFICANT
        if glacier is not None:
            state[glacier] = GLACIER
            rgba[glacier] = (*GLACIER_FILL, 255)
        return cls(rgba, state)


def _cols(z: int, x: int, k: int, sub: int, nx: int, res: float) -> np.ndarray:
    world = TILE * k * 2**z
    px = x * TILE * k + np.arange(TILE) * k + sub
    lon = (px + 0.5) / world * 360.0 - 180.0
    return np.round((lon + 180.0) / res).astype("int64") % nx


def _rows(z: int, y: int, k: int, sub: int, ny: int, res: float) -> np.ndarray:
    world = TILE * k * 2**z
    py = y * TILE * k + np.arange(TILE) * k + sub
    lat = np.degrees(np.arctan(np.sinh(math.pi * (1 - 2 * (py + 0.5) / world))))
    return np.clip(np.round((90.0 - lat) / res).astype("int64"), 0, ny - 1)


def render_tile(grid: LayerGrid, z: int, x: int, y: int, res: float = 0.1) -> np.ndarray | None:
    """RGBA uint8 (256, 256, 4) for tile z/x/y, or None when the tile is empty."""
    ny, nx = grid.state.shape
    k = 2 ** max(0, NATIVE_ZOOM - z)
    if k == 1:
        jj, ii = _rows(z, y, 1, 0, ny, res), _cols(z, x, 1, 0, nx, res)
        rgba = grid.rgba[jj][:, ii]
        if not rgba[..., 3].any():
            return None
        state = grid.state[jj][:, ii]
        glac = state == GLACIER
        insig = state == INSIGNIFICANT
        out = rgba.copy()
    else:
        acc = np.zeros((TILE, TILE, 3), dtype="float64")
        alpha = np.zeros((TILE, TILE), dtype="float64")
        g_frac = np.zeros((TILE, TILE), dtype="float64")
        i_frac = np.zeros((TILE, TILE), dtype="float64")
        for sy in range(k):
            jj = _rows(z, y, k, sy, ny, res)
            sub_rgba = grid.rgba[jj]
            sub_state = grid.state[jj]
            for sx in range(k):
                ii = _cols(z, x, k, sx, nx, res)
                c = sub_rgba[:, ii].astype("float64")
                a = c[..., 3] / 255.0
                acc += c[..., :3] * a[..., None]
                alpha += a
                s = sub_state[:, ii]
                g_frac += s == GLACIER
                i_frac += s == INSIGNIFICANT
        n = k * k
        if not alpha.any():
            return None
        out = np.zeros((TILE, TILE, 4), dtype="uint8")
        with np.errstate(invalid="ignore", divide="ignore"):
            col = np.where(alpha[..., None] > 0, acc / alpha[..., None], 0)
        out[..., :3] = np.round(col).astype("uint8")
        out[..., 3] = np.round(alpha / n * 255).astype("uint8")
        glac = g_frac / n >= 0.5
        insig = (i_frac / n >= 0.5) & ~glac
    # screen-space diagonal hatch, continuous across tiles
    gx = x * TILE + np.arange(TILE)
    gy = y * TILE + np.arange(TILE)
    line = ((gx[None, :] + gy[:, None]) % HATCH_SPACING) < HATCH_WIDTH
    if glac.any():
        out[glac & ~line, :3] = GLACIER_FILL
        out[glac & line, :3] = GLACIER_LINE
        out[glac, 3] = np.maximum(out[glac, 3], 255)
    m = insig & line & (out[..., 3] > 0)
    if m.any():
        out[m, :3] = np.round(
            0.4 * out[m, :3].astype("float64") + 0.6 * np.array(HATCH_LINE)
        ).astype("uint8")
    return out


def encode_webp(rgba: np.ndarray, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, format="WEBP", quality=quality, method=4)
    return buf.getvalue()


def write_pmtiles(
    path: Path,
    grid: LayerGrid,
    maxzoom: int = 6,
    minzoom: int = 0,
    quality: int = 90,
    metadata: dict | None = None,
) -> dict:
    """Render every non-empty tile and write one PMTiles archive. Returns stats."""
    from pmtiles.tile import Compression, TileType, zxy_to_tileid
    from pmtiles.writer import Writer

    tiles: list[tuple[int, bytes]] = []
    for z in range(minzoom, maxzoom + 1):
        n = 2**z
        for y in range(n):
            for x in range(n):
                img = render_tile(grid, z, x, y)
                if img is not None:
                    tiles.append((zxy_to_tileid(z, x, y), encode_webp(img, quality)))
    tiles.sort(key=lambda t: t[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".pmtiles.tmp")
    with open(tmp, "wb") as f:
        w = Writer(f)
        for tid, data in tiles:
            w.write_tile(tid, data)
        w.finalize(
            {
                "tile_type": TileType.WEBP,
                "tile_compression": Compression.NONE,
                "min_zoom": minzoom,
                "max_zoom": maxzoom,
                "min_lon_e7": -1800000000,
                "min_lat_e7": -850511287,
                "max_lon_e7": 1800000000,
                "max_lat_e7": 850511287,
                "center_zoom": 2,
                "center_lon_e7": 100000000,
                "center_lat_e7": 480000000,
            },
            metadata or {},
        )
    tmp.replace(path)
    return {"tiles": len(tiles), "bytes": path.stat().st_size}
