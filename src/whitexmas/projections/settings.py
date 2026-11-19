"""Settings for the projections track and where its files live.

Kept in code (with CLI overrides) rather than in ``config/pipeline.yaml``, which the pipeline
owns. Every output records the settings it was built with.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..paths import DataPaths

GWLS = (1.5, 2.0, 3.0)
DEFINITIONS = ("christmas_day", "all_three_days", "any_day")


@dataclass(frozen=True)
class ProjSettings:
    # 1 cm of snow at an assumed density of 250 kg m-3 (docs/projections.md §4)
    threshold_kg_m2: float = 2.5
    # centre days within +/- pool_days of 25 Dec are averaged (0 = Christmas Day only)
    pool_days: int = 7
    # D-12: the model baseline is the ERA5-Land window itself, 1996-2025 (historical up to
    # 2014, SSP2-4.5 from 2015), so the change is not double counted against the observations
    baseline: tuple[int, int] = (1996, 2025)
    # days up to 2014 come from historical, later ones from this experiment
    baseline_experiment: str = "ssp245"
    gwls: tuple[float, ...] = GWLS
    definitions: tuple[str, ...] = DEFINITIONS
    # a model cell counts as land when its land fraction is at least this (%)
    land_min_pct: float = 50.0
    # observed baseline window (ERA5-Land), id as in the pipeline's windows
    obs_window: str = "1996_2025"
    # models excluded after validation (see docs/projections.md, skill table)
    exclude: tuple[str, ...] = field(default_factory=tuple)

    def as_attrs(self) -> dict:
        d = asdict(self)
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in d.items()}


@dataclass(frozen=True)
class ProjPaths:
    root: Path

    @classmethod
    def from_data(cls, paths: DataPaths) -> ProjPaths:
        return cls(paths.root)

    @property
    def cmip6(self) -> Path:
        return self.root / "cmip6"

    @property
    def plan(self) -> Path:
        return self.cmip6 / "plan.json"

    @property
    def interim(self) -> Path:
        return self.root / "interim" / "projections"

    @property
    def models(self) -> Path:
        """Per-model counts and log-odds changes on the model's own grid."""
        return self.interim / "models"

    @property
    def ensemble(self) -> Path:
        """Ensemble statistics on the 0.1° ERA5-Land grid."""
        return self.interim / "projections.zarr"

    @property
    def validation(self) -> Path:
        return self.interim / "validation"

    @property
    def products(self) -> Path:
        return self.root / "products" / "projections"

    @property
    def staging(self) -> Path:
        """Where a real export renders ``tiles/proj*.pmtiles`` and ``proj/``; the pipeline's
        export stages them into its web-out through :func:`export.manifest_fragment`."""
        return self.products / "web"
