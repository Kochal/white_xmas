from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from whitexmas import download as dl
from whitexmas.config import Config
from whitexmas.paths import DataPaths


def test_snow_request_matches_cds_schema(cfg: Config):
    r = dl.snow_request(cfg, 1950)
    assert r == {
        "variable": ["snow_depth"],
        "year": "1950",
        "month": "12",
        "day": ["24", "25", "26"],
        "daily_statistic": "daily_mean",
        "time_zone": "utc+00:00",
        "frequency": "1_hourly",
        "area": [90, -180, -90, 180],
    }


def test_plan_one_job_per_year_plus_static(cfg: Config, tmp_path: Path):
    jobs = dl.plan_jobs(cfg, DataPaths(tmp_path))
    snow = [j for j in jobs if j.kind == "snow"]
    static = [j for j in jobs if j.kind == "static"]
    assert len(snow) == 76
    assert {j.key for j in static} == {
        "static/land_sea_mask",
        "static/geopotential",
        "static/glacier_mask",
        "static/lake_cover",
    }


def _write_fake_snow(path: Path, year: int) -> None:
    # Small grid is enough for the fake client; verification is patched to accept it.
    t = pd.date_range(f"{year}-12-24", periods=3)
    ds = xr.Dataset(
        {"sde": (("valid_time", "latitude", "longitude"), np.zeros((3, 2, 2), "f4"))},
        coords={"valid_time": t, "latitude": [90.0, 89.9], "longitude": [-180.0, -179.9]},
    )
    ds.to_netcdf(path)


class FakeRemote:
    def __init__(self, year, fail_times):
        self.request_id = f"job-{year}"
        self.year = year
        self.fail_times = fail_times

    status = "successful"

    @property
    def results_ready(self):
        return True

    def download(self, target):
        if self.fail_times[0] > 0:
            self.fail_times[0] -= 1
            raise ConnectionError("boom")
        _write_fake_snow(Path(target), self.year)
        return target


class FakeClient:
    def __init__(self, fail_times, submits):
        self.fail_times = fail_times
        self.submits = submits

    def submit(self, dataset, request):
        self.submits.append(request["year"])
        return FakeRemote(int(request["year"]), self.fail_times)

    def get_remote(self, jid):
        return FakeRemote(int(jid.split("-")[1]), self.fail_times)


@pytest.fixture
def small_grid(monkeypatch):
    monkeypatch.setattr(dl, "NY", 2)
    monkeypatch.setattr(dl, "NX", 2)


def test_run_job_retries_then_skips_when_done(cfg, tmp_path, small_grid):
    paths = DataPaths(tmp_path)
    job = next(j for j in dl.plan_jobs(cfg, paths, [1999]) if j.kind == "snow")
    manifest = dl.Manifest(paths.download_manifest)
    fail, submits = [2], []
    out = dl.run_job(
        job, manifest, lambda: FakeClient(fail, submits), max_retries=5, sleep=lambda s: None
    )
    assert out == "done"
    entry = manifest.get(job.key)
    assert entry["status"] == "done"
    assert entry["job_id"] == "job-1999"
    assert entry["sha256"] == dl.sha256_file(job.target)
    # resumed the same CDS job after failures instead of resubmitting
    assert submits == ["1999"]

    # second run: file verifies, nothing is submitted
    out2 = dl.run_job(job, dl.Manifest(paths.download_manifest), lambda: FakeClient([0], submits))
    assert out2 == "skipped"
    assert submits == ["1999"]


def test_run_job_redownloads_corrupted_file(cfg, tmp_path, small_grid):
    paths = DataPaths(tmp_path)
    job = next(j for j in dl.plan_jobs(cfg, paths, [2001]) if j.kind == "snow")
    manifest = dl.Manifest(paths.download_manifest)
    submits = []
    dl.run_job(job, manifest, lambda: FakeClient([0], submits), sleep=lambda s: None)
    job.target.write_bytes(b"garbage")
    assert not dl.is_done(job, manifest)
