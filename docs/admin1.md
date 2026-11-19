# States and provinces

Per-region white-Christmas statistics for administrative level 1 (states, provinces, regions,
counties) worldwide, computed from the same ERA5-Land cube and indicators as the map.

- Code: `src/whitexmas/admin1/`, tests in `tests/test_admin1*.py`.
- Run: `uv run whitexmas admin1 run` (or the steps `weights`, `stats`, `export`).
- Output: `$WHITEXMAS_DATA/products/admin1/` (web files, CSV, manifest fragment); the main
  `whitexmas export` stages the web files into its web-out and lists them in the manifest.
- Web data: contract **v1.6** (below), format `wx-admin1-v1`.

## Boundaries

**Natural Earth 10m admin-1 states and provinces** (version 5.1.1, public domain), the same
family and scale as the country borders the site already uses
(`ne_10m_admin_0_countries`). 4,596 features in 253 countries, downloaded by the pipeline into
`$WHITEXMAS_DATA/external/` with its SHA-256 in `external/manifest.json`.

Natural Earth is not uniform: for five countries it ships units *below* the first level. Those
are dissolved to the first level (`admin1.dissolve` in `config/pipeline.yaml`):

| Country | Natural Earth features | Dissolved to | Id |
| --- | --- | --- | --- |
| Italy | 110 provinces | 20 regions (`region`) | ISO 3166-2 (`IT-25` Lombardy) |
| France | 101 départements | 13 metropolitan + 5 overseas regions | ISO (`FR-ARA`) |
| Spain | 52 provinces | 17 autonomous communities + Ceuta, Melilla | ISO (`ES-CT`) |
| United Kingdom | 232 local authorities | England, Scotland, Wales, Northern Ireland | ISO (`GB-SCT`) |
| Slovenia | 193 municipalities | 12 statistical regions | `SVN-<NAME>` (no ISO code) |

Everything else is used as published: 16 German Länder, 50 US states + DC, 13 Canadian
provinces and territories, 47 Japanese prefectures, 9 Austrian states, 18 Finnish regions,
86 Russian federal subjects (as drawn by Natural Earth), and so on. Some countries keep fine units because that *is* their
first level (Latvian municipalities, Ugandan districts, Irish counties); those regions are
small and often flagged `low_res`.

**Result: 3,988 regions in 252 countries.** Seven admin-0 units have no admin-1 feature (Bajo
Nuevo Bank, Brazilian Island, Bir Tawil, Cyprus U.N. buffer zone, Scarborough Reef, Serranilla
Bank, Southern Patagonian Ice Field); each is one region, flagged `admin0`.

**Ids.** ISO 3166-2 where Natural Earth's code is well formed (`CC-XXX`) and unique, else
Natural Earth's `adm1_code` reduced to letters, digits and `-` (155 features share an ISO code
in Natural Earth, mostly Philippine cities, Malagasy regions, Bosnian cantons and Irish city
councils; another 188 have placeholder codes such as `XK-X02~` in Kosovo). Dissolved groups
use the ISO code of the group (config). Admin-0 fallbacks use Natural Earth's `ADM0_A3`.
**Names:** Natural Earth `name_en` (Bavaria, Tyrol), the local form in `name_local` when it
differs (Bayern, Tirol).

**Country key:** the same ISO 3166-1 alpha-3 key as `regions.json` (`ISO_A3`, else
`ISO_A3_EH`, else `ADM0_A3`), so a region's `country` joins the country table directly.

**geoBoundaries** (ADM1) was considered. It has proper first-level units for Italy, France,
Spain and the UK, but its licences differ by country (several are CC BY-SA or
non-commercial), its sources and vintages are mixed, and it has no worldwide ISO-coded
single file. Natural Earth's gaps that matter are the five sub-level countries above, and
dissolving fixes them, so geoBoundaries is not used.

## Which cells belong to a region

ERA5-Land cells are 0.1° (about 9 × 11 km in mid-latitudes); many regions are only a few cells
across, so a cell is not simply "in" or "out":

- **Cell fractions.** Each region gets the share of every cell it covers (0–1). A cell on a
  border is split between the regions by those shares, so no cell is counted twice and no
  region loses its edge cells. Regions whose bounding box spans at most 400 cells (city
  states, islands, small counties) use the exact polygon-cell intersection; larger regions
  are rasterised on a grid 10 times finer per axis (4 times for continent-sized regions such
  as Antarctica or Nunavut), so a fraction is accurate to 1 % of a cell, and only edge cells
  are affected by that rounding.
- **Area weight** = fraction × cos(latitude): a cell's area shrinks towards the poles.
- **Land only.** Only land cells count (land-sea mask ≥ 0.5 and lake cover < 0.5, as on the
  map). The coastal part of a region that ERA5-Land classes as sea simply has no cells.
- **Glaciers excluded**, as in the country table: cells flagged glacier on the map (hatched)
  are left out of every average; `glacier_pct` gives their share of the region's land. A
  region whose land is all glacier has no values (`all_glacier`).
- **No land cell at all** (small islands, reefs, a thin coastal strip): the region takes the
  nearest land cell within 2 cells (about 20 km) of its interior point or of any cell it
  touches, flagged `nearest_cell`; with none that close, it has no values (`no_land`).
- **Small regions** with fewer than 3 cells' worth of land (sum of fractions) are flagged
  `low_res`: their value rests on a handful of 9 km cells and can be off for a small valley
  or island. Nothing is silently NaN: every value that cannot be computed is `null`, and
  `flags` says why.

## Statistics

For both thresholds (calibrated 5 cm default, raw 1 cm) and all three definitions:

| Statistic | How |
| --- | --- |
| Probability per window | area-weighted mean of the map's cell probabilities, for the full period, the two normals and every decade (the same windows the map ships) |
| Change | 1996–2025 minus 1961–1990 of the regional values (pp) |
| Yearly series 1950–2025 | per year, the area-weighted share of the region that was white (%) |
| Trend | ordinary least squares slope of the yearly series, pp per decade (identical to the area-weighted mean of the cells' trends) |
| Significance | Mann-Kendall test on the yearly regional series (tie-corrected); `trend_p < 0.1` counts as significant, as on the map |
| Spread | area share with p ≥ 50 % (`share50`), and the 5th and 95th percentiles of the cell probabilities weighted by area (`p5`, `p95`), per window |
| Elevation | ERA5-Land cell mean elevation: area-weighted mean, and min and max over the region's land cells that lie at least half inside it |
| Population-weighted probability | see below, per window, plus its change |

The regional trend test runs on the regional series, not by counting significant cells: a
region where most cells drift down slightly can be clearly significant as a whole even when
few of its cells are on their own.

**Projections** (+1.5, +2, +3 °C; calibrated threshold, Christmas Day; method B as in
[projections.md](projections.md)): for each of the 19 CMIP6 models, the model's projected
probability per cell (the map's own log-odds transfer onto the 1996–2025 ERA5-Land baseline)
is averaged over the region; the 10th, 50th and 90th percentiles are then taken across the
models' regional means. Agreement: at least two thirds of the models agree on the direction of
the region's change (decrease, increase, or no change within ±0.05 pp). This is the
statistically right order: the median of regional means, not the regional mean of per-cell
medians, which would mix models across cells. The raw 1 cm view has no projections, as on the
map.

### Headline number and the population view

**The headline is the area-weighted value** (the same weighting as the country table): "how
much of the region has a white Christmas". A state can have a snowy mountain and a green
valley, so the panel shows the spread next to it, and a **population-weighted value
alongside**: "the white-Christmas probability where people live".

Population source: **GeoNames `cities15000`** (CC BY 4.0, already downloaded for the place
search): every place with at least 15,000 inhabitants is weighted by its population and takes
the value of the same cell as in `places.json` (its own cell, or the nearest land cell within
2 cells). Chosen because it is already part of the pipeline, open, small, and makes the
regional number consistent with the city values people search for. Limitations: it ignores
rural people and small towns, so in regions without such a place the population-weighted
value is `null` (`places` = 0), and it leans towards the largest city. A gridded population
(for example GHS-POP, CC BY 4.0, ~ 1 km) would count everyone; it is a 400 MB+ download and
could replace the places later without changing the schema.

## Web data: contract v1.6 (proposal, additive)

Optional, like projections: the site shows states and provinces only when the manifest lists
them, and must work without them.

### manifest.json

```jsonc
"admin1": {
  "available": true,
  "format": "wx-admin1-v1",
  "index": "admin1/index.json",
  "boundaries": "admin1/boundaries.json",
  "country": "admin1/c/{country}.json",     // {country} = the country key from index.json
  "data_version": "2025.1",
  "built": "2026-11-19T18:00:00Z",
  "build_hash": "abc123def456"
}
```

### admin1/index.json (always loaded with the layer; ~200 kB gzip)

```jsonc
{
  "format": "wx-admin1-v1", "contract": "1.6",
  "data_version": "2025.1", "built": "…", "build_hash": "…",
  "threshold": "calibrated",                  // values below: default threshold …
  "definition": "christmas_day",              // … and default definition
  "windows": { "p_full": "1950_2025", "p_then": "1961_1990", "p_now": "1996_2025" },
  "trend_alpha": 0.1,                         // trend_p < trend_alpha = significant
  "headline": "area",                         // p_* are area-weighted; *_pop population-weighted
  "fields": ["id", "name", "country", "lon", "lat", "area_km2", "flags",
             "p_full", "p_then", "p_now", "change", "trend", "trend_p", "p_now_pop",
             "p_then_raw", "p_now_raw", "p_gwl1.5", "p_gwl2.0", "p_gwl3.0"],
  "rows": [["DE-BY", "Bavaria", "DEU", 11.3, 48.9, 70550, [], 33.0, 41.0, 26.0, -15.0,
            -2.31, 0.012, 21.4, 70.1, 61.0, 21.0, 18.0, 11.0]],
  "countries": { "DEU": { "name": "Germany", "regions": 16 } },
  "flags": { "low_res": "fewer than 3 land cells …", "…": "…" },  // texts for every flag
  "attribution": "Borders: Natural Earth (public domain). Places: GeoNames (CC BY 4.0)."
}
```

- One row per region, in the order of `boundaries.json` feature ids (row k ↔ feature id k).
- `lon`, `lat`: a point inside the region (for labels and search results); `area_km2`: the
  polygon area.
- `trend`: pp/decade over the full period; `trend_p`: Mann-Kendall p (the site decides how to
  show insignificant trends, e.g. greyed out, like the hatching on the map).
- `p_then_<id>`/`p_now_<id>`: the other thresholds (today `raw`), as in `regions.json`.
- `p_gwl<level>`: median projected probability (calibrated threshold); absent when
  projections are not available.
- Any value can be `null`; `flags` (array of strings) says why.

**Flags:** `admin0` (no admin-1 subdivision in the source: the region is the whole admin-0
unit), `low_res` (fewer than 3 land cells), `nearest_cell` (no land cell inside: nearest land
cell's value), `no_land` (no values), `all_glacier` (no values). `index.flags` carries a
sentence for each, so the site can show it without hard-coding.

### admin1/boundaries.json (~1.4 MB gzip)

GeoJSON `FeatureCollection`; each feature has a numeric `id` (its row in `index.json`, for
MapLibre `feature-state`) and `properties: { "id": "DE-BY", "country": "DEU" }`. Simplified
with GEOS coverage simplification at 0.03° (about 3 km; shared borders stay identical, no gaps
or slivers between neighbours), parts smaller than 30 km² dropped (a region keeps at least its
largest part), coordinates rounded to 3 decimals (≈ 100 m). Good for zoom 0–7, which covers the
map's raster zooms (0–6). Polygons crossing the antimeridian are split there (as in Natural
Earth). The file is plain JSON; GitHub Pages serves it gzip-compressed.

PMTiles vector tiles were considered: the site already uses PMTiles for rasters, but building
vector tiles needs tippecanoe, which is not available on the pipeline's Windows host; a single
GeoJSON within 1.5 MB gzip is simpler and is enough for 4,000 polygons.

### admin1/c/{country}.json (loaded when a region is opened; ≤ ~150 kB gzip)

```jsonc
{
  "format": "wx-admin1-v1", "contract": "1.6", "data_version": "2025.1", "built": "…",
  "build_hash": "…",
  "country": "DEU", "country_name": "Germany",
  "years": [1950, 2025],
  "thresholds": ["calibrated", "raw"],        // ids of manifest.thresholds, default first
  "definitions": ["christmas_day", "all_three_days", "any_day"],
  "windows": ["1950_2025", "1961_1990", "1996_2025", "2016_2025", "…", "1956_1965"],
  "windows_then_now": ["1961_1990", "1996_2025"],
  "trend_alpha": 0.1,
  "spread_share_pct": 50,
  "projections": { "threshold": "calibrated", "definition": "christmas_day",
                   "gwls": [1.5, 2.0, 3.0], "baseline_window": "1996_2025",
                   "models": ["ACCESS-ESM1-5", "…"] },   // null when not available
  "regions": [{
    "id": "DE-BY", "name": "Bavaria", "name_local": "Bayern", "type": "State",
    "flags": [],
    "lon": 11.3, "lat": 48.9, "bbox": [8.98, 47.27, 13.84, 50.56],
    "area_km2": 70550,          // polygon area
    "land_km2": 69800,          // land cells used (glaciers excluded)
    "cells": 840.2,             // land cells used, as a sum of cell fractions
    "glacier_pct": 0.0,         // glacier share of the region's land
    "elev_m": [107, 512, 2341], // ERA5-Land cell elevation: min, area-weighted mean, max
    "places": 41, "places_pop": 5400000,   // GeoNames places behind the *_pop values
    "stats": {
      "calibrated": {
        "christmas_day": {
          "p":       [33.0, 41.0, 26.0, …],   // per window, in the order of "windows"
          "p_pop":   [24.0, 30.1, 17.9, …],   // population-weighted, per window
          "share50": [18.0, 30.2, 12.5, …],   // % of the area with p >= 50 %, per window
          "p5":      [ 9.2, 13.0,  6.7, …],   // 5th percentile of cell p (area-weighted)
          "p95":     [83.0, 90.0, 76.7, …],   // 95th percentile
          "change": -15.0, "change_pop": -12.2,  // p_now - p_then (pp)
          "trend": -2.31, "trend_p": 0.012,       // pp/decade, Mann-Kendall p
          "series": [55.2, 12.0, …]               // % of the area white, per year
        },
        "all_three_days": { … }, "any_day": { … }
      },
      "raw": { … }
    },
    "proj": {                     // null when projections are not available or no baseline
      "baseline": 26.0,           // 1996–2025, calibrated, Christmas Day
      "p10": [16.0, 13.1, 8.0], "p50": [21.0, 18.0, 11.0], "p90": [27.3, 25.0, 19.9],
      "change": [-5.0, -8.0, -15.0],          // p50 - baseline (pp)
      "agree": [true, true, true],            // >= 2/3 of models agree on the direction
      "n_models": 19,
      "p50_pop": [14.1, 12.2, 7.3]
    }
  }]
}
```

All probabilities are % with one decimal; `null` where not computable (see `flags`).

### Sample fixture

`tests/fixtures/admin1_sample/admin1/` holds a small, **clearly fake** dataset in exactly this
format: real Natural Earth outlines for Austria, Germany, Finland, Italy, Liechtenstein (every
region `low_res`) and the Cyprus buffer zone (`admin0` + `no_land`, all values `null`), values
made up (a smooth function of latitude), `data_version: "sample"`. Regenerate with
`uv run whitexmas admin1 sample`. The website copies it into its own fixture tree; it is never
real data.

## Limitations

- **Resolution.** A 0.1° cell is about 9 km; small regions (`low_res`) rest on a handful of
  cells, and mountains are smoothed (each cell has one mean elevation), so a valley and its
  peaks share a value. `p5`/`p95` and `share50` show how much a region varies at that
  resolution, not at the scale of a town.
- **UTC day, calibration scope.** As for the map (methodology: limitations): daily means are
  UTC days, and the 5 cm calibration was checked against stations in Europe and North
  America only.
- **Borders.** Natural Earth 1:10m borders are generalised and some are disputed; the regions
  are statistical units, not a statement about sovereignty.
- **Population weighting** uses places with at least 15,000 inhabitants only (see above).
