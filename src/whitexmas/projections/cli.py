"""``whitexmas projections ...``: future white-Christmas probability at global warming levels.

Steps, each reading the one before:

  changes   per-model counts and log-odds changes on each model grid
  validate  model bias against ERA5-Land (skill table) and, with the snow cube, the hindcast
  ensemble  regrid, apply to the ERA5-Land baseline, p10/median/p90 and agreement
  export    PMTiles layers, wx-proj-v1 point tiles, manifest fragment, COGs
  run       all of the above

Inputs come from ``scripts/projections/cmip6_select.py`` and ``cmip6_download.py``.
Registered in the main CLI with ``app.add_typer(projections.cli.app, name="projections")``;
until then ``uv run python -m whitexmas.projections ...`` works the same.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Annotated

import typer

from ..paths import DataPaths
from .settings import ProjPaths, ProjSettings

app = typer.Typer(add_completion=False, no_args_is_help=True, help=__doc__)

Models = Annotated[list[str] | None, typer.Option("--model", "-m", help="Only these models")]
Exclude = Annotated[list[str] | None, typer.Option("--exclude", "-x", help="Drop these models")]
Threshold = Annotated[float, typer.Option(help="SWE threshold in kg m-2 (1 cm at 250 kg m-3)")]
Pool = Annotated[int, typer.Option(help="Pool centre days within +/- this of 25 Dec (0 = off)")]

log = logging.getLogger(__name__)


def _setup(verbose: bool, threshold: float, pool: int, exclude: list[str] | None):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    paths = DataPaths.from_env()
    s = ProjSettings(threshold_kg_m2=threshold, pool_days=pool, exclude=tuple(exclude or ()))
    return paths, ProjPaths.from_data(paths), s


def _era5_land(paths: DataPaths):
    from .baseline import load_baseline

    try:
        return load_baseline(paths, "christmas_day").land
    except Exception:  # noqa: BLE001 - only used where a model has no sftlf
        return None


@app.command()
def changes(
    model: Models = None,
    threshold: Threshold = 2.5,
    pool: Pool = 7,
    force: bool = False,
    verbose: bool = False,
) -> None:
    """Per-model white-Christmas counts and log-odds changes (models with complete downloads)."""
    from .changes import compute_model, models_ready

    paths, pp, s = _setup(verbose, threshold, pool, None)
    ready = models_ready(pp, s.baseline[0])
    todo = [m for m in (model or ready) if m in ready]
    skipped = sorted(set(model or []) - set(ready))
    if skipped:
        typer.echo(f"downloads incomplete, skipped: {', '.join(skipped)}")
    land = _era5_land(paths)
    for m in todo:
        out = pp.models / f"{m}.nc"
        if out.exists() and not force and _same_settings(out, s):
            continue
        compute_model(pp, m, s, land)
    typer.echo(f"{len(todo)} models: {', '.join(todo)}")


def _same_settings(path: Path, s: ProjSettings) -> bool:
    import xarray as xr

    with xr.open_dataset(path) as ds:
        return all(
            ds.attrs.get(f"setting_{k}") == str(v)
            for k, v in s.as_attrs().items()
            if k != "exclude"
        )


@app.command()
def validate(
    model: Models = None,
    threshold: Threshold = 2.5,
    pool: Pool = 7,
    period: Annotated[
        str | None, typer.Option(help="ERA5-Land comparison years, e.g. 1961-1990")
    ] = None,
    hindcast: Annotated[
        bool, typer.Option(help="Also run the 1961-1990 -> 1996-2025 hindcast")
    ] = True,
    verbose: bool = False,
) -> None:
    """Bias against ERA5-Land per model (skill table) and the hindcast Brier skill."""
    from . import validation

    paths, pp, s = _setup(verbose, threshold, pool, None)
    per = tuple(int(x) for x in period.split("-")) if period else None
    try:
        res = validation.validate(paths, s, model, per)
    except FileNotFoundError as e:
        typer.echo(f"validation skipped, selection.json left unchanged: {e}")
        res = None
    if res is not None:
        for r in res["models"]:
            typer.echo(json.dumps(r))
        amount = validation.snow_amount(paths, s, model, per or (1961, 1990))
        era_med = amount["era5_median_swe_kg_m2"]
        if era_med is None:
            typer.echo("snow amount: no ERA5-Land raw files for that period, check skipped")
        else:
            typer.echo(f"snow amount (ERA5-Land median {era_med:.1f} kg m-2):")
            for r in amount["models"]:
                typer.echo(json.dumps(r))
        stem = "skill" if per is None or per == tuple(s.baseline) else f"skill_{per[0]}_{per[1]}"
        sel = validation.select_models(pp.validation, f"{stem}.json")
        typer.echo(f"kept {len(sel['kept'])}: {', '.join(sel['kept'])}")
        for m, why in sel["dropped"].items():
            typer.echo(f"dropped {m}: {why}")
    if hindcast:
        try:
            hc = validation.hindcast(paths, s, model)
            typer.echo(json.dumps({k: v for k, v in hc.items() if k != "reliability"}, indent=1))
        except FileNotFoundError as e:
            typer.echo(f"hindcast skipped: {e}")


@app.command()
def ensemble(
    model: Models = None,
    exclude: Exclude = None,
    threshold: Threshold = 2.5,
    pool: Pool = 7,
    definition: Annotated[list[str] | None, typer.Option("--definition", "-d")] = None,
    verbose: bool = False,
) -> None:
    """Regrid, apply to the ERA5-Land baseline and compute ensemble statistics."""
    from .ensemble import build_ensemble

    paths, pp, s = _setup(verbose, threshold, pool, exclude)
    build_ensemble(paths, s, model, definition)


@app.command()
def export(
    web_out: Annotated[
        Path | None,
        typer.Option(
            help="Also stage into this web data folder (real builds always render into "
            "products/projections/web; the pipeline's export stages from there). Required for a "
            "placeholder preview."
        ),
    ] = None,
    allow_placeholder: Annotated[
        bool,
        typer.Option(
            help="Allow a local preview built on the placeholder baseline "
            "(needs a --web-out other than web/static/data)"
        ),
    ] = False,
    patch_manifest: Annotated[
        bool, typer.Option(help="Also merge into an existing web_out/manifest.json")
    ] = False,
    cogs: bool = True,
    workers: Annotated[int | None, typer.Option(help="Tile rendering processes")] = None,
    verbose: bool = False,
) -> None:
    """Write projection layers, wx-proj-v1 point tiles, the manifest fragment and COGs."""
    from .export import export_projections

    paths, *_ = _setup(verbose, 2.5, 7, None)
    res = export_projections(
        paths,
        web_out,
        cogs=cogs,
        allow_placeholder=allow_placeholder,
        patch=patch_manifest,
        workers=workers,
    )
    typer.echo(
        f"{len(res['layers'])} layers, {res['points']['tiles']} point tiles in "
        f"{res['rendered_into']}"
        + (f", staged into {res['staged_into']}" if res["staged_into"] else "")
        + (" (PLACEHOLDER baseline)" if res["placeholder"] else "")
    )


@app.command()
def run(
    exclude: Exclude = None,
    threshold: Threshold = 2.5,
    pool: Pool = 7,
    web_out: Annotated[
        Path | None,
        typer.Option(
            help="Also stage into this web data folder (real builds always render into "
            "products/projections/web; the pipeline's export stages from there). Required for a "
            "placeholder preview."
        ),
    ] = None,
    allow_placeholder: bool = False,
    verbose: bool = False,
) -> None:
    """changes -> validate -> ensemble -> export."""
    changes(model=None, threshold=threshold, pool=pool, force=False, verbose=verbose)
    validate(
        model=None, threshold=threshold, pool=pool, period=None, hindcast=True, verbose=verbose
    )
    ensemble(
        model=None,
        exclude=exclude,
        threshold=threshold,
        pool=pool,
        definition=None,
        verbose=verbose,
    )
    export(
        web_out=web_out,
        allow_placeholder=allow_placeholder,
        patch_manifest=False,
        cogs=True,
        workers=None,
        verbose=verbose,
    )
