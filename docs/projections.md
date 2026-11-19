# Future projections: white Christmas at +1.5, +2 and +3 °C

Status: **P1 and P2 done: validated on ERA5-Land 1996–2025 with a hindcast, built and exported on the
calibrated 5 cm baseline (D-17, 2026-11-19).**
This page is the working document for the projections track (plan §3b, milestones P1–P2) and
the source for the methodology page's Future section.

## In one paragraph

We ask: *how much less likely is a white Christmas here in a warmer world?* For each of about 20
global climate models (CMIP6), we count how often there is snow on the ground on Christmas Day in
the model's own world, once for the recent past (1996–2025, the same years as the observations)
and once for the 20 years in which
that model is 1.5, 2 or 3 °C warmer than in 1850–1900. The change between the two is applied to
today's observed probability from ERA5-Land (1996–2025). Because each model is only compared with
itself, a model that has too much or too little snow overall still contributes a useful *change*.
The spread across models gives the uncertainty band (method B, decision D-9; warming levels, D-10).

## Data availability (Phase 1 spike, 2026-11-18)

### 1. Which models publish daily snow?

Daily **snow depth** (`snd`) is rare; daily **snow amount** (`snw`, snow water equivalent,
kg m⁻², table `day`) is common. Searches on 2026-11-18 (latest versions only; union of the
indices below):

| Variable / table | historical | ssp245 | ssp585 |
|---|---|---|---|
| `snd` / `day` | 0 models | 0 | 0 |
| `snd` / `Eday` | 7 (CESM2, GISS-E2-1-G, GISS-E2-2-G, IPSL-CM6A-LR, IPSL-CM6A-LR-INCA, MIROC6, UKESM1-0-LL) | **2** (GISS-E2-1-G, MIROC6) | 2 |
| `snw` / `day` | 37 models | **22** | 22 |
| `snc` / `day` (snow cover %) | 36 | 24 | 21 |

Sources and how they were queried:

- ESGF Solr index at DKRZ, `https://esgf-data.dkrz.de/esg-search/search` with
  `project=CMIP6&variable_id=…&table_id=…&experiment_id=…&type=Dataset&distrib=true&facets=source_id`.
- ESGF 1.5 bridge at ORNL, `https://esgf-node.ornl.gov/esgf-1-5-bridge` (same query; it also sees
  US-only holdings such as CESM2, EC-Earth3-Veg, MIROC-ES2L/ES2H). Slow: 1–4 minutes per query.
- `intake-esgf` 2026.11 with the STAC indices `discovery.{east,west}.esgf.io`, `project="CMIP6"`
  (about 20 s for all `snw/day` datasets). This is what the selection script uses.
- The CEDA index (`esgf.ceda.ac.uk`) timed out and IPSL's index returned HTTP 500 during the spike.

Models with daily `snw` for **historical and ssp245**: ACCESS-CM2, ACCESS-ESM1-5, AWI-CM-1-1-MR,
BCC-CSM2-MR, CESM2, CanESM5, EC-Earth3, EC-Earth3-Veg, GFDL-CM4, GFDL-ESM4, HadGEM3-GC31-LL,
INM-CM4-8, INM-CM5-0, IPSL-CM6A-LR, MIROC-ES2H, MIROC-ES2L, MIROC6, MPI-ESM1-2-HR, MPI-ESM1-2-LR,
MRI-ESM2-0, NESM3, UKESM1-0-LL (22). All but CESM2-on-DKRZ and EC-Earth3-Veg also have ssp585.

**CDS `projections-cmip6`** carries no daily snow. Its constraints API
(`POST https://cds.climate.copernicus.eu/api/retrieve/v1/processes/projections-cmip6/constraints`)
lists only seven daily variables (tas, tasmax, tasmin, huss, sfcWind, pr, psl);
`surface_snow_amount` and `snow_depth` exist only as **monthly** fields (15 models for monthly snw).
So ESGF is the only source for method B.

**Decision:** use daily `snw` (see §4 for the conversion to a depth threshold). This gives 21
usable models (MIROC-ES2H is dropped because Hauser et al. have no warming-level windows for its
`p4` members), well above the 8–15 target. Duplicated model families (EC-Earth3/-Veg, MPI-ESM1-2
HR/LR, INM-CM4-8/5-0, GFDL-CM4/ESM4, HadGEM3/UKESM, MIROC6/ES2L) are kept for now; validation
(Phase 2) decides which are kept and whether families are down-weighted.

### 2. File sizes, download speed and subsetting

- **Volume:** the files we need (historical from 1985, ssp245 2015–2100, ssp585 only where a model
  needs it for +3 °C) are **767 files, 48.6 GB** in total, from 0.1 GB (MIROC-ES2L, AWI) to 15 GB
  (BCC-CSM2-MR, 0.5°-ish grid). Most models are 1–3 GB.
- **Speed** (single stream, from this machine): DKRZ `esgf3.dkrz.de` 6–20 MB/s (typically ~15),
  IPSL `vesg.ipsl.upmc.fr` ~10 MB/s, ORNL `esgf-node.ornl.gov` similar. With 6 parallel streams
  the whole set takes roughly 1–2 hours.
- **Reachability:** CEDA (`esgf.ceda.ac.uk` and `dap.ceda.ac.uk`), ICHEC, CNRM and DWD data nodes
  were **unreachable** from this network (connect timeout / TLS error). Every file we need has a
  replica on DKRZ, ORNL, IPSL, GFDL or NASA NCCS, so this does not cost any model.
- **Subsetting:** OPeNDAP (`thredds/dodsC`) returns **404 on DKRZ** and is not offered on most
  other reachable nodes. HTTP range requests do work (HTTP 206), so a remote read of only the
  December time steps via `fsspec` + `h5netcdf` is possible, but it took 16.7 s for a 35 MB
  MPI-ESM1-2-LR file against 2.0 s for downloading the whole file (files are chunked one day per
  chunk, so a December read is many small requests). **We download whole files**, verify their
  SHA-256 against ESGF, cut them locally to **11 Dec – 8 Jan of every year** (Christmas ± 14 days,
  about 13 % of the original size after compression) and delete the raw file.
  The wider window (instead of just Dec 24–26) costs almost nothing and lets Phase 2 pool nearby
  days to reduce sampling noise in each model's frequency estimate (see the decisions log).
- **Land fraction:** `sftlf` (table `fx`) is fetched per model from a present-day experiment.
  NESM3 publishes `sftlf` only for a paleo experiment (`lig127k`), so its land mask is derived from
  the snow field itself.

Scripts (standalone, PEP 723 inline dependencies, run with `uv run`):

- `scripts/projections/cmip6_select.py` → `$WHITEXMAS_DATA/cmip6/plan.json` (models, members,
  warming-level windows, files with every replica URL and checksum).
- `scripts/projections/cmip6_download.py` → `$WHITEXMAS_DATA/cmip6/snw/<model>/*_xmas.nc`,
  `sftlf/<model>/*.nc`, and the manifest `manifest.jsonl` / `manifest.json` (model, member,
  experiment, variable, source URL, source SHA-256 as verified against ESGF, and the SHA-256 of
  the local subset). Re-running skips anything already in the manifest with a matching checksum.

### 3. Warming-level windows

We use the published per-model crossing years of **Hauser et al.**
([`mathause/cmip_warming_levels`](https://github.com/mathause/cmip_warming_levels), commit
`f9aa658`, file `cmip6_all_ens/csv/cmip6_warming_levels_all_ens_1850_1900.csv`): 20-year windows
whose global-mean surface air temperature is 1.5, 2.0 or 3.0 °C above 1850–1900, per model *and
member*. They cover 21 of the 22 candidate models, so we do not need to compute them from `tas`.

- +1.5 and +2 °C come from **ssp245** for every model.
- +3 °C comes from ssp245 where the model reaches it by 2100 (ACCESS-CM2, CESM2, CanESM5,
  EC-Earth3, EC-Earth3-Veg, HadGEM3-GC31-LL, IPSL-CM6A-LR, UKESM1-0-LL), otherwise from **ssp585**
  (the other 13). Using a warming level rather than a date is what makes mixing scenarios
  acceptable: at a given global warming, regional snow changes are close to scenario-independent.

| Model | Member | +1.5 °C | +2 °C | +3 °C |
|---|---|---|---|---|
| ACCESS-CM2 | r1i1p1f1 | 2019–2038 | 2031–2050 | 2062–2081 |
| ACCESS-ESM1-5 | r1i1p1f1 | 2020–2039 | 2036–2055 | 2051–2070 (585) |
| AWI-CM-1-1-MR | r1i1p1f1 | 2011–2030 | 2030–2049 | 2050–2069 (585) |
| BCC-CSM2-MR | r1i1p1f1 | 2026–2045 | 2048–2067 | 2056–2075 (585) |
| CESM2 | r11i1p1f1 | 2021–2040 | 2035–2054 | 2075–2094 |
| CanESM5 | r1i1p1f1 | 2004–2023 | 2015–2034 | 2040–2059 |
| EC-Earth3 | r1i1p1f1 | 2013–2032 | 2035–2054 | 2076–2095 |
| EC-Earth3-Veg | r5i1p1f1 | 1998–2017 | 2018–2037 | 2053–2072 |
| GFDL-CM4 | r1i1p1f1 | 2022–2041 | 2040–2059 | 2050–2069 (585) |
| GFDL-ESM4 | r1i1p1f1 | 2037–2056 | 2064–2083 | 2066–2085 (585) |
| HadGEM3-GC31-LL | r1i1p1f3 | 2010–2029 | 2024–2043 | 2052–2071 |
| INM-CM4-8 | r1i1p1f1 | 2026–2045 | 2054–2073 | 2060–2079 (585) |
| INM-CM5-0 | r1i1p1f1 | 2028–2047 | 2063–2082 | 2065–2084 (585) |
| IPSL-CM6A-LR | r1i1p1f1 | 2009–2028 | 2024–2043 | 2056–2075 |
| MIROC-ES2L | r1i1p1f2 | 2032–2051 | 2054–2073 | 2061–2080 (585) |
| MIROC6 | r1i1p1f1 | 2037–2056 | 2064–2083 | 2067–2086 (585) |
| MPI-ESM1-2-HR | r1i1p1f1 | 2028–2047 | 2054–2073 | 2064–2083 (585) |
| MPI-ESM1-2-LR | r1i1p1f1 | 2027–2046 | 2048–2067 | 2062–2081 (585) |
| MRI-ESM2-0 | r1i1p1f1 | 2021–2040 | 2040–2059 | 2055–2074 (585) |
| NESM3 | r1i1p1f1 | 2015–2034 | 2033–2052 | 2045–2064 (585) |
| UKESM1-0-LL | r1i1p1f2 | 2014–2033 | 2025–2044 | 2050–2069 |

**Model baseline (decision D-12, 2026-11-19): 1996–2025**, historical up to 2014 and SSP2-4.5
from 2015, exactly the ERA5-Land baseline window. The first draft used 1995–2014 (plan §3b),
which is centred about 0.15 °C of global warming earlier than the observations, so the change
applied to ERA5-Land was slightly double counted; matching the windows removes that.

What a calendar baseline cannot remove: hot models are already warmer than the real world in
1996–2025. CanESM5 (+1.5 °C window 2004–2023), EC-Earth3-Veg (1998–2017) and largely
UKESM1-0-LL (2014–2033) reach +1.5 °C *inside* the baseline, so their +1.5 °C change is near
zero by construction, while cooler models (MIROC6, GFDL-ESM4: 2037–2056) show the full step.
The alternative is a warming-level baseline: each model's own +1.0 °C window from the same
Hauser et al. table (about the observed warming in 1996–2025), so every model contributes the
change from +1.0 °C to the target level. That is a small change (a per-model baseline window
instead of `ProjSettings.baseline`) if it is wanted; it is not used unless decided.

### 4. From snow water equivalent to a 1 cm depth threshold

Snow depth = SWE / snow density. With SWE in kg m⁻² (= mm of water) and density ρ in kg m⁻³,
1 cm of snow corresponds to **SWE = 0.01 m × ρ**. Typical densities: fresh snow 50–150 kg m⁻³,
a settled December snowpack 200–300 kg m⁻³ (Sturm et al. 2010, J. Hydrometeorol., give
early-winter bulk densities of about 220–260 kg m⁻³ across their snow classes). We use **ρ = 250 kg m⁻³, so 1 cm ↔ 2.5 kg m⁻²**, and
test 1 and 5 kg m⁻² (1 cm at 100 kg m⁻³, 2 cm at 250 kg m⁻³) for sensitivity.

Why the exact threshold matters little here: the absolute model snow is never compared with
ERA5-Land. Each model's *change* in the log-odds of "snow above the threshold" between its own
baseline and its own warmer window is what gets transferred. A different threshold shifts the
model's baseline frequency a little, but the log-odds change in the cells where snow is
uncertain (the cells that matter) is nearly the same. A first check on MPI-ESM1-2-LR
(Dec 25, 1995–2014 vs its +2 °C window 2048–2067, cells with 3–17 white years of 20; a first check
made with the earlier baseline):

| SWE threshold (kg m⁻²) | 0.5 | 1 | 2.5 | 5 | 10 |
|---|---|---|---|---|---|
| median log-odds change | −0.45 | −0.50 | −0.50 | −0.42 | −0.45 |

The full sensitivity test across all models is part of Phase 2 validation.

## Method

1. **Per model, per year:** white yes/no on 25 December when `snw ≥ 2.5 kg m⁻²` (§4), on the
   model's own grid and calendar. Land cells only: model land fraction (`sftlf`) ≥ 50 %, or the
   ERA5-Land land mask aggregated to the model grid where `sftlf` is missing (NESM3).
2. **Day pooling (noise reduction).** A single day in 20 years is a very noisy frequency estimate:
   with 20 yes/no values the standard error of a log-odds change is about 0.6 at 50 %, as large
   as the signal at +2 °C. So each model's frequency is the share of days within **±7 days of
   25 December** (18 Dec – 1 Jan) on which the rule holds, averaged over the 20 years. This is the
   same quantity (how often is there snow on the ground at Christmas in this model's climate),
   estimated from 15 correlated days instead of one. The smoothing below still counts 20 years,
   so pooling does not make a model look more certain than its 20 years allow. `--pool 0` gives
   the plain Christmas-Day count; the three definitions pool the same way (a 3-day rule centred
   on each day).
3. **Frequencies** in the baseline (1996–2025: historical to 2014, SSP2-4.5 from 2015; D-12) and
   in each warming-level window (§3). Historical and scenario files are joined on the calendar
   date, so the 2014 season keeps its January 2015 days.
4. **Change in log-odds** with Jeffreys smoothing, `q = (k + ½)/(n + 1)`, so 0 % and 100 % stay
   finite: `Δ = logit(q_future) − logit(q_baseline)`, with `k` the (fractional) white-year count
   and `n` = 20 years.
5. **Regrid** each model's `Δ` bilinearly to the 0.1° ERA5-Land grid. Model ocean cells are first
   filled from the nearest model land cell so that coastal ERA5-Land cells get a value.
6. **Apply** to the ERA5-Land baseline `p` (1996–2025, `n` = 30 years, at the published default
   threshold: the station-calibrated 5 cm, D-17; the raw 1 cm view has no projections) in the same smoothed space
   and map back: `p' = ((n+1)·expit(logit((p·n + ½)/(n+1)) + Δ) − ½)/n`, clipped to 0–100 %.
   With no change this returns `p` exactly, and a 100 % cell can still decline.
7. **Ensemble:** median, 10th and 90th percentile of `p'` across models. **Agreement:** at least
   two thirds of the models with a value agree on the direction of the change, where "no change"
   (`Δ = 0`, e.g. a model cell with snow in every year of both windows) counts as a direction of
   its own (contract v1.3 states this for the hatching and the `wx-proj-v1` agreement bit).
   Without that, cells that keep snow in every model would be flagged as disagreeing.

Why log-odds: a change of "−20 percentage points" means something very different at 25 % and at
95 %. Log-odds is the scale on which a logistic relation between snow and temperature is linear,
it keeps every result between 0 and 100 %, and it lets each model's change be transferred without
comparing its absolute snow with ERA5-Land.

### Running it

```
uv run scripts/projections/cmip6_select.py          # plan.json (models, windows, files)
uv run scripts/projections/cmip6_download.py        # subsets + manifest, resumable
uv run whitexmas projections run      # renders into $WHITEXMAS_DATA/products/projections/web
uv run whitexmas export               # stages the projection files into its web-out and lists them
```

`run` is `changes → validate → ensemble → export`; each step also exists on its own.
Outputs: `interim/projections/models/<model>.nc` (counts and Δ per model grid),
`interim/projections/validation/` (bias maps, `skill.csv`, `hindcast.json`),
`interim/projections/projections.zarr` (0.1° ensemble), and the web products below.

**Publishing (D-16).** A real export always renders into the staging folder
`$WHITEXMAS_DATA/products/projections/web/` (`tiles/proj*.pmtiles`, `proj/`) and writes
`manifest_fragment.json`. The pipeline's `whitexmas export` calls
`manifest_fragment(paths, web_out)`, which copies the staged files into that web-out (skipping
files that are already identical by size and SHA-256, and removing point tiles the new index no
longer lists), checks that every layer URL and `proj/index.json` with all its tiles are there,
and only then returns the layers and the `projections` block. If the staged set is missing or
incomplete it returns None, so the manifest keeps `projections.available: false`; it never lists
layers whose files are not in the web-out. A build on
the placeholder baseline (no `interim/indicators.zarr` yet) refuses to export unless
`--allow-placeholder` is passed, and even then never into `web/static/data` (that folder is
bundled and published), so a preview needs its own `--web-out`. A placeholder preview writes
`manifest_fragment.placeholder.json` (never merged) and COGs tagged `placeholder=true` in
`cog_placeholder/`. Model validation never falls back to the placeholder: without real
ERA5-Land data for the period it is skipped, and the ensemble refuses a model selection that
does not record a real ERA5-Land reference.

### Web products (contract: `manifest.projections`, `wx-proj-v1`)

- `tiles/proj__christmas_day__gwl{1.5,2.0,3.0}.pmtiles`: median projected probability,
  colormap `probability`, kind `projection`.
- `tiles/projchange__christmas_day__gwl{…}.pmtiles`: median change against 1996–2025 in
  percentage points, colormap `change`, hatched where the models do not agree (kind
  `projection_change`, `hatch_disagreement: true`; contract v1.2).
- `proj/<tx>_<ty>.bin.gz`: `wx-proj-v1` point tiles (p10, median, p90 and agreement per level).
- `$WHITEXMAS_DATA/products/projections/manifest_fragment.json`: the layer entries and the
  `projections` block. The pipeline's `whitexmas export` stages the files and merges it into
  `manifest.json` (via `whitexmas.projections.export.manifest_fragment(paths, web_out)`);
  `whitexmas projections export --web-out X --patch-manifest` stages into X and merges directly.
- COGs of p10, p50, p90 and change per level in `$WHITEXMAS_DATA/products/projections/cog/`.

Sizes on the real baseline: 15.6 MB for the 6 layers and 1.6 MB of point tiles.

Code: `src/whitexmas/projections/`, tests in `tests/projections/`.

## Results (calibrated 5 cm baseline, D-17, 2026-11-19)

Built on the pipeline's default ERA5-Land indicators: 1996–2025, `christmas_day`, at the
**station-calibrated threshold of 5 cm** (decision D-17: 5 cm in ERA5-Land matches at least 1 cm
measured at weather stations; contract v1.5 "Thresholds"). Projections exist for this default
threshold only, and every projection layer carries `"threshold": "calibrated"`. The raw 1 cm
view has no projections. Median projected probability, with the 10–90 % model range in brackets.
¹ = fewer than two thirds of the models agree on the direction of change (hatched on the change
map).

| Place | Today (1996–2025) | +1.5 °C | +2 °C | +3 °C |
|---|---|---|---|---|
| Oslo | 67 % | 61 % (46–73) | 56 % (40–67) | 34 % (24–67) |
| Stockholm | 30 % | 28 % (16–33) | 16 % (9–29) | 11 % (4–18) |
| Helsinki | 50 % | 46 % (30–53) | 34 % (23–43) | 22 % (15–33) |
| Moscow | 87 % | 80 % (70–85) | 73 % (59–83) | 57 % (30–74) |
| Warsaw | 13 % | 11 % (5–15) | 9 % (4–13) | 5 % (1–10) |
| Berlin | 7 % | 5 % (2–9) ¹ | 4 % (1–8) | 2 % (0–5) |
| Prague | 10 % | 8 % (3–10) | 6 % (4–9) | 4 % (1–6) |
| Vienna | 10 % | 7 % (4–10) | 7 % (3–12) | 4 % (1–8) |
| Munich | 27 % | 21 % (13–28) | 18 % (11–27) | 11 % (6–21) |
| Zurich | 27 % | 21 % (13–30) | 16 % (9–28) | 10 % (5–15) |
| Innsbruck | 93 % | 90 % (81–94) | 87 % (78–93) | 78 % (68–87) |
| London | 0 % | 1 % (0–1) | 0 % (0–1) ¹ | 0 % (0–1) ¹ |
| Montreal | 70 % | 62 % (48–69) | 52 % (41–68) | 42 % (27–62) |
| Toronto ² | 37 % | 31 % (21–40) | 27 % (16–39) | 19 % (9–27) |
| Minneapolis | 63 % | 54 % (39–67) | 48 % (29–69) | 35 % (18–49) |
| Chicago | 33 % | 30 % (19–40) ¹ | 28 % (14–37) | 16 % (9–28) |
| Boston | 23 % | 21 % (13–30) ¹ | 18 % (9–26) | 10 % (5–17) |
| New York | 3 % | 2 % (1–5) ¹ | 2 % (0–4) | 1 % (0–3) |
| Denver | 40 % | 36 % (21–45) | 26 % (17–40) | 26 % (14–37) |
| Sapporo | 100 % | 99 % (98–100) | 99 % (97–100) | 95 % (88–99) |

² Toronto's own ERA5-Land cell is Lake Ontario (no data); like `places.json`, the row uses the
nearest land cell (43.7 °N). Innsbruck and Sapporo show the 9 km cell, which includes the
surrounding mountains or the snowy hinterland; a valley floor or the city centre is less snowy
than that.

What the numbers say:

- **The decline is gradual at +1.5 °C and clear by +2 °C.** Over land 25–75 °N, in places where a
  white Christmas is uncertain today (10–90 %), the average probability falls from 47 % today
  to 42 % at +1.5 °C, 38 % at +2 °C and 31 % at +3 °C. Models agree on the direction in 79 %,
  91 % and 94 % of those places.
- **Mid-latitude and Nordic cities lose the most:** Stockholm 30 → 16 % and Helsinki 50 → 34 % at
  +2 °C; Minneapolis 63 → 35 %, Montreal 70 → 42 % and Munich 27 → 11 % at +3 °C.
- **Places where Christmas snow is already rare** (Berlin 7 %, Vienna 10 %, New York 3 %) fall
  to a few per cent; London (0 %) stays at essentially zero.
- **Cold or high places change least** (Sapporo, Innsbruck): snow cover there stays reliable even
  several degrees warmer. Moscow still drops from 87 % to 57 % at +3 °C.
- The ranges are wide. This is mostly year-to-year weather inside each model's 20-year window,
  not disagreement about the physics; it is why the site shows the band, not just the median.

With the earlier raw 1 cm baseline the percentages were higher everywhere (Munich 63 % today),
but the projected changes had the same pattern: the model-side change does not depend on the
observed threshold; only the baseline it is applied to does.

### Products

- `tiles/proj__christmas_day__gwl{1.5,2.0,3.0}.pmtiles` and
  `tiles/projchange__christmas_day__gwl{…}.pmtiles`: 6 layers, 14.9 MB, 3144 tiles each (z0–6,
  lossless WebP, same renderer and colours as the historical layers), `"threshold": "calibrated"`.
- `proj/<tx>_<ty>.bin.gz`: 1391 `wx-proj-v1` point tiles, 1.6 MB.
- `manifest_fragment.json` (not a placeholder, `threshold: {"id": "calibrated", "cm": 5}`): 6 layers
  and the `projections` block with `warming_levels` "around the 2030s", "around the 2040s", and
  for +3 °C "late this century or later; most models reach it only under SSP5-8.5".
- COGs of p10, p50, p90 and change per level in `$WHITEXMAS_DATA/products/projections/cog/`.

Rendered into `$WHITEXMAS_DATA/products/projections/web/` (`tiles/`, `proj/`). `whitexmas export`
stages them into its web-out and lists them (see "Publishing" above); this needs a checkout that
contains both the pipeline and the projections package.

**Combined final web data (2026-11-19).** `whitexmas export` from this branch (pipeline
`f4f9b50` + projections) into a clean web-out: 78 layers (72 pipeline + 6 projection),
`projections.available: true`, every layer URL, point tile, projection point tile, `places.json`
and `regions.json` present; 2865 files, 203 MB. Bundle `whitexmas-web-data-2025.1.tar.gz`:
193.7 MB (budget 400 MB; largest file 4.9 MB).

## Validation and model selection

Three checks per model, all scored over land 25–75 °N (where Christmas snow varies), weighted by
cos(latitude), glacier cells excluded, on each model's own grid (ERA5-Land is aggregated to it).

- **Frequency pattern:** the model's white-Christmas frequency against ERA5-Land for the same
  years: mean bias, mean absolute error (all cells, and the "transition" cells where ERA5-Land is
  between 5 and 95 %), and spatial correlation. Bias maps per model:
  `interim/projections/validation/bias_<model>_<years>.nc`.
- **Snow amount:** the median Christmas-Day SWE on snowy days at 40–60 °N against ERA5-Land snow
  depth converted at 250 kg m⁻³. A frequency check cannot see a snowpack that never melts (it is
  "white" either way), but such a model cannot lose its Christmas snow in a warmer world either.
- **Hindcast (Brier skill):** apply each model's own 1961–1990 → 1996–2025 change to ERA5-Land's
  1961–1990 probability and score it against what ERA5-Land observed in 1996–2025. The Brier
  skill score against "no change" says whether the model changes point the right way by about the
  right amount; a reliability table checks the ensemble median.

**Selection rule** (`validation.select_models`, applied automatically before the ensemble): a model
is dropped if its snow amount is outside 0.25–4 × ERA5-Land, its pattern correlation is below 0.80,
or its transition-cell error exceeds 35 pp.

### Skill table (ERA5-Land 1996–2025, calibrated 5 cm)

Model frequencies are for each model's 1996–2025 baseline (historical + SSP2-4.5, Christmas ± 7
days, threshold 2.5 kg m⁻², about 1 cm of snow); ERA5-Land is Christmas Day from the pipeline's
snow cube at the published default, the station-calibrated **5 cm** (D-17), with its glacier
mask. Both stand for "about 1 cm of real snow", so this is a like-for-like comparison. Snow amount
compares 1961–1990 (ERA5-Land median Christmas SWE at 40–60 °N: 64 kg m⁻² at 250 kg m⁻³). The
hindcast column is each model's own Brier skill.

**Re-run on 2026-11-19 for D-17.** The change transfer itself (the model-side counts and log-odds
changes) does not depend on the observed threshold, so the per-model files were not recomputed.
What does depend on it is the observed reference, so the skill table, the selection and the
hindcast were re-run against ERA5-Land at 5 cm. Earlier runs against the raw 1 cm (1996–2025 and
1961–1990) gave the same selection; at 1 cm most models looked short of snow (biases −5 to
−15 pp), at the calibrated 5 cm most are within ±5 pp.

| Model | Grid | Model % | ERA5-Land % | Bias (pp) | MAE (pp) | MAE transition (pp) | Corr. | SWE ratio | Hindcast BSS | Used |
|---|---|---|---|---|---|---|---|---|---|---|
| ACCESS-CM2 | 144x192 | 73 | 56 | +18.0 | 18.2 | 40.5 | 0.82 | 10.15 | – | **no** |
| ACCESS-ESM1-5 | 145x192 | 54 | 55 | -0.6 | 6.7 | 15.6 | 0.95 | 0.54 | +0.3 % | yes |
| AWI-CM-1-1-MR | 192x384 | 50 | 55 | -5.8 | 9.6 | 20.2 | 0.93 | 0.43 | +1.6 % | yes |
| BCC-CSM2-MR | 160x320 | 59 | 55 | +4.0 | 7.9 | 17.9 | 0.93 | 0.68 | +1.6 % | yes |
| CanESM5 | 64x128 | 64 | 55 | +9.1 | 11.8 | 25.6 | 0.88 | 0.62 | +0.8 % | yes |
| CESM2 | 192x288 | 59 | 56 | +3.3 | 7.6 | 18.4 | 0.93 | 0.62 | +1.1 % | yes |
| EC-Earth3 | 256x512 | 67 | 55 | +11.7 | 11.8 | 28.5 | 0.91 | 0.6 | -1.5 % | yes |
| EC-Earth3-Veg | 256x512 | 67 | 55 | +11.8 | 11.9 | 28.5 | 0.91 | 0.56 | -1.3 % | yes |
| GFDL-CM4 | 180x288 | 57 | 55 | +1.9 | 5.3 | 12.9 | 0.96 | 0.57 | +0.4 % | yes |
| GFDL-ESM4 | 180x288 | 56 | 55 | +1.0 | 5.5 | 13.2 | 0.96 | 0.55 | -3.2 % | yes |
| HadGEM3-GC31-LL | 144x192 | 57 | 55 | +1.4 | 5.7 | 13.8 | 0.96 | 0.44 | +1.7 % | yes |
| INM-CM4-8 | 120x180 | 55 | 56 | -0.6 | 7.9 | 17.7 | 0.93 | 0.64 | +0.2 % | yes |
| INM-CM5-0 | 120x180 | 54 | 56 | -1.4 | 7.8 | 17.4 | 0.93 | 0.6 | -1.0 % | yes |
| IPSL-CM6A-LR | 143x144 | 65 | 55 | +9.5 | 10.8 | 25.5 | 0.91 | 0.68 | -0.3 % | yes |
| MIROC-ES2L | 64x128 | 59 | 56 | +2.9 | 12.0 | 24.1 | 0.85 | 0.52 | +1.0 % | yes |
| MIROC6 | 128x256 | 59 | 56 | +3.1 | 9.0 | 20.3 | 0.91 | 0.61 | +1.1 % | yes |
| MPI-ESM1-2-HR | 192x384 | 53 | 56 | -2.8 | 8.4 | 18.5 | 0.93 | 0.45 | -0.3 % | yes |
| MPI-ESM1-2-LR | 96x192 | 54 | 55 | -1.2 | 8.3 | 18.9 | 0.93 | 0.49 | +1.0 % | yes |
| MRI-ESM2-0 | 160x320 | 63 | 55 | +8.0 | 10.5 | 23.4 | 0.89 | 0.66 | +0.5 % | yes |
| NESM3 | 96x192 | 48 | 54 | -6.7 | 10.2 | 21.9 | 0.91 | 0.18 | – | **no** |
| UKESM1-0-LL | 144x192 | 58 | 55 | +3.1 | 7.2 | 17.1 | 0.95 | 0.35 | -0.1 % | yes |

- **Dropped: ACCESS-CM2.** Its Christmas snowpack is ten times ERA5-Land's (median 646 kg m⁻²;
  at Chicago often more than 1 m of snow on Christmas Day): it practically never melts, so its
  future change is near zero by construction. Its frequency pattern alone looks fine, which is
  why the amount check exists.
- **Dropped: NESM3.** Snow amount 0.18 × ERA5-Land (a thin snowpack barely above the threshold).
  (ACCESS-CM2 also fails the transition-cell rule at 5 cm: 40.5 pp.)
- Against the calibrated threshold most models are close to ERA5-Land (biases within ±5 pp for 13
  of the 19 used, pattern correlation 0.85–0.96). EC-Earth3/-Veg, IPSL-CM6A-LR, CanESM5 and
  MRI-ESM2-0 are somewhat too snowy (+8 to +12 pp). Because only each model's *change* is used,
  a moderate bias is acceptable. The snow-amount ratios cluster at 0.35–0.68, i.e. ERA5-Land
  December snow is on average lighter than the assumed 250 kg m⁻³ (or deeper than the models'),
  consistently.
- **19 models are used**, from 13 model families: six pairs share most of their code
  (EC-Earth3/-Veg, MPI-ESM1-2-HR/-LR, INM-CM4-8/5-0, GFDL-CM4/ESM4, HadGEM3/UKESM1,
  MIROC6/MIROC-ES2L). They are weighted equally for now; family weighting is a possible refinement.

### Hindcast: 1961–1990 → 1996–2025

Each model's own change from 1961–1990 to 1996–2025 (historical + SSP2-4.5, the production
computation including its land mask), applied to ERA5-Land 1961–1990 and scored against what
ERA5-Land observed in 1996–2025, both at the calibrated 5 cm (land 25–75 °N, 19 models;
re-run for D-17; the run at 1 cm gave +3.1 % against a ceiling of +9.1 %):

| Forecast for 1996–2025 | Brier score | Skill vs "no change" |
|---|---|---|
| No change (ERA5-Land 1961–1990) | 0.0584 | 0 |
| **Ensemble median (this method)** | **0.0561** | **+4.0 %** |
| Single models | 0.0574–0.0603 | -3.2 % to +1.7 % |
| Perfect: the observed 1996–2025 frequency | 0.0524 | +10.3 % (the ceiling) |

Mean change over the region: observed -3.0 pp, ensemble median
-2.0 pp.

What this says, in plain words:

- **The method works in the right direction and is somewhat conservative.** Applied to the past,
  it predicts the observed decline in white Christmases with about two thirds of its size, and it
  earns about 40 % of the skill that even a perfect knowledge of the 1996–2025 frequencies
  would give. The rest of a single year's outcome is weather, which no projection can predict.
- **Only the ensemble median has skill.** Single models score between −3 % and +2 %: one model's
  change over 30 years is largely its own year-to-year variability. That is why the published value
  is the median of 19 models and why the 10–90 % band is wide.
- **Reliability** of the ensemble median is good: in every 10 % bin, forecast and observed
  frequency are within 4.5 pp. Observed values are a little lower in the middle bins, the same
  conservative tendency (the real decline was slightly larger than projected).

| Forecast bin | Forecast % | Observed % | Share of area |
|---|---|---|---|
| 0-10 % | 1.4 | 1.5 | 31.1 % |
| 10-20 % | 14.6 | 13.2 | 5.3 % |
| 20-30 % | 24.7 | 22.3 | 3.2 % |
| 30-40 % | 34.9 | 32.4 | 2.7 % |
| 40-50 % | 44.9 | 41.4 | 2.5 % |
| 50-60 % | 54.8 | 50.5 | 2.4 % |
| 60-70 % | 65.0 | 60.7 | 2.6 % |
| 70-80 % | 75.0 | 70.9 | 2.5 % |
| 80-90 % | 85.3 | 82.4 | 3.0 % |
| 90-100 % | 99.4 | 98.5 | 44.7 % |

### Earlier dry run (1961–1975 → 1981–1995)

A dry run on years that are already on disk (each model's change from 1961–1975 to 1981–1995,
applied to ERA5-Land 1961–1975, scored on 1981–1995): Brier score 0.0541 with no change,
0.0541 for the ensemble median (skill +0.2 %), and −2 to −9 % for single models. Little global
warming happened between those periods (observed mean change −1 pp, ensemble median 0 pp), so a
single model's change is mostly its own year-to-year noise, and only the ensemble median avoids
adding that noise. Reliability of the ensemble median is good (forecast and observed frequency
within 4 pp in every 10 % bin). The real test (1961–1990 → 1996–2025, about 0.5 °C more global
warming) is above.

### Sensitivity to threshold and day pooling

Christmas-Day log-odds change from the 1996–2025 baseline to +2 °C, all 21 models, cells where
the models' median baseline frequency is 10–90 %, Northern Hemisphere 25–75 °N on a 1° grid
(`scripts/projections/sensitivity.py`):

| SWE threshold (kg m⁻²) | Pooling | Median change | Model spread (p10–p90) | Noise (neighbour diff.) |
|---|---|---|---|---|
| 2.5 | none (Dec 25 only) | −0.514 | 1.63 | 0.110 |
| 2.5 | ± 3 days | −0.518 | 1.36 | 0.089 |
| **2.5** | **± 7 days (used)** | **−0.510** | **1.21** | **0.077** |
| 1.0 | ± 7 days | −0.508 | 1.17 | 0.069 |
| 5.0 | ± 7 days | −0.494 | 1.29 | 0.086 |

The typical change hardly depends on the threshold or on pooling (−0.49 to −0.52: at 50 % today,
about 38 % at +2 °C). Pooling ± 7 days narrows the model spread by about a quarter (26 %) and
cell-to-cell noise by 30 %, which is the point of it: less of the uncertainty band is sampling
noise. (With the earlier 1995–2014 baseline the median change was −0.55; the 1996–2025 baseline
is about 0.15 °C warmer, so the step to +2 °C is a little smaller.)

## Limitations

- **Coarse models.** Model grids are about 100 km (0.7°–2.8°). Mountains, valleys and coasts are
  smeared, so the change at a ski resort is the change of a 100 km box around it, applied to the
  resort's own 9 km ERA5-Land baseline.
- **Short windows.** 20-year windows are short. Natural year-to-year variability adds noise to
  every model's change; the model spread partly reflects that noise, not only model differences.
  Day pooling reduces it but cannot remove it.
- **One scenario path labels the decades.** The projection is for a warming level, not a date.
  The label is derived from the models actually used: the decade of the median centre of their
  SSP2-4.5 warming-level windows ("+1.5 °C around the 2030s", "+2 °C around the 2040s" with
  the current 19 models). Only 7 of the 19 reach +3 °C under SSP2-4.5 by 2100, so +3 °C is
  labelled "late this century or later; most models reach it only under SSP5-8.5" (the rule:
  fewer than half the models reach the level under SSP2-4.5). With faster or slower emission
  cuts the same warming level comes earlier or later.
- **Hot models and the calendar baseline.** Models and ERA5-Land share the 1996–2025 baseline
  (D-12), so nothing is double counted. But hot models are already near +1.5 °C in those years,
  so their +1.5 °C change is small; the ensemble mixes "how much warmer" with "how sensitive the
  model is". See §3 for the warming-level-baseline alternative.
- **Snow amount, not depth.** Models provide snow water equivalent; the 1 cm threshold is
  converted with an assumed density (§4). The change transfer makes the result insensitive to
  the exact value.
