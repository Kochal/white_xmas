"""Command-line entry point: ``whitexmas download | ingest | indicators | export | build``."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from .config import Config
from .paths import DataPaths

app = typer.Typer(add_completion=False, no_args_is_help=True, help=__doc__)

try:  # `whitexmas projections …`, once the projections package is on this branch
    from .projections.cli import app as projections_app

    app.add_typer(projections_app, name="projections")
except ModuleNotFoundError as e:  # pragma: no cover - depends on which branch is checked out
    # Only "the projections package is absent" is expected; re-raise anything else.
    if e.name not in ("whitexmas.projections", "whitexmas.projections.cli"):
        raise

ConfigOpt = Annotated[Path | None, typer.Option("--config", "-c", help="Path to pipeline.yaml")]


def _setup(config: Path | None, verbose: bool = False) -> tuple[Config, DataPaths]:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # cdsapi/ecmwf clients are chatty at INFO.
    logging.getLogger("ecmwf.datastores").setLevel(logging.WARNING)
    logging.getLogger("multiurl").setLevel(logging.WARNING)
    cfg = Config.load(config)
    paths = DataPaths.from_env()
    return cfg, paths


def _parse_years(years: str | None, cfg: Config) -> list[int] | None:
    if not years:
        return None
    out: list[int] = []
    for part in years.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


@app.command()
def info(config: ConfigOpt = None) -> None:
    """Show configuration and data paths."""
    cfg, paths = _setup(config)
    typer.echo(f"data root: {paths.root}")
    typer.echo(f"years:     {cfg.first_year}-{cfg.last_year}")
    typer.echo(f"windows:   {', '.join(w.id for w in cfg.windows())}")
    typer.echo(f"defs:      {', '.join(cfg.definition_ids)}")


@app.command()
def download(
    config: ConfigOpt = None,
    years: Annotated[str | None, typer.Option(help="e.g. 1950-1960,2025")] = None,
    parallel: Annotated[int, typer.Option(help="CDS requests in flight")] = 6,
    static_only: bool = False,
    verbose: bool = False,
) -> None:
    """Download ERA5-Land daily snow depth (Dec 24-26) and static fields from the CDS."""
    from .download import download_all

    cfg, paths = _setup(config, verbose)
    res = download_all(cfg, paths, _parse_years(years, cfg), parallel, static_only)
    failed = {k: v for k, v in res.items() if v.startswith("failed")}
    typer.echo(f"{len(res) - len(failed)} ok, {len(failed)} failed")
    if failed:
        for k, v in sorted(failed.items()):
            typer.echo(f"  {k}: {v}")
        raise typer.Exit(1)


@app.command()
def ingest(config: ConfigOpt = None, force: bool = False, verbose: bool = False) -> None:
    """Build the Zarr snow cube and masks from the downloaded NetCDFs."""
    from .ingest import ingest as run

    cfg, paths = _setup(config, verbose)
    run(cfg, paths, force=force)


@app.command()
def indicators(
    config: ConfigOpt = None,
    force: bool = False,
    threshold: Annotated[
        str | None, typer.Option(help="Only this threshold id (e.g. calibrated, raw)")
    ] = None,
    verbose: bool = False,
) -> None:
    """Compute probabilities, change, trend and significance for every definition and window,
    for every configured snow-depth threshold."""
    from .indicators import compute_all

    cfg, paths = _setup(config, verbose)
    compute_all(cfg, paths, force=force, only=threshold)


@app.command()
def export(
    config: ConfigOpt = None,
    web_out: Annotated[Path, typer.Option(help="Web data output folder")] = Path("web/static/data"),
    force: bool = False,
    workers: Annotated[
        int | None, typer.Option(help="Tile render processes (default: CPUs - 2, max 8)")
    ] = None,
    max_layers: Annotated[
        int | None,
        typer.Option(help="Render at most N map layers, then stop; re-run to resume"),
    ] = None,
    verbose: bool = False,
) -> None:
    """Export web data (manifest, PMTiles, point tiles, places, regions), COGs and the bundle."""
    from .export import export_all

    cfg, paths = _setup(config, verbose)
    res = export_all(cfg, paths, web_out, force=force, workers=workers, max_layers=max_layers)
    if res.get("remaining_layers"):
        typer.echo(f"{res['remaining_layers']} layers left; run export again to continue")


@app.command()
def sanity(
    config: ConfigOpt = None,
    legacy_tif: Annotated[
        Path | None, typer.Option(help="Legacy any-day probability GeoTIFF (1980-2024)")
    ] = None,
    out: Annotated[Path | None, typer.Option(help="Output folder")] = None,
    verbose: bool = False,
) -> None:
    """Write the sanity report (city values, legacy comparison)."""
    from .sanity import build_report

    cfg, paths = _setup(config, verbose)
    build_report(cfg, paths, legacy_tif, out or paths.products / "sanity")


@app.command()
def stations(config: ConfigOpt = None, verbose: bool = False) -> None:
    """Check snow thresholds against GHCN-Daily weather stations (calibrates threshold_cm)."""
    from .stations import run

    cfg, paths = _setup(config, verbose)
    res = run(cfg, paths)
    cal = res["calibration"]
    typer.echo(
        f"{len(res['stations'])} stations ({cal['n_calibration']} for calibration); "
        f"best whole-cm threshold: {cal['best_cm']} cm "
        f"(bias {cal['stats'][cal['best_cm']]['bias_pp']:+.1f} pp, "
        f"MAE {cal['stats'][cal['best_cm']]['mae_pp']:.1f} pp)"
    )


@app.command()
def build(
    config: ConfigOpt = None,
    web_out: Annotated[Path, typer.Option(help="Web data output folder")] = Path("web/static/data"),
    skip_download: bool = False,
    workers: Annotated[int | None, typer.Option(help="Tile render processes")] = None,
    verbose: bool = False,
) -> None:
    """Run every step in order; each step skips work whose inputs are unchanged."""
    if not skip_download:
        download(config=config, years=None, parallel=6, static_only=False, verbose=verbose)
    ingest(config=config, force=False, verbose=verbose)
    indicators(config=config, force=False, threshold=None, verbose=verbose)
    export(
        config=config,
        web_out=web_out,
        force=False,
        workers=workers,
        max_layers=None,
        verbose=verbose,
    )


if __name__ == "__main__":
    app()
