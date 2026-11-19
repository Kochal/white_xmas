"""Turn the downloaded NetCDFs into one Zarr snow cube plus static masks.

Output (``$WHITEXMAS_DATA/interim/snow_cube.zarr``):

- ``snow_depth_cm[year, day, lat, lon]``: int16, daily-mean snow depth in whole centimetres
  (floored, so ``>= k cm`` on the cube is exactly ``>= k cm`` on the source for integer k),
  ``-1`` = nodata (ocean or missing). North-up (lat 90 → -90), lon -180 … 179.9.
- ``land``: bool, cell has snow data in at least one year and is not water.
- ``land_sea_mask``, ``glacier_fraction``, ``lake_cover``: float32 fractions from the ERA5-Land
  invariants.

ERA5-Land also simulates snow on inland water with its lake model. Cells that are mostly water
(``land_sea_mask < 0.5`` or ``lake_cover >= 0.5``) are set to nodata, so lakes such as Lake
Michigan or Ladoga render as water, not as land with little snow.
- ``orography_m``: float32 surface height (geopotential / g).

Chunks are (all years, all days, 50, 50): one chunk per 5° point tile, which serves point access
in one read and lets indicators stream over tiles; map products read the whole array once.
"""

from __future__ import annotations

import json
import logging
import warnings
from pathlib import Path

import netCDF4
import numpy as np
import xarray as xr
import zarr
from zarr.codecs import BloscCodec

from .config import Config
from .download import SNOW_VAR, STATIC_VARIABLES, Manifest, plan_jobs
from .paths import DataPaths

log = logging.getLogger(__name__)

NODATA = -1
CHUNK = 50
BAND = 50  # rows read per pass (multiple of CHUNK); ~80 MB of cube per pass
G = 9.80665
CUBE_VERSION = 2  # 2: water cells (sea or lake) masked to nodata
LAND_MIN = 0.5  # land_sea_mask >= this is land
LAKE_MAX = 0.5  # lake_cover >= this is water


def lat_lon(ny: int, nx: int, res: float = 0.1) -> tuple[np.ndarray, np.ndarray]:
    lat = np.round(90.0 - res * np.arange(ny), 6)
    lon = np.round(-180.0 + res * np.arange(nx), 6)
    return lat, lon


def to_cm(depth_m: np.ndarray) -> np.ndarray:
    """Metres (float, NaN = nodata) → floored whole cm as int16, NODATA for NaN."""
    a = np.asarray(depth_m, dtype="float64") * 100.0
    out = np.full(a.shape, NODATA, dtype="int16")
    ok = np.isfinite(a)
    # Tiny negative values (-1e-23) occur from averaging; clip to 0. Add a small epsilon so
    # values like 0.03 m (2.9999999 cm in float32) floor to 3, not 2.
    out[ok] = np.clip(np.floor(np.maximum(a[ok], 0.0) + 1e-4), 0, np.iinfo("int16").max)
    return out


def _lon_order(lon: np.ndarray) -> np.ndarray:
    """Index that reorders a longitude axis to start at -180 (handles 0…360 grids)."""
    wrapped = ((lon + 180.0) % 360.0) - 180.0
    return np.argsort(np.round(wrapped, 6), kind="stable")


def _lat_order(lat: np.ndarray) -> np.ndarray:
    return np.argsort(-lat, kind="stable")


def water_mask(
    land_sea_mask: np.ndarray | None, lake_cover: np.ndarray | None
) -> np.ndarray | None:
    """True where a cell is mostly sea or lake; None if neither field is available."""
    if land_sea_mask is None and lake_cover is None:
        return None
    shape = (land_sea_mask if land_sea_mask is not None else lake_cover).shape
    water = np.zeros(shape, dtype=bool)
    if land_sea_mask is not None:
        water |= np.nan_to_num(land_sea_mask, nan=0.0) < LAND_MIN
    if lake_cover is not None:
        water |= np.nan_to_num(lake_cover, nan=0.0) >= LAKE_MAX
    return water


def _read_static(path: Path, var: str, lat_idx: np.ndarray, lon_idx: np.ndarray) -> np.ndarray:
    with netCDF4.Dataset(path) as ds:
        v = ds[var]
        v.set_auto_mask(True)
        arr = np.ma.filled(v[0] if v.ndim == 3 else v[:], np.nan).astype("float32")
    return arr[lat_idx][:, lon_idx]


def snow_files(cfg: Config, paths: DataPaths) -> dict[int, list[Path]]:
    """Downloaded snow files per year (one per year, or one per day when split)."""
    out: dict[int, list[Path]] = {}
    for j in plan_jobs(cfg, paths):
        if j.kind == "snow":
            out.setdefault(j.year, []).append(j.target)
    return out


def input_fingerprint(cfg: Config, paths: DataPaths) -> str:
    """Hash of the inputs: manifest SHA-256 of every file + relevant config."""
    import hashlib

    man = Manifest(paths.download_manifest)
    h = hashlib.sha256()
    for j in plan_jobs(cfg, paths):
        e = man.get(j.key) or {}
        h.update(f"{j.key}={e.get('sha256')}\n".encode())
    h.update(cfg.section_hash("years", "grid", "download").encode())
    h.update(f"cube{CUBE_VERSION}".encode())
    return h.hexdigest()[:16]


def ingest(cfg: Config, paths: DataPaths, force: bool = False) -> Path:
    files = snow_files(cfg, paths)
    missing = [str(p) for ps in files.values() for p in ps if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"{len(missing)} snow files missing (run `whitexmas download`): {missing[:3]} …"
        )
    fp = input_fingerprint(cfg, paths)
    out = paths.cube
    if out.exists() and not force:
        try:
            if zarr.open_group(str(out), mode="r").attrs.get("input_fingerprint") == fp:
                log.info("cube up to date (%s); skipping ingest", fp)
                return out
        except Exception:  # noqa: BLE001 - unreadable cube: rebuild
            pass
    build_cube(
        years=cfg.years,
        files=files,
        static_dir=paths.static_raw,
        out=out,
        attrs={"input_fingerprint": fp},
    )
    return out


def build_cube(
    years: list[int],
    files: dict[int, list[Path]],
    static_dir: Path,
    out: Path,
    attrs: dict | None = None,
    band: int = BAND,
    chunk: int = CHUNK,
) -> Path:
    first = files[years[0]][0]
    with netCDF4.Dataset(first) as ds:
        src_lat = np.asarray(ds["latitude"][:], dtype="float64")
        src_lon = np.asarray(ds["longitude"][:], dtype="float64")
    lat_idx, lon_idx = _lat_order(src_lat), _lon_order(src_lon)
    ny, nx = src_lat.size, src_lon.size
    res = float(abs(src_lat[1] - src_lat[0]))
    lat, lon = lat_lon(ny, nx, res)
    if not np.allclose(src_lat[lat_idx], lat, atol=1e-4) or not np.allclose(
        ((src_lon[lon_idx] + 180) % 360) - 180, lon, atol=1e-4
    ):
        raise ValueError("source grid does not match the expected regular global grid")
    n_years = len(years)

    tmp = out.with_name(out.name + ".tmp")
    if tmp.exists():
        import shutil

        shutil.rmtree(tmp)
    root = zarr.open_group(str(tmp), mode="w")
    comp = BloscCodec(cname="zstd", clevel=5, shuffle="bitshuffle")
    cube = root.create_array(
        "snow_depth_cm",
        shape=(n_years, 3, ny, nx),
        chunks=(n_years, 3, chunk, chunk),
        dtype="int16",
        fill_value=NODATA,
        compressors=comp,
        dimension_names=["year", "day", "lat", "lon"],
    )
    cube.attrs.update(
        {
            "units": "cm",
            "long_name": "daily-mean snow depth (floored to whole cm)",
            "nodata": NODATA,
        }
    )

    handles: dict[int, list[netCDF4.Dataset]] = {
        y: [netCDF4.Dataset(p) for p in sorted(files[y])] for y in years
    }
    # Each file may come in its own orientation; index it to north-up, -180-first.
    order: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for hs in handles.values():
        for h in hs:
            f_lat = np.asarray(h["latitude"][:], dtype="float64")
            f_lon = np.asarray(h["longitude"][:], dtype="float64")
            li, lo = _lat_order(f_lat), _lon_order(f_lon)
            if not np.allclose(f_lat[li], lat, atol=1e-4) or not np.allclose(
                ((f_lon[lo] + 180) % 360) - 180, lon, atol=1e-4
            ):
                raise ValueError(f"{h.filepath()}: grid differs from the first file")
            order[id(h)] = (li, lo)
    statics = {
        "land_sea_mask": ("land_sea_mask", 1.0, {"units": "1"}),
        "glacier_mask": ("glacier_fraction", 1.0, {"units": "1"}),
        "geopotential": ("orography_m", 1.0 / G, {"units": "m"}),
        "lake_cover": ("lake_cover", 1.0, {"units": "1"}),
    }
    static_arrays: dict[str, np.ndarray] = {}
    for src in statics:
        p = static_dir / f"{src}.nc"
        if not p.exists():
            log.warning("static field %s missing; skipping", p)
            continue
        with netCDF4.Dataset(p) as ds:
            s_lat = np.asarray(ds["latitude"][:], dtype="float64")
            s_lon = np.asarray(ds["longitude"][:], dtype="float64")
        arr = _read_static(p, STATIC_VARIABLES[src], _lat_order(s_lat), _lon_order(s_lon))
        if arr.shape != (ny, nx):
            raise ValueError(f"{p}: shape {arr.shape} != {(ny, nx)}")
        static_arrays[src] = arr
    water = water_mask(static_arrays.get("land_sea_mask"), static_arrays.get("lake_cover"))
    if water is None:
        log.warning("no land-sea mask or lake cover: water cells keep their snow data")

    land = np.zeros((ny, nx), dtype=bool)
    try:
        for j0 in range(0, ny, band):
            j1 = min(ny, j0 + band)
            buf = np.full((n_years, 3, j1 - j0, nx), NODATA, dtype="int16")
            for yi, y in enumerate(years):
                day = 0
                for h in handles[y]:
                    v = h[SNOW_VAR]
                    v.set_auto_mask(True)
                    li, lo = order[id(h)]
                    rows = li[j0:j1]
                    r0, r1 = int(rows.min()), int(rows.max()) + 1
                    block = np.ma.filled(v[:, r0:r1, :], np.nan)
                    block = block[:, rows - r0][:, :, lo]
                    for k in range(block.shape[0]):
                        buf[yi, day] = to_cm(block[k])
                        day += 1
                if day != 3:
                    raise ValueError(f"year {y}: expected 3 days, got {day}")
            if water is not None:
                buf[:, :, water[j0:j1]] = NODATA
            cube[:, :, j0:j1, :] = buf
            land[j0:j1] = (buf != NODATA).any(axis=(0, 1))
            log.info("ingest: rows %d-%d of %d", j0, j1, ny)
    finally:
        for hs in handles.values():
            for h in hs:
                h.close()

    def put2d(name: str, arr: np.ndarray, dtype: str, fill, **a) -> None:
        z = root.create_array(
            name,
            data=arr.astype(dtype),
            chunks=(chunk * 10, chunk * 10),
            compressors=comp,
            fill_value=fill,
            dimension_names=["lat", "lon"],
        )
        z.attrs.update(a)

    put2d(
        "land", land, "bool", False,
        long_name="cell has snow data in at least one year and is not mostly sea or lake",
    )  # fmt: skip
    for src, arr in static_arrays.items():
        name, scale, a = statics[src]
        put2d(name, arr * scale, "float32", np.nan, **a)

    for name, vals, unit in [
        ("year", np.array(years, "int16"), "year"),
        ("day", np.array([24, 25, 26], "int8"), "day of December"),
        ("lat", lat, "degrees_north"),
        ("lon", lon, "degrees_east"),
    ]:
        z = root.create_array(
            name, data=vals, chunks=vals.shape, compressors=None, dimension_names=[name]
        )
        z.attrs.update({"units": unit})
    root.attrs.update(
        {
            "title": "White Christmas snow cube (ERA5-Land daily-mean snow depth, Dec 24-26)",
            "source": "Copernicus Climate Change Service, ERA5-Land "
            "(derived-era5-land-daily-statistics)",
            "cube_version": CUBE_VERSION,
            "years": json.dumps([years[0], years[-1]]),
            **(attrs or {}),
        }
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        zarr.consolidate_metadata(str(tmp))
    if out.exists():
        import shutil

        shutil.rmtree(out)
    tmp.rename(out)
    log.info("cube written to %s", out)
    return out


def open_cube(path: Path) -> xr.Dataset:
    return xr.open_zarr(str(path), consolidated=True, mask_and_scale=False)
