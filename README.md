# White Christmas

How likely is a white Christmas where you live, and how has that changed since 1950?

This repository holds a reproducible data pipeline and a static website that answer that question
for every land cell on Earth, using the ERA5-Land reanalysis (0.1°, about 9 km) for 1950–2025.

- `src/whitexmas/`: the Python pipeline (download → ingest → indicators → export).
- `web/`: the website (SvelteKit, MapLibre, PMTiles), built from the files the pipeline exports.
- `docs/methodology.md`: data, definitions, statistics and limitations, in plain language.
- `legacy/`: the original notebook and download script, kept for reference only.

## Definitions

A year counts as a *white Christmas* in a grid cell when the daily-mean snow depth is at least 1 cm:

| id | rule |
| --- | --- |
| `christmas_day` (default) | on 25 December |
| `all_three_days` | on each of 24, 25 and 26 December (the German weather service's rule) |
| `any_day` | on at least one of 24, 25 or 26 December |

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/) and a free
[Copernicus Climate Data Store](https://cds.climate.copernicus.eu/) account with its API key in
`~/.cdsapirc` (you also need to accept the ERA5-Land licence on the dataset page once).

```bash
uv sync
export WHITEXMAS_DATA=/path/to/white_xmas_data   # where raw data and products go (outside git)
uv run whitexmas download      # ERA5-Land daily snow depth, Dec 24–26, 1950–2025 (~100 MB/year)
uv run whitexmas ingest        # NetCDF → one Zarr snow cube
uv run whitexmas indicators    # probabilities, change, trend, significance
uv run whitexmas export --web-out web/static/data
# or everything at once:
uv run whitexmas build
```

`WHITEXMAS_DATA` defaults to `../white_xmas_data` next to the repository. Every step is
idempotent: re-running it skips work whose inputs have not changed.

Configuration (years, threshold, definitions, windows, colour scales) lives in
`config/pipeline.yaml`.

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
