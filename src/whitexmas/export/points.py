"""``wx-points-v1`` point tiles: per-cell yearly snow depth for Dec 24-26, 5° x 5° tiles.

Uncompressed layout (little-endian), gzip-compressed on disk:
  header (16 B): b"WXP1", uint16 first_year, uint16 n_years, uint16 n_cells_x,
                 uint16 n_cells_y, uint8 n_days, 3 reserved bytes
  body: uint8[n_cells_y][n_cells_x][n_years][n_days], whole cm; 254 = >= 254 cm; 255 = nodata
  glacier bitmask: uint8[ceil(nx*ny/8)], bit k (LSB first) = cell k in row-major order
"""

from __future__ import annotations

import gzip
import json
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

MAGIC = b"WXP1"
HEADER = struct.Struct("<4sHHHHB3x")
CELLS = 50
NODATA = 255
CAP = 254


def to_uint8(cube_cm: np.ndarray) -> np.ndarray:
    """int16 cm with -1 nodata → uint8 (0..253, 254 = >= 254 cm, 255 = nodata)."""
    a = np.asarray(cube_cm)
    out = np.clip(a, 0, CAP).astype("uint8")
    out[a < 0] = NODATA
    return out


def encode_tile(values: np.ndarray, glacier: np.ndarray, first_year: int) -> bytes:
    """values: uint8 (ny, nx, n_years, n_days); glacier: bool (ny, nx). Returns gzip bytes."""
    ny, nx, n_years, n_days = values.shape
    header = HEADER.pack(MAGIC, first_year, n_years, nx, ny, n_days)
    bits = np.packbits(glacier.reshape(-1).astype("uint8"), bitorder="little")
    raw = header + np.ascontiguousarray(values, dtype="uint8").tobytes() + bits.tobytes()
    return gzip.compress(raw, compresslevel=9, mtime=0)


@dataclass
class PointTile:
    first_year: int
    values: np.ndarray  # (ny, nx, n_years, n_days) uint8
    glacier: np.ndarray  # (ny, nx) bool


def decode_tile(data: bytes) -> PointTile:
    raw = gzip.decompress(data)
    magic, first, n_years, nx, ny, n_days = HEADER.unpack_from(raw, 0)
    if magic != MAGIC:
        raise ValueError(f"bad magic {magic!r}")
    n = ny * nx * n_years * n_days
    body = np.frombuffer(raw, dtype="uint8", count=n, offset=HEADER.size)
    nbits = (nx * ny + 7) // 8
    bits = np.frombuffer(raw, dtype="uint8", count=nbits, offset=HEADER.size + n)
    if len(raw) != HEADER.size + n + nbits:
        raise ValueError("unexpected tile length")
    glac = np.unpackbits(bits, bitorder="little")[: nx * ny].astype(bool).reshape(ny, nx)
    return PointTile(first, body.reshape(ny, nx, n_years, n_days), glac)


def tile_of(lon: float, lat: float, tile_deg: int = 5) -> tuple[int, int]:
    return int(np.floor((lon + 180) / tile_deg)), int(np.floor((90 - lat) / tile_deg))


def write_point_tiles(
    out_dir: Path,
    cube,  # array-like (year, day, lat, lon) int16, supports slicing (zarr)
    glacier: np.ndarray,
    land: np.ndarray,
    years: list[int],
) -> dict:
    """Write every tile with at least one land cell, plus index.json. Returns stats."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ny, nx = land.shape
    names: list[str] = []
    total = 0
    for ty in range((ny + CELLS - 1) // CELLS):
        j0, j1 = ty * CELLS, min(ny, (ty + 1) * CELLS)
        if not land[j0:j1].any():
            continue
        band = np.asarray(cube[:, :, j0:j1, :])  # (year, day, rows, nx)
        for tx in range(nx // CELLS):
            i0, i1 = tx * CELLS, (tx + 1) * CELLS
            if not land[j0:j1, i0:i1].any():
                continue
            vals = np.full((CELLS, CELLS, len(years), 3), NODATA, dtype="uint8")
            block = band[:, :, :, i0:i1]  # (year, day, rows, 50)
            vals[: j1 - j0] = to_uint8(block).transpose(2, 3, 0, 1)
            g = np.zeros((CELLS, CELLS), bool)
            g[: j1 - j0] = glacier[j0:j1, i0:i1]
            data = encode_tile(vals, g, years[0])
            name = f"{tx}_{ty}"
            (out_dir / f"{name}.bin.gz").write_bytes(data)
            names.append(name)
            total += len(data)
    index = {"format": "wx-points-v1", "tile_deg": 5, "years": [years[0], years[-1]],
             "tiles": names}  # fmt: skip
    (out_dir / "index.json").write_text(json.dumps(index, separators=(",", ":")))
    return {"tiles": len(names), "bytes": total}
