"""``whitexmas admin1 weights | stats | export | run | sample``."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(add_completion=False, no_args_is_help=True, help=__doc__)
ConfigOpt = Annotated[Path | None, typer.Option("--config", "-c", help="Path to pipeline.yaml")]


def _setup(config, verbose):
    from ..cli import _setup as base

    return base(config, verbose)


@app.command()
def weights(config: ConfigOpt = None, force: bool = False, verbose: bool = False) -> None:
    """Regions, cell-fraction and population weights, simplified outlines."""
    from .build import step_weights

    cfg, paths = _setup(config, verbose)
    typer.echo(step_weights(cfg, paths, force=force))


@app.command()
def stats(config: ConfigOpt = None, force: bool = False, verbose: bool = False) -> None:
    """Regional statistics (windows, spread, yearly series, trend, projections)."""
    from .build import step_stats

    cfg, paths = _setup(config, verbose)
    typer.echo(step_stats(cfg, paths, force=force))


@app.command()
def export(
    config: ConfigOpt = None,
    out: Annotated[
        Path | None, typer.Option(help="Output folder (default products/admin1)")
    ] = None,
    verbose: bool = False,
) -> None:
    """Web files (contract v1.6), CSV and manifest fragment into products/admin1/."""
    from .build import step_export

    cfg, paths = _setup(config, verbose)
    typer.echo(step_export(cfg, paths, out))


@app.command()
def run(config: ConfigOpt = None, force: bool = False, verbose: bool = False) -> None:
    """weights → stats → export, each skipped when up to date."""
    from .build import step_export, step_stats, step_weights

    cfg, paths = _setup(config, verbose)
    step_weights(cfg, paths, force=force)
    step_stats(cfg, paths, force=force)
    typer.echo(step_export(cfg, paths))


@app.command()
def sample(
    out: Annotated[Path, typer.Option(help="Output folder")] = Path("tests/fixtures/admin1_sample"),
    config: ConfigOpt = None,
    verbose: bool = False,
) -> None:
    """Write a small fake wx-admin1-v1 dataset (real outlines, made-up values)."""
    from ..external import fetch
    from .sample import make_sample

    cfg, paths = _setup(config, verbose)
    for name in ("ne_10m_admin_1_states_provinces.zip", "ne_10m_admin_0_countries.zip"):
        fetch(name, paths.external)
    sizes = make_sample(paths.external, cfg, out)
    typer.echo(f"{len(sizes)} files, {sum(sizes.values()) / 1e3:.0f} kB in {out}")
