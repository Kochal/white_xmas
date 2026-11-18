"""Data directories, resolved from the environment. No hard-coded machine paths."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config" / "pipeline.yaml"


def data_root() -> Path:
    """Root of the shared data directory.

    Read from ``WHITEXMAS_DATA``; defaults to ``white_xmas_data`` next to the repository
    (for a worktree checkout, next to the main repository folder).
    """
    env = os.environ.get("WHITEXMAS_DATA")
    if env:
        return Path(env).expanduser().resolve()
    # Walk up until we leave any worktrees/ folder, then sit beside the repo.
    root = REPO_ROOT
    for parent in [REPO_ROOT, *REPO_ROOT.parents]:
        if parent.name == "worktrees":
            root = parent.parent
            break
    return (root.parent / "white_xmas_data").resolve()


@dataclass(frozen=True)
class DataPaths:
    root: Path

    @classmethod
    def from_env(cls) -> DataPaths:
        return cls(data_root())

    @property
    def era5land(self) -> Path:
        return self.root / "era5land"

    @property
    def snow_raw(self) -> Path:
        return self.era5land / "snow_depth"

    @property
    def static_raw(self) -> Path:
        return self.era5land / "static"

    @property
    def download_manifest(self) -> Path:
        return self.era5land / "manifest.json"

    @property
    def interim(self) -> Path:
        return self.root / "interim"

    @property
    def cube(self) -> Path:
        return self.interim / "snow_cube.zarr"

    @property
    def indicators(self) -> Path:
        return self.interim / "indicators.zarr"

    @property
    def products(self) -> Path:
        return self.root / "products"

    @property
    def cog(self) -> Path:
        return self.products / "cog"

    @property
    def external(self) -> Path:
        """Third-party reference data (GeoNames, Natural Earth)."""
        return self.root / "external"
