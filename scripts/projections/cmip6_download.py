# /// script
# requires-python = ">=3.12"
# dependencies = ["requests", "xarray", "h5netcdf", "netcdf4", "cftime", "numpy"]
# ///
"""Download the CMIP6 files listed in ``$WHITEXMAS_DATA/cmip6/plan.json``.

Standalone (Phase 1 of the projections track). Run with::

    uv run scripts/projections/cmip6_download.py [--workers 4] [--keep-raw]

ESGF's OPeNDAP endpoints were unavailable on the reachable nodes during the
spike (DKRZ returns 404 for ``dodsC``), so whole files are downloaded over
HTTPS, verified against the ESGF SHA-256, cut down to the Christmas window
(11 Dec - 8 Jan of every year, i.e. Christmas +/- 14 days) and the raw file is
deleted. Land fraction (``sftlf``) files are kept whole.

Idempotent: a file whose subset already appears in the manifest with a
matching checksum is skipped. Every finished file appends one JSON line to
``$WHITEXMAS_DATA/cmip6/manifest.jsonl``; ``manifest.json`` is the aggregated
view rewritten at the end of each run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import threading
import time
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import requests
import xarray as xr

DATA = Path(
    os.environ.get("WHITEXMAS_DATA", r"C:\Users\AlexanderKoch\TransparentEarth\white_xmas_data")
)
OUT = DATA / "cmip6"
TMP = OUT / "tmp"
MANIFEST_LINES = OUT / "manifest.jsonl"
MANIFEST = OUT / "manifest.json"

SUBSET_DEC_FIRST_DAY = 11  # keep 11-31 Dec ...
SUBSET_JAN_LAST_DAY = 8  # ... and 1-8 Jan

_lock = threading.Lock()
_host_sems: dict[str, threading.Semaphore] = defaultdict(lambda: threading.Semaphore(2))
_dead_hosts: set[str] = set()


def log(msg: str) -> None:
    with _lock:
        print(f"{dt.datetime.now():%H:%M:%S} {msg}", flush=True)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict[str, dict]:
    done = {}
    if MANIFEST_LINES.exists():
        for line in MANIFEST_LINES.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                done[rec["source_file"]] = rec
    return done


def append_manifest(rec: dict) -> None:
    with _lock, open(MANIFEST_LINES, "a") as fh:
        fh.write(json.dumps(rec) + "\n")


def fetch(url: str, dest: Path, expected_size: int | None) -> None:
    host = url.split("/")[2]
    with _host_sems[host]:
        with requests.get(url, stream=True, timeout=(20, 180)) as r:
            r.raise_for_status()
            t0, n = time.time(), 0
            with open(dest, "wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)
                    n += len(chunk)
            rate = n / max(time.time() - t0, 1e-3) / 1e6
    if expected_size and n != expected_size:
        raise OSError(f"size mismatch {n} != {expected_size}")
    log(f"  got {dest.name[:-5]} from {host}: {n / 1e6:.0f} MB at {rate:.1f} MB/s")


def subset(raw: Path, dest: Path) -> int:
    """Keep 11 Dec - 8 Jan of every year. Returns the number of time steps kept."""
    coder = xr.coders.CFDatetimeCoder(use_cftime=True)
    with xr.open_dataset(raw, decode_times=coder) as ds:
        m, d = ds.time.dt.month.values, ds.time.dt.day.values
        sel = ((m == 12) & (d >= SUBSET_DEC_FIRST_DAY)) | ((m == 1) & (d <= SUBSET_JAN_LAST_DAY))
        sub = ds.isel(time=np.where(sel)[0]).load()
    sub.attrs["whitexmas_subset"] = (
        f"time steps with date in {SUBSET_DEC_FIRST_DAY}-31 Dec or 1-{SUBSET_JAN_LAST_DAY} Jan, "
        f"cut from {raw.name[:-5] if raw.name.endswith('.part') else raw.name}"
    )
    enc = {v: {"zlib": True, "complevel": 4} for v in sub.data_vars if sub[v].ndim >= 2}
    tmp = dest.with_suffix(".tmp.nc")
    sub.to_netcdf(tmp, encoding=enc)
    os.replace(tmp, dest)
    return int(sel.sum())


def process(f: dict, done: dict, keep_raw: bool) -> dict | None:
    name = f["file"]
    rel = (
        Path(f["variable"])
        / f["model"]
        / (name if f["variable"] == "sftlf" else name.replace(".nc", "_xmas.nc"))
    )
    dest = OUT / rel
    prev = done.get(name)
    if (
        prev
        and dest.exists()
        and prev.get("subset_sha256")
        and sha256_of(dest) == prev["subset_sha256"]
    ):
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    raw = TMP / (name + ".part")
    last_err = None
    for url in f["urls"]:
        host = url.split("/")[2]
        if host in _dead_hosts:
            continue
        for attempt in range(3):
            try:
                fetch(url, raw, f.get("size"))
                got = sha256_of(raw)
                if f.get("sha256") and got != f["sha256"]:
                    raise OSError(f"sha256 mismatch from {host}")
                if f["variable"] == "sftlf":
                    os.replace(raw, dest)
                    nsteps = None
                else:
                    nsteps = subset(raw, dest)
                    if not keep_raw:
                        raw.unlink()
                rec = {
                    "model": f["model"],
                    "member": f["member"],
                    "experiment": f["experiment"],
                    "variable": f["variable"],
                    "table": f["table"],
                    "dataset_id": f.get("dataset_id"),
                    "source_file": name,
                    "source_url": url,
                    "source_size": f.get("size"),
                    "source_sha256": got,
                    "source_sha256_verified": bool(f.get("sha256")),
                    "subset_file": rel.as_posix(),
                    "subset_sha256": sha256_of(dest),
                    "subset_size": dest.stat().st_size,
                    "subset_time_steps": nsteps,
                    "subset_days": None
                    if nsteps is None
                    else f"{SUBSET_DEC_FIRST_DAY}-31 Dec + 1-{SUBSET_JAN_LAST_DAY} Jan",
                    "downloaded_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                }
                append_manifest(rec)
                return rec
            except (requests.ConnectionError, requests.Timeout) as e:
                last_err = e
                if attempt == 0 and isinstance(e, requests.ConnectTimeout):
                    _dead_hosts.add(host)
                    log(f"  {host} unreachable, skipping it from now on")
                    break
                time.sleep(5 * 2**attempt)
            except Exception as e:  # noqa: BLE001
                last_err = e
                log(f"  {name} from {host} failed: {e!r}")
                time.sleep(5 * 2**attempt)
            finally:
                if raw.exists() and not keep_raw:
                    raw.unlink(missing_ok=True)
    raise RuntimeError(f"all sources failed for {name}: {last_err!r}")


def write_aggregate() -> None:
    recs = list(load_manifest().values())
    recs.sort(key=lambda r: (r["model"], r["variable"], r["experiment"], r["source_file"]))
    MANIFEST.write_text(
        json.dumps(
            {
                "description": "CMIP6 inputs for White Christmas projections (method B). "
                "source_* describe the ESGF file, subset_* the local Christmas-window cut.",
                "updated": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                "files": recs,
            },
            indent=1,
        )
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--keep-raw", action="store_true")
    ap.add_argument("--model", action="append", help="only these models")
    args = ap.parse_args()

    plan = json.loads((OUT / "plan.json").read_text())
    files = plan["files"]
    if args.model:
        files = [f for f in files if f["model"] in args.model]
    # small and fx files first so every model gets started early
    files.sort(key=lambda f: (f["variable"] != "sftlf", f.get("size") or 0))
    TMP.mkdir(parents=True, exist_ok=True)
    done = load_manifest()
    log(f"{len(files)} files in plan, {len(done)} in manifest")
    failed = []
    with ThreadPoolExecutor(args.workers) as ex:
        futs = {ex.submit(process, f, done, args.keep_raw): f for f in files}
        for i, fut in enumerate(as_completed(futs), 1):
            f = futs[fut]
            try:
                rec = fut.result()
                if rec:
                    log(f"[{i}/{len(files)}] ok {f['file']}")
            except Exception as e:  # noqa: BLE001
                failed.append(f["file"])
                log(f"[{i}/{len(files)}] FAILED {f['file']}: {e}")
                traceback.print_exc()
            if i % 20 == 0:
                write_aggregate()
    write_aggregate()
    log(f"finished: {len(files) - len(failed)} ok, {len(failed)} failed")
    if failed:
        (OUT / "failed.txt").write_text("\n".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
