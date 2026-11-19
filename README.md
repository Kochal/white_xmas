# White Christmas

How likely is a white Christmas where you live, and how has that changed since 1950?

This repository holds a reproducible data pipeline and a static website that answer that question
for every land cell on Earth, using the ERA5-Land reanalysis (0.1°, about 9 km) for 1950–2025.

- `src/whitexmas/`: the Python pipeline (download → ingest → indicators → export).
- `web/`: the website (SvelteKit, MapLibre, PMTiles), built from the files the pipeline exports.
- `docs/methodology.md`: data, definitions, statistics and limitations, in plain language.
- `legacy/`: the original notebook and download script, kept for reference only.

## Definitions

A year counts as a *white Christmas* in a grid cell when ERA5-Land's daily-mean snow depth reaches a
threshold. The default is **5 cm**, calibrated so that it matches at least 1 cm measured at
weather stations (`whitexmas stations`); the raw **1 cm** view is offered too. Three rules:

| id | rule |
| --- | --- |
| `christmas_day` (default) | on 25 December |
| `all_three_days` | on each of 24, 25 and 26 December (the German weather service's rule) |
| `any_day` | on at least one of 24, 25 or 26 December |

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/) and a free
[Copernicus Climate Data Store](https://cds.climate.copernicus.eu/) account with its API key in
`~/.cdsapirc` (accept the ERA5-Land licence on the dataset page once).

```bash
uv sync
export WHITEXMAS_DATA=/path/to/white_xmas_data   # raw data and products live here, outside git
uv run whitexmas build                           # all steps below, in order
```

Or step by step:

| Command | Does | Output (under `$WHITEXMAS_DATA`) |
| --- | --- | --- |
| `whitexmas download` | ERA5-Land daily-mean snow depth, Dec 24–26, 1950–2025, global (one CDS request per year, ~6 MB each) plus land-sea mask, orography and glacier mask | `era5land/` + `manifest.json` (request, CDS job id, SHA-256 per file) |
| `whitexmas ingest` | NetCDF → one Zarr cube `snow_depth_cm[year, day, lat, lon]` (int16, whole cm, −1 = nodata) and masks | `interim/snow_cube.zarr` |
| `whitexmas indicators` | probability and valid years per definition and window, change between the normals, trend + Mann-Kendall p, glacier flag, for every threshold | `interim/indicators.zarr` (default), `interim/indicators__raw.zarr` |
| `whitexmas export --web-out web/static/data` | web data per the web data contract (manifest, PMTiles, point tiles, places, regions), COGs, the data bundle | `web/static/data/`, `products/cog/`, `products/whitexmas-web-data-<version>.tar.gz` |
| `whitexmas stations` | checks the snow thresholds against GHCN-Daily weather stations, selected automatically across the Northern Hemisphere (`--mode list`: the hand-picked D-17 list) | `products/stations/` (`snow_variable_check.html`, `stations_global.csv`/`.json`); list mode: `products/sanity/` |
| `whitexmas sanity --legacy-tif <tif>` | city values for every threshold, the station-check summary and a comparison with the legacy map | `products/sanity/` |

`WHITEXMAS_DATA` defaults to `white_xmas_data` next to the repository. Every step is idempotent:
it records a fingerprint of its inputs and configuration and skips work that is already up to
date (`--force` redoes it). A full rebuild after the download takes about 10 minutes.

Configuration (years, thresholds, definitions, windows, glacier rule, stations, export settings) lives in
`config/pipeline.yaml`. The method is described in [`docs/methodology.md`](docs/methodology.md).

## Development

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest
```

## Data credit and licence

- Code: MIT (`LICENSE`).
- Data products: CC BY 4.0 (`LICENSE-DATA`).
- Contains modified Copernicus Climate Change Service information (ERA5-Land, 2026). Neither the
  European Commission nor ECMWF is responsible for any use that may be made of the Copernicus
  information or data it contains.
  Muñoz Sabater, J. (2019, updated): ERA5-Land hourly data from 1950 to present. Copernicus Climate
  Change Service (C3S) Climate Data Store (CDS). DOI: 10.24381/cds.e2161bac
- Place names: [GeoNames](https://www.geonames.org/) (CC BY 4.0).
- Country boundaries: [Natural Earth](https://www.naturalearthdata.com/) (public domain).
