"""Download ERA5-Land daily-mean snow depth (Dec 24-26) and static fields from the CDS.

- One request per year (optionally split by day), global, NetCDF.
- Idempotent: a file listed in the manifest whose SHA-256 matches and which opens with the
  expected shape is skipped.
- Submitted job ids are written to the manifest before waiting, so an interrupted run resumes
  the same CDS jobs instead of queueing new ones.
- Retries with exponential backoff.

The CDS key is read by ``cdsapi`` from ``~/.cdsapirc`` (or ``CDSAPI_URL``/``CDSAPI_KEY``) and is
never logged or written anywhere.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import zipfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import Config
from .paths import DataPaths

log = logging.getLogger(__name__)

STATIC_DATASET = "reanalysis-era5-land"
STATIC_VARIABLES = {
    "land_sea_mask": "lsm",
    "geopotential": "z",
    "glacier_mask": "glm",
    "lake_cover": "cl",
}
NY, NX = 1801, 3600
SNOW_VAR = "sde"


# --------------------------------------------------------------------------- requests
@dataclass(frozen=True)
class Job:
    key: str  # manifest key, e.g. "snow_depth/1950" or "static/land_sea_mask"
    dataset: str
    request: dict[str, Any]
    target: Path
    kind: str  # "snow" | "static"
    year: int | None = None
    days: tuple[int, ...] = field(default=())


def snow_request(cfg: Config, year: int, days: list[int] | None = None) -> dict[str, Any]:
    d = cfg.download
    days = days or list(d["days"])
    return {
        "variable": [d["variable"]],
        "year": str(year),
        "month": f"{int(d['month']):02d}",
        "day": [f"{x:02d}" for x in days],
        "daily_statistic": d["daily_statistic"],
        "time_zone": d["time_zone"],
        "frequency": d["frequency"],
        "area": [90, -180, -90, 180],
    }


def static_request(variable: str) -> dict[str, Any]:
    # Invariant fields: any single time step carries them.
    return {
        "variable": [variable],
        "year": "2020",
        "month": "01",
        "day": ["01"],
        "time": ["00:00"],
        "data_format": "netcdf",
        "download_format": "unarchived",
    }


def plan_jobs(cfg: Config, paths: DataPaths, years: list[int] | None = None) -> list[Job]:
    d = cfg.download
    years = years or cfg.years
    jobs: list[Job] = []
    for var, flag in [
        ("land_sea_mask", "land_sea_mask"),
        ("geopotential", "geopotential"),
        ("glacier_mask", "glacier_mask"),
        ("lake_cover", "lake_cover"),
    ]:
        if d.get("static", {}).get(flag, True):
            jobs.append(
                Job(
                    key=f"static/{var}",
                    dataset=STATIC_DATASET,
                    request=static_request(var),
                    target=paths.static_raw / f"{var}.nc",
                    kind="static",
                )
            )
    for y in years:
        if d.get("split_by_day"):
            for day in d["days"]:
                jobs.append(
                    Job(
                        key=f"snow_depth/{y}-{day}",
                        dataset=d["dataset"],
                        request=snow_request(cfg, y, [day]),
                        target=paths.snow_raw / f"sd_daymean_{y}12{day:02d}.nc",
                        kind="snow",
                        year=y,
                        days=(day,),
                    )
                )
        else:
            jobs.append(
                Job(
                    key=f"snow_depth/{y}",
                    dataset=d["dataset"],
                    request=snow_request(cfg, y),
                    target=paths.snow_raw / f"sd_daymean_{y}_dec24-26.nc",
                    kind="snow",
                    year=y,
                    days=tuple(d["days"]),
                )
            )
    return jobs


# --------------------------------------------------------------------------- manifest
class Manifest:
    """Thread-safe JSON manifest of downloaded files."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))
        else:
            self.data = {"schema": 1, "files": {}}

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            return self.data["files"].get(key)

    def update(self, key: str, **fields: Any) -> None:
        with self._lock:
            entry = self.data["files"].setdefault(key, {})
            entry.update(fields)
            self._write()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


# --------------------------------------------------------------------------- verification
def verify_netcdf(job: Job, path: Path) -> tuple[bool, str]:
    """Open the file and check variable, grid and number of time steps."""
    import xarray as xr

    try:
        with xr.open_dataset(path, engine="netcdf4") as ds:
            names = list(ds.data_vars)
            if job.kind == "snow":
                # The daily-statistics product names geometric snow depth "sde" (metres).
                if SNOW_VAR not in ds:
                    return False, f"no '{SNOW_VAR}' variable (have {names})"
                da = ds[SNOW_VAR]
                tdim = next((d for d in da.dims if "time" in d), None)
                nt = da.sizes[tdim] if tdim else 1
                if nt != len(job.days):
                    return False, f"expected {len(job.days)} days, got {nt}"
                times = ds[tdim].values if tdim else []
                for t in times:
                    ts = str(t)[:10]
                    if not ts.startswith(f"{job.year}-12-"):
                        return False, f"unexpected time {ts}"
            else:
                short = STATIC_VARIABLES[job.key.split("/")[1]]
                if short not in ds:
                    return False, f"no '{short}' variable (have {names})"
                da = ds[short]
            lat = next(d for d in da.dims if d.startswith("lat"))
            lon = next(d for d in da.dims if d.startswith("lon"))
            if da.sizes[lat] != NY or da.sizes[lon] != NX:
                return False, f"grid {da.sizes[lat]}x{da.sizes[lon]} != {NY}x{NX}"
    except Exception as e:  # noqa: BLE001 - any failure to open means "not verified"
        return False, f"cannot open: {e}"
    return True, "ok"


def _unpack_if_zip(path: Path) -> None:
    """Some CDS products arrive zipped; unpack a single NetCDF member in place."""
    if not zipfile.is_zipfile(path):
        return
    with zipfile.ZipFile(path) as z:
        members = [m for m in z.namelist() if m.endswith(".nc")]
        if len(members) != 1:
            raise RuntimeError(f"{path}: expected one .nc in zip, got {z.namelist()}")
        tmp = path.with_suffix(".unzipped")
        with z.open(members[0]) as src, open(tmp, "wb") as dst:
            while b := src.read(1 << 20):
                dst.write(b)
    tmp.replace(path)


# --------------------------------------------------------------------------- client
def make_client():
    """A CDS client using the key from ~/.cdsapirc. Never logs the key."""
    import cdsapi.api
    from ecmwf import datastores

    url, key, verify = cdsapi.api.get_url_key_verify(None, None, None)
    return datastores.Client(
        url=url, key=key, verify=bool(verify), progress=False, maximum_tries=10
    )


def is_done(job: Job, manifest: Manifest, check_sha: bool = True) -> bool:
    entry = manifest.get(job.key)
    if not job.target.exists() or not entry or entry.get("status") != "done":
        return False
    if check_sha and entry.get("sha256") != sha256_file(job.target):
        return False
    return verify_netcdf(job, job.target)[0]


def run_job(
    job: Job,
    manifest: Manifest,
    client_factory: Callable[[], Any] = make_client,
    max_retries: int = 6,
    backoff: float = 60.0,
    poll: float = 30.0,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Download one job; returns "skipped" or "done". Raises after max_retries."""
    if is_done(job, manifest):
        return "skipped"
    job.target.parent.mkdir(parents=True, exist_ok=True)
    attempt = 0
    while True:
        attempt += 1
        try:
            client = client_factory()
            entry = manifest.get(job.key) or {}
            remote = None
            jid = entry.get("job_id")
            if jid and entry.get("status") != "done" and entry.get("request") == job.request:
                try:
                    remote = client.get_remote(jid)
                    _ = remote.status
                    log.info("%s: resuming CDS job %s", job.key, jid)
                except Exception:  # noqa: BLE001 - job expired or deleted: resubmit
                    remote = None
            if remote is None:
                remote = client.submit(job.dataset, job.request)
                manifest.update(
                    job.key,
                    dataset=job.dataset,
                    request=job.request,
                    job_id=remote.request_id,
                    status="submitted",
                    submitted_at=_now(),
                    file=str(job.target.relative_to(job.target.parents[1])).replace("\\", "/"),
                )
                log.info("%s: submitted CDS job %s", job.key, remote.request_id)
            try:
                while not remote.results_ready:
                    sleep(poll)
            except Exception:
                # The job failed or expired (resumed or freshly submitted): forget it so the
                # next attempt submits afresh instead of resuming a dead job.
                manifest.update(job.key, job_id=None)
                raise
            tmp = job.target.with_suffix(".part")
            if tmp.exists():
                tmp.unlink()
            remote.download(str(tmp))
            _unpack_if_zip(tmp)
            ok, why = verify_netcdf(job, tmp)
            if not ok:
                manifest.update(job.key, status="failed_verify", error=why)
                raise RuntimeError(f"{job.key}: verification failed: {why}")
            tmp.replace(job.target)
            manifest.update(
                job.key,
                status="done",
                sha256=sha256_file(job.target),
                bytes=job.target.stat().st_size,
                downloaded_at=_now(),
                error=None,
            )
            log.info("%s: done (%.1f MB)", job.key, job.target.stat().st_size / 1e6)
            return "done"
        except Exception as e:  # noqa: BLE001
            msg = str(e).splitlines()[0][:300] if str(e) else type(e).__name__
            manifest.update(job.key, status="error", error=msg, attempts=attempt)
            if attempt >= max_retries:
                raise
            wait = backoff * 2 ** (attempt - 1)
            log.warning(
                "%s: attempt %d failed (%s); retrying in %.0fs", job.key, attempt, msg, wait
            )
            sleep(wait)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def download_all(
    cfg: Config,
    paths: DataPaths,
    years: list[int] | None = None,
    parallel: int = 6,
    static_only: bool = False,
) -> dict[str, str]:
    jobs = plan_jobs(cfg, paths, years)
    if static_only:
        jobs = [j for j in jobs if j.kind == "static"]
    manifest = Manifest(paths.download_manifest)
    d = cfg.download
    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=parallel) as ex:
        futs = {
            ex.submit(
                run_job,
                j,
                manifest,
                make_client,
                int(d.get("max_retries", 6)),
                float(d.get("backoff_seconds", 60)),
            ): j
            for j in jobs
        }
        for fut in as_completed(futs):
            j = futs[fut]
            try:
                results[j.key] = fut.result()
            except Exception as e:  # noqa: BLE001
                results[j.key] = f"failed: {e}"
                log.error("%s failed permanently: %s", j.key, e)
    return results
