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
| Significance | Mann-Kendall test on the yearly regional series (tie-corrected), `trend_p`; and the Benjamini-Hochberg adjusted `trend_q` across all testable regions (see below). A **clear trend** is `trend_q < 0.1` |
| Spread | area share with p ≥ 50 % (`share50`), and the 5th and 95th percentiles of the cell probabilities weighted by area (`p5`, `p95`), per window |
| Elevation | ERA5-Land cell mean elevation: area-weighted mean, and min and max over the region's land cells that lie at least half inside it |
| Population-weighted probability | see below, per window, plus its change |

The regional trend test runs on the regional series, not by counting significant cells: a
region where most cells drift down slightly can be clearly significant as a whole even when
few of its cells are on their own.

**Many regions, many tests.** `trend_p` is a per-region test at α = 0.1: among regions whose
white-Christmas chance has not really changed, about 1 in 10 still passes it by chance. With
about 1,600 testable regions that is around 160 false "trends", so `trend_p < 0.1` alone must
not be read as "this region has a clear trend". Each region therefore also gets
**`trend_q`**, the Benjamini-Hochberg adjusted p-value computed across all testable regions
(per threshold and definition): among the regions with `trend_q < 0.1`, at most about 10 % are
expected to be false discoveries. Testable means a series with at least 3 years that is not
constant; the ~2,200 regions that are always 0 % or always 100 % (Mann-Kendall p = 1 by
construction) cannot be false discoveries and are not counted (`trend_q` is `null` for them).
Benjamini-Hochberg remains valid when tests are positively dependent, which is the case here:
neighbouring regions share the same weather, so their tests are not independent. **The site
should use `trend_q < 0.1` for "clear trend"** and may show `trend_p` as detail. Real data
(calibrated, Christmas Day): 1,583 testable regions, 404 with `trend_p < 0.1`, 75 with
`trend_q < 0.1` (Bavaria q = 0.03, Scotland 0.10; Tyrol p = 0.009 but q = 0.15; Lombardy
p = 0.03, q = 0.24). Lag-1 autocorrelation of the regional series is small or negative
(Bavaria −0.22, Minnesota −0.18, Hokkaido 0.13; independent review), so Mann-Kendall without
prewhitening is adequate, slightly conservative where it is negative.

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

### admin1/index.json (always loaded with the layer; 132 kB gzip)

```jsonc
{
  "format": "wx-admin1-v1", "contract": "1.6",
  "data_version": "2025.1", "built": "…", "build_hash": "…",
  "threshold": "calibrated",                  // values below: default threshold …
  "definition": "christmas_day",              // … and default definition
  "windows": { "p_full": "1950_2025", "p_then": "1961_1990", "p_now": "1996_2025" },
  "trend_alpha": 0.1,                         // trend_q < trend_alpha = clear trend
  "headline": "area",                         // p_* are area-weighted; *_pop population-weighted
  "fields": ["id", "name", "country", "lon", "lat", "area_km2", "flags",
             "p_full", "p_then", "p_now", "change", "trend", "trend_p", "p_now_pop",
             "p_then_raw", "p_now_raw", "p_gwl1.5", "p_gwl2.0", "p_gwl3.0",
             "type", "trend_q"],
  "rows": [["DE-BY", "Bavaria", "DEU", 11.3, 48.9, 70550, [], 33.0, 41.0, 26.0, -15.0,
            -2.31, 0.012, 21.4, 70.1, 61.0, 21.0, 18.0, 11.0, "State", 0.033]],
  "countries": { "DEU": { "name": "Germany", "regions": 16 } },
  "flags": { "low_res": "fewer than 3 land cells …", "…": "…" },  // texts for every flag
  "attribution": "Borders: Natural Earth (public domain). Places: GeoNames (CC BY 4.0)."
}
```

- One row per region, in the order of `boundaries.json` feature ids (row k ↔ feature id k).
- `lon`, `lat`: a point inside the region (for labels and search results); `area_km2`: the
  polygon area.
- `trend`: pp/decade over the full period; `trend_p`: per-region Mann-Kendall p; `trend_q`:
  Benjamini-Hochberg q across all testable regions, `null` for constant series. **Use
  `trend_q < trend_alpha` for "clear trend"** (see Statistics); `trend_p` is detail only.
- `type`: the region's kind as Natural Earth names it in English (State, Province, Region,
  County, Municipality, …; "Region" for dissolved groups, "Country" for `admin0`), to tell
  duplicate names apart (Buenos Aires city and province, Sofia, Lankaran × 3, Antarctica × 2).
- `p_full`, `p_then`: also useful as tie-breaks when many regions share a rounded `p_now`
  (dozens at 100 %, about 2,000 at 0 %).
- `p_then_<id>`/`p_now_<id>`: the other thresholds (today `raw`), as in `regions.json`.
- `p_gwl<level>`: median projected probability (calibrated threshold); absent when
  projections are not available.
- Any value can be `null`; `flags` (array of strings) says why.
- Fields are looked up by name in `fields`; new fields are only ever appended (`type` and
  `trend_q` were added in the review round of contract v1.6).

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

### admin1/c/{country}.json (loaded when a region is opened; ≤ 70 kB gzip)

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
    "lon": 11.3, "lat": 48.9, "bbox": [8.98, 47.27, 13.84, 50.56],   // [west, south, east, north]
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
          "trend_q": 0.033,                       // BH q; "clear trend" = trend_q < 0.1
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

`bbox` is the smallest longitude span holding the region. For a region split at the
antimeridian (Alaska, Chukotka, Fiji, Kiribati) it wraps: `east` is given + 360, so
`west < east` always holds and `east` can exceed 180 (Alaska `[172.48, 51.22, 230.01, 71.41]`,
Chukotka `[157.69, 61.81, 191.01, 71.6]`, Fiji's Northern division `[178.28, -17.01, 180.18,
-16.12]`, Kiribati `[169.52, -11.46, 208.22, 4.72]`); a wrapped box is always narrower than
180°. MapLibre's `fitBounds` accepts that directly. The two Antarctica features, spread around
the globe, keep plain bounds (`[-180, -90, 180, -60.52]`).

### Sample fixture

`tests/fixtures/admin1_sample/admin1/` holds a small, **clearly fake** dataset in exactly this
format: real Natural Earth outlines for Austria, Germany, Finland, Italy, Liechtenstein (every
region `low_res`) and the Cyprus buffer zone (`admin0` + `no_land`, all values `null`), values
made up (a smooth function of latitude), `data_version: "sample"`. Regenerate with
`uv run whitexmas admin1 sample`. The website copies it into its own fixture tree; it is never
real data.

## Results (data version 2025.1, built 2026-11-19)

Run on the full ERA5-Land cube and the shipped indicators and projections (19 models). Values:
calibrated 5 cm threshold, snow on Christmas Day, 1996–2025 unless stated; trend over
1950–2025 with its Mann-Kendall p. "City" is the main city's own cell, as in the city search.

| Region | Area-weighted | Population-weighted | p5–p95 | Area ≥ 50 % | 1961–1990 | Trend (pp/decade) | +2 °C (median) | City |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Bavaria (DE-BY) | 27.8 % | 23.5 % | 7–87 | 16 % | 45.4 % | −5.5 (p < 0.001) | 22.6 % | Munich 26.7 % |
| Minnesota (US-MN) | 77.8 % | 63.4 % | 53–97 | 99 % | 87.8 % | −2.2 (p 0.20) | 69.9 % | Minneapolis 63.3 % |
| Ontario (CA-ON) | 95.6 % | 51.8 % | 70–100 | 98 % | 97.6 % | −0.3 (p 0.31) | 91.7 % | Toronto 36.7 % |
| Hokkaido (JP-01) | 94.1 % | 91.1 % | 67–100 | 99 % | 90.5 % | +0.7 (p 0.15) | 90.5 % | Sapporo 100 % |
| Tyrol (AT-7) | 97.9 % | 93.3 % | 93–100 | 100 % | 100 % | −0.5 (p 0.009) | 94.9 % | Innsbruck 93.3 % |
| Lapland (FI-10) | 99.9 % | 97.7 % | 100–100 | 100 % | 100 % | 0.0 (p 0.76) | 99.0 % | Rovaniemi 100 % |
| Lombardy (IT-25) | 31.7 % | 9.9 % | 0–97 | 30 % | 37.8 % | −1.7 (p 0.03) | 26.7 % | Milan 10.0 % |
| Scotland (GB-SCT) | 7.9 % | 2.0 % | 0–27 | 0 % | 15.7 % | −1.5 (p 0.005) | 5.9 % | – |

What this shows:

- **The population view matters where people live in the valleys or lowlands.** Lombardy is
  32 % white by area (the Alps) but 10 % where people live (the Po plain, Milan 10 %); Ontario
  is 96 % by area (the boreal north) but 52 % by population (the south, Toronto 37 %).
- **The city cross-check passes**: the population-weighted value sits next to the main city's
  value (Munich 27 / Bavaria 23.5, Minneapolis 63 / Minnesota 63, Innsbruck 93 / Tyrol 93,
  Milan 10 / Lombardy 10), and every city lies inside its region's p5–p95 except Toronto, which
  is in the warmest 5 % of Ontario's area. That is expected, not an error.
- **Bavaria** has lost the most of these: from 45 % (1961–1990) to 28 % (1996–2025), −5.5 pp
  per decade, clearly significant; **Minnesota's** decline (−2.2 pp per decade) is not
  significant over 76 noisy years.

Coverage: 3,988 regions; 3,736 have values. 252 (mostly small islands in the Seychelles,
Maldives, Bahamas, Anguilla, Nauru, Bermuda and the Cook Islands, up to the 946 km² of
Kiribati's atolls and the 816 km² Chatham Islands) have no ERA5-Land land cell inside or within
2 cells (`no_land`, values `null`); 47 coastal cities and small islands take the nearest land
cell (`nearest_cell`, e.g. Gibraltar, Beirut, Conakry, Lantau Island); 524 regions are
`low_res` (under 3 cells). No region is all glacier. The population-weighted value is
`null` for 979 regions without a GeoNames place of 15,000+ inhabitants. 34,175 of the 34,177
places fall in a region.

The regional window value equals the mean of the regional yearly series over the same years
(difference below 0.001 pp for every region, threshold, definition and window checked), and the
projection baseline equals the 1996–2025 value, as they should.

### Timings and sizes (measured)

On the pipeline workstation, one step at a time:

| Step | Wall time | Output |
| --- | --- | --- |
| `admin1 weights` | 34 s (fractions 23 s) | 2.33 million region-cell entries, `interim/admin1/` 16 MB |
| `admin1 stats` | 118 s (windows 31 s, cube pass 64 s, projections 20 s) | `interim/admin1/stats.npz` 4.9 MB |
| `admin1 export` | 13 s | 254 web files, 24.1 MB (3.39 MB gzip); CSV 4.9 MB |

Web files: `index.json` 0.6 MB (132 kB gzip), `boundaries.json` 5.1 MB (1.43 MB gzip), the
largest country file Latvia (119 municipalities) 69 kB gzip. The data bundle grows by 24 MB (it
was 203 MB of the 400 MB budget).

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
- **Small islands** without an ERA5-Land land cell have no values (252 regions, see above).
- **Projections inherit the map's small-probability floor.** A model cell with no snow in
  either window gets a slightly positive log-odds change from the Jeffreys smoothing, because
  the baseline counts 30 years and the warming-level window 20 (logit(0.5/21) − logit(0.5/31)).
  A place at 0 % today is therefore projected at about 0.8 % (Florida 0.0 → 0.8 %; London's
  "0 → 1 %" in projections.md is the same effect), and an always-white place drops to 99.2 %
  with no change in the model at all. This comes from the projection method, not from the regional
  averaging, and is reported for a fix there.
