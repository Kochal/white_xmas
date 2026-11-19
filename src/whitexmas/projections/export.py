"""Web and open-data products for the projections (web data contract, ``wx-proj-v1``).

Writes, from ``interim/projections/projections.zarr``:

Real builds render into the staging folder ``$WHITEXMAS_DATA/products/projections/web``;
:func:`manifest_fragment` (called by the pipeline's export with its web-out) copies them from
there into the web-out and verifies them before the layers are listed (D-16).

- ``<staging>/tiles/proj__<def>__gwl<g>.pmtiles``: median projected probability (colormap
  ``probability``), and ``projchange__<def>__gwl<g>.pmtiles``: median change against the
  1996-2025 baseline in percentage points (colormap ``change``), hatched where fewer than two
  thirds of the models agree on the direction. Rendered with the pipeline's tile code so colours
  and glacier hatching match the historical layers.
- ``<staging>/proj/<tx>_<ty>.bin.gz`` (+ ``proj/index.json``): ``wx-proj-v1`` point tiles.
- ``$WHITEXMAS_DATA/products/projections/manifest_fragment.json``: the manifest ``layers``
  entries and the ``projections`` block; :func:`manifest_fragment` stages the files and returns
  it so the pipeline's manifest writer can merge it, and :func:`patch_manifest` merges it into
  an existing ``manifest.json`` directly.
- ``$WHITEXMAS_DATA/products/projections/cog/*.tif``: COGs of p10, p50, p90 and change
  (a placeholder preview goes to ``cog_placeholder/`` and is tagged ``placeholder=true``).

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
from .cmip6 import load_plan
from .settings import ProjPaths

log = logging.getLogger(__name__)

MAGIC = b"WXQ1"
HEADER = struct.Struct("<4sBBHH6x")
CELLS = 50
NODATA = 255

LABELS = {1.5: "+1.5 °C", 2.0: "+2 °C", 3.0: "+3 °C"}
NOT_REACHED = "late this century or later; most models reach it only under SSP5-8.5"


def approx_label(windows: list[dict | None]) -> str:
    """When a warming level is reached under SSP2-4.5 (plan D-10, contract v1.3).

    ``windows`` holds, per model used, its window for the level (``{"experiment", "start",
    "end"}``) or None. The label is the decade of the median SSP2-4.5 window centre; when
    fewer than half of the models reach the level under SSP2-4.5, it says so instead.
    """
    centres = [
        (w["start"] + w["end"]) / 2 for w in windows if w and w.get("experiment") == "ssp245"
    ]
    if not windows or len(centres) < len(windows) / 2:
        return NOT_REACHED
    decade = int(np.floor(np.median(centres) / 10.0) * 10)
    return f"around the {decade}s"


def warming_levels(models: list[str], gwls: list[float], plan_models: dict) -> list[dict]:
    """``manifest.projections.warming_levels`` derived from the models actually used."""
    out = []
    for g in gwls:
        wins = [plan_models.get(m, {}).get("windows", {}).get(str(float(g))) for m in models]
        out.append({"gwl": float(g), "label": LABELS.get(float(g), f"+{g:g} °C"),
                    "approx": approx_label(wins)})  # fmt: skip
    return out


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
    (out_dir / "index.json").write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")
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
                    "url": f"tiles/{lid}.pmtiles",
                    "colormap": "change",
                    "hatch_disagreement": True,
                    "minzoom": 0,
                    "maxzoom": maxzoom,
                }
            )
    return layers


def projections_block(models: list[str], levels: list[dict], baseline_window: str) -> dict:
    return {
        "available": True,
        "warming_levels": levels,
        "baseline_window": baseline_window,
        "points": {"tile_deg": 5, "format": "wx-proj-v1", "path": "proj/{tx}_{ty}.bin.gz"},
        "models": models,
    }


def _needed_files(staging: Path, frag: dict) -> list[str] | None:
    """Paths (relative to a web-out) of every file the fragment's layers and point tiles need,
    or None when the staged set under ``staging`` is missing or incomplete."""
    idx = staging / "proj" / "index.json"
    if not idx.is_file():
        log.warning("projections: %s is missing", idx)
        return None
    tiles = json.loads(idx.read_text(encoding="utf-8")).get("tiles", [])
    rels = [ly["url"] for ly in frag["layers"]] + ["proj/index.json"]
    rels += [f"proj/{t}.bin.gz" for t in tiles]
    missing = [r for r in rels if not (staging / r).is_file()]
    if missing:
        log.warning("projections: %d staged files missing in %s, e.g. %s", len(missing),
                    staging, missing[:3])  # fmt: skip
        return None
    return rels


def _sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _identical(a: Path, b: Path) -> bool:
    return b.is_file() and a.stat().st_size == b.stat().st_size and _sha256(a) == _sha256(b)


def stage_files(staging: Path, frag: dict, web_out: Path) -> bool:
    """Copy the fragment's files from ``staging`` into ``web_out`` (skipping identical ones),
    remove point tiles in ``web_out/proj`` that the new index no longer lists, and verify that
    every needed file is present and identical. Returns False (copying nothing) when the
    staged set is incomplete."""
    import shutil

    rels = _needed_files(staging, frag)
    if rels is None:
        return False
    web_out = Path(web_out)
    if web_out.resolve() == staging.resolve():
        return True
    copied = 0
    for rel in rels:
        src, dst = staging / rel, web_out / rel
        if _identical(src, dst):
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".tmp")
        shutil.copyfile(src, tmp)
        tmp.replace(dst)
        copied += 1
    keep = {Path(r).name for r in rels if r.startswith("proj/")}
    stale = [p for p in (web_out / "proj").glob("*.bin.gz") if p.name not in keep]
    for p in stale:
        p.unlink()
    bad = [r for r in rels if not _identical(staging / r, web_out / r)]
    if bad:
        log.warning("projections: %d files did not verify in %s, e.g. %s", len(bad), web_out,
                    bad[:3])  # fmt: skip
        return False
    log.info("projections: staged %d files into %s (%d copied, %d stale point tiles removed)",
             len(rels), web_out, copied, len(stale))  # fmt: skip
    return True


def manifest_fragment(paths: DataPaths, web_out: Path | None = None) -> dict | None:
    """``{"layers": [...], "projections": {...}}`` for the pipeline's manifest (D-16).

    With ``web_out``: first stages the projection tiles and point tiles into ``web_out`` and
    verifies them; returns None (so the manifest keeps ``available: false``) when there is no
    real export, when it was built on the placeholder baseline, or when the staged files are
    missing or incomplete. Never returns layers whose files are not in ``web_out``.

    Without ``web_out`` (pipeline hooks older than D-16): returns the fragment unverified and
    logs a warning.
    """
    pp = ProjPaths.from_data(paths)
    f = pp.products / "manifest_fragment.json"
    if not f.exists():
        return None
    frag = json.loads(f.read_text(encoding="utf-8"))
    if frag.get("placeholder"):
        return None
    out = {"layers": frag["layers"], "projections": frag["projections"]}
    if web_out is None:
        log.warning(
            "manifest_fragment() called without web_out: projection files are neither staged "
            "nor verified; pass the export's web_out (D-16)"
        )
        return out
    if not stage_files(pp.staging, frag, Path(web_out)):
        log.warning("projections left out of the manifest: staged files incomplete")
        return None
    return out


def patch_manifest(manifest_path: Path, fragment: dict) -> None:
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    ids = {ly["id"] for ly in fragment["layers"]}
    m["layers"] = [ly for ly in m.get("layers", []) if ly["id"] not in ids] + fragment["layers"]
    m["projections"] = fragment["projections"]
    manifest_path.write_text(
        json.dumps(m, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )


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
    lossless: bool,
) -> dict:
    import xarray as xr

    from ..export.tiles import LayerGrid, write_pmtiles

    ds = xr.open_zarr(store)
    vals = ds[var].sel(definition=d, gwl=g).values
    hatch = ~ds["agree"].sel(definition=d, gwl=g).values if var == "change" else None
    grid = LayerGrid.build(vals, cmap, ds["glacier"].values, hatch)
    meta = {"id": lid, "attribution": "CMIP6 models (ESGF) + ERA5-Land (Copernicus C3S)"}
    return write_pmtiles(
        Path(out), grid, maxzoom=maxzoom, quality=quality, metadata=meta, lossless=lossless
    )


def is_pipeline_web_out(web_out: Path) -> bool:
    """True for the pipeline's web data folder (``web/static/data``), which gets bundled."""
    from ..paths import REPO_ROOT

    p = Path(web_out).resolve()
    return p == (REPO_ROOT / "web" / "static" / "data").resolve() or p.parts[-3:] == (
        "web",
        "static",
        "data",
    )


def export_projections(
    paths: DataPaths,
    web_out: Path | None = None,
    cogs: bool = True,
    allow_placeholder: bool = False,
    definitions: tuple[str, ...] = ("christmas_day",),
    patch: bool = False,
    workers: int | None = None,
) -> dict:
    """Write the projection products.

    A real build always renders into the staging folder (``products/projections/web``); when
    ``web_out`` is given as well, the files are then staged into it exactly as the pipeline's
    export does (:func:`manifest_fragment`), and ``patch`` also merges the fragment into an
    existing ``web_out/manifest.json``.

    A build on the placeholder baseline is refused unless ``allow_placeholder``; it then needs
    its own ``web_out``, never the staging folder or the pipeline's ``web/static/data``.
    """
    import xarray as xr

    from ..config import Config

    ex = Config.load(None).export  # same tile settings as the historical layers
    maxzoom = int(ex.get("tile_maxzoom", 6))
    quality = int(ex.get("webp_quality", 50))
    lossless = bool(ex.get("webp_lossless", True))
    pp = ProjPaths.from_data(paths)
    ds = xr.open_zarr(pp.ensemble)
    placeholder = bool(ds.attrs.get("placeholder"))
    if placeholder and not allow_placeholder:
        raise RuntimeError(
            "projections were built on the PLACEHOLDER baseline; rebuild them once the "
            "pipeline's indicators exist, or pass allow_placeholder for a local preview"
        )
    if placeholder and (
        web_out is None
        or is_pipeline_web_out(web_out)
        or Path(web_out).resolve() == pp.staging.resolve()
    ):
        raise RuntimeError(
            f"refusing to write a PLACEHOLDER preview into {web_out or pp.staging}: that folder "
            "is (or feeds) the published bundle; pass a separate preview folder as web_out"
        )
    target = Path(web_out) if placeholder else pp.staging
    if not placeholder:
        # a fresh staging folder, so no stale point tiles survive a rebuild
        import shutil

        if (target / "proj").exists():
            shutil.rmtree(target / "proj")
    defs = [str(d) for d in ds["definition"].values if str(d) in definitions]
    if not defs:
        raise ValueError(f"none of {definitions} in {pp.ensemble}")
    gwls = [float(g) for g in ds["gwl"].values]
    models = json.loads(ds.attrs["models"])
    settings = json.loads(ds.attrs["settings"])
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
    workers = workers or max(1, min(len(jobs), (os.cpu_count() or 2) - 2, 8))
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
                str(target / "tiles" / f"{lid}.pmtiles"),
                maxzoom,
                quality,
                lossless,
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
        target / "proj",
        sel["p10"].values,
        sel["p50"].values,
        sel["p90"].values,
        sel["agree"].values,
    )
    log.info("wx-proj-v1: %d tiles, %.1f MB", pts["tiles"], pts["bytes"] / 1e6)
    frag = {
        "placeholder": placeholder,
        "layers": plan_layers(defs, gwls, maxzoom),
        "projections": projections_block(
            models,
            warming_levels(models, gwls, load_plan(pp.cmip6)["models"]),
            settings.get("obs_window", "1996_2025"),
        ),
    }
    pp.products.mkdir(parents=True, exist_ok=True)
    # a placeholder preview never replaces a real fragment
    frag_name = "manifest_fragment.placeholder.json" if placeholder else "manifest_fragment.json"
    (pp.products / frag_name).write_text(json.dumps(frag, indent=1), encoding="utf-8")
    staged_into = None
    if not placeholder and web_out is not None:
        if manifest_fragment(paths, Path(web_out)) is None:
            raise RuntimeError(f"staging the projection files into {web_out} failed")
        staged_into = str(web_out)
    out_dir = Path(web_out) if web_out is not None else target
    if patch and (out_dir / "manifest.json").exists():
        patch_manifest(out_dir / "manifest.json", frag)
        log.info("merged projections into %s", out_dir / "manifest.json")
    if cogs:
        from ..export.cog import write_cog

        tags = {
            "source": "CMIP6 (ESGF) change applied to ERA5-Land (Copernicus C3S)",
            "models": ",".join(models),
            "license": "CC BY 4.0",
            "placeholder": "true" if placeholder else "false",
        }
        cog_dir = pp.products / ("cog_placeholder" if placeholder else "cog")
        for d in defs:
            for g in gwls:
                for k, unit in (("p10", "%"), ("p50", "%"), ("p90", "%"), ("change", "pp")):
                    write_cog(
                        cog_dir / f"proj_{k}__{d}__{gwl_id(g)}.tif",
                        ds[k].sel(definition=d, gwl=g).values,
                        tags={**tags, "units": unit, "definition": d, "warming_level": g},
                    )
    return {
        "layers": stats,
        "points": pts,
        "placeholder": placeholder,
        "rendered_into": str(target),
        "staged_into": staged_into,
    }
