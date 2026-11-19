# Future projections: white Christmas at +1.5, +2 and +3 °C

Status: **Phase 1 done; Phase 2 built and validated on 1961–1990; final validation and the real
baseline wait for the pipeline's ERA5-Land 1996–2025 data.**
This page is the working document for the projections track (plan §3b, milestones P1–P2). The
method, model list, skill table and limitations sections are filled in as Phase 2 lands.

## In one paragraph

We ask: *how much less likely is a white Christmas here in a warmer world?* For each of about 20
global climate models (CMIP6), we count how often there is snow on the ground on Christmas Day in
the model's own world, once for the recent past (1995–2014) and once for the 20 years in which
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

Two things to note. Hot models (CanESM5, EC-Earth3-Veg, UKESM1-0-LL) reach +1.5 °C during or just
after the 1995–2014 baseline, so their +1.5 °C change is small by construction; that is correct
for a warming-level framing. And the model baseline (1995–2014, about +0.85 °C) is centred six
years earlier than the ERA5-Land baseline (1996–2025); the difference is about 0.15 °C of global
warming, small next to the steps between levels. Both are stated on the methodology page.

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
(Dec 25, 1995–2014 vs its +2 °C window 2048–2067, cells with 3–17 white years of 20):

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
3. **Frequencies** in the baseline (historical 1995–2014) and in each warming-level window (§3).
4. **Change in log-odds** with Jeffreys smoothing, `q = (k + ½)/(n + 1)`, so 0 % and 100 % stay
   finite: `Δ = logit(q_future) − logit(q_baseline)`, with `k` the (fractional) white-year count
   and `n` = 20 years.
5. **Regrid** each model's `Δ` bilinearly to the 0.1° ERA5-Land grid. Model ocean cells are first
   filled from the nearest model land cell so that coastal ERA5-Land cells get a value.
6. **Apply** to the ERA5-Land baseline `p` (1996–2025, `n` = 30 years) in the same smoothed space
   and map back: `p' = ((n+1)·expit(logit((p·n + ½)/(n+1)) + Δ) − ½)/n`, clipped to 0–100 %.
   With no change this returns `p` exactly, and a 100 % cell can still decline.
7. **Ensemble:** median, 10th and 90th percentile of `p'` across models. **Agreement:** at least
   two thirds of the models with a value agree on the direction of the change, where "no change"
   (`Δ = 0`, e.g. a model cell with snow in every year of both windows) counts as a direction of
   its own. Without that, cells that keep snow in every model would be flagged as disagreeing.

Why log-odds: a change of "−20 percentage points" means something very different at 25 % and at
95 %. Log-odds is the scale on which a logistic relation between snow and temperature is linear,
it keeps every result between 0 and 100 %, and it lets each model's change be transferred without
comparing its absolute snow with ERA5-Land.

### Running it

```
uv run scripts/projections/cmip6_select.py          # plan.json (models, windows, files)
uv run scripts/projections/cmip6_download.py        # subsets + manifest, resumable
uv run python -m whitexmas.projections run --web-out web/static/data
```

`run` is `changes → validate → ensemble → export`; each step also exists on its own.
Outputs: `interim/projections/models/<model>.nc` (counts and Δ per model grid),
`interim/projections/validation/` (bias maps, `skill.csv`, `hindcast.json`),
`interim/projections/projections.zarr` (0.1° ensemble), and the web products below. A build on
the placeholder baseline (no `interim/indicators.zarr` yet) refuses to export unless
`--allow-placeholder` is passed, and its manifest fragment is marked so the pipeline never
publishes it.

### Web products (contract: `manifest.projections`, `wx-proj-v1`)

- `tiles/proj__christmas_day__gwl{1.5,2.0,3.0}.pmtiles`: median projected probability,
  colormap `probability`, kind `projection`.
- `tiles/projchange__christmas_day__gwl{…}.pmtiles`: median change against 1996–2025 in
  percentage points, colormap `change`, hatched where the models do not agree (kind
  `projection_change`, `hatch_low_agreement: true`; a proposed contract addition).
- `proj/<tx>_<ty>.bin.gz`: `wx-proj-v1` point tiles (p10, median, p90 and agreement per level).
- `$WHITEXMAS_DATA/products/projections/manifest_fragment.json`: the layer entries and the
  `projections` block, merged into `manifest.json` by `whitexmas.projections.export`.
- COGs of p10, p50, p90 and change per level in `$WHITEXMAS_DATA/products/projections/cog/`.

Sizes with the placeholder baseline: about 2.8 MB per layer (6 layers) and 3.4 MB of point tiles.

Code: `src/whitexmas/projections/`, tests in `tests/projections/`.

## Validation and model selection

Three checks per model, all scored over land 25–75 °N (where Christmas snow varies), weighted by
cos(latitude), glacier cells excluded, on each model's own grid (ERA5-Land is aggregated to it):

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
  right amount; a reliability table checks the ensemble median. _Pending: needs ERA5-Land
  1996–2025 (the pipeline's download had reached 1998 on 2026-11-19)._

**Selection rule** (`validation.select_models`, applied automatically before the ensemble): a model
is dropped if its snow amount is outside 0.25–4 × ERA5-Land, its pattern correlation is below 0.80,
or its transition-cell error exceeds 35 pp.

### Interim results (ERA5-Land 1961–1990)

ERA5-Land 1995–2014 is not complete yet, so the first validation uses 1961–1990, a period where
every year is on disk; model frequencies are from each model's `historical` run for the same
years (Christmas ± 7 days, threshold 2.5 kg m⁻²). The run on 1995–2014 replaces this table once the
data is in. ERA5-Land median Christmas SWE at 40–60 °N: 64 kg m⁻² (at 250 kg m⁻³).

| Model | Grid | Model % | ERA5-Land % | Bias (pp) | MAE (pp) | MAE transition (pp) | Corr. | SWE ratio | Used |
|---|---|---|---|---|---|---|---|---|---|
| ACCESS-CM2 | 144x192 | 77 | 68 | +8.8 | 10.0 | 24.9 | 0.90 | 10.15 | **no** |
| ACCESS-ESM1-5 | 145x192 | 58 | 67 | -9.3 | 12.3 | 27.9 | 0.88 | 0.54 | yes |
| AWI-CM-1-1-MR | 192x384 | 51 | 69 | -17.5 | 17.8 | 32.8 | 0.84 | 0.43 | yes |
| BCC-CSM2-MR | 160x320 | 62 | 67 | -5.5 | 8.7 | 20.4 | 0.93 | 0.68 | yes |
| CanESM5 | 64x128 | 68 | 68 | +0.0 | 7.3 | 17.4 | 0.94 | 0.62 | yes |
| CESM2 | 192x288 | 63 | 69 | -5.9 | 8.5 | 22.1 | 0.93 | 0.62 | yes |
| EC-Earth3 | 256x512 | 71 | 69 | +2.7 | 5.1 | 13.8 | 0.97 | 0.6 | yes |
| EC-Earth3-Veg | 256x512 | 70 | 69 | +1.4 | 4.3 | 11.3 | 0.98 | 0.56 | yes |
| GFDL-CM4 | 180x288 | 61 | 68 | -7.1 | 9.2 | 21.2 | 0.92 | 0.57 | yes |
| GFDL-ESM4 | 180x288 | 57 | 68 | -10.7 | 12.2 | 26.3 | 0.89 | 0.55 | yes |
| HadGEM3-GC31-LL | 144x192 | 61 | 68 | -7.4 | 9.0 | 20.7 | 0.93 | 0.44 | yes |
| INM-CM4-8 | 120x180 | 56 | 69 | -13.3 | 14.7 | 29.5 | 0.86 | 0.64 | yes |
| INM-CM5-0 | 120x180 | 57 | 69 | -12.2 | 13.8 | 27.6 | 0.86 | 0.6 | yes |
| IPSL-CM6A-LR | 143x144 | 67 | 68 | -1.1 | 5.6 | 13.7 | 0.96 | 0.68 | yes |
| MIROC-ES2L | 64x128 | 61 | 68 | -7.1 | 11.6 | 23.8 | 0.88 | 0.52 | yes |
| MIROC6 | 128x256 | 62 | 68 | -6.8 | 9.9 | 23.3 | 0.91 | 0.61 | yes |
| MPI-ESM1-2-HR | 192x384 | 53 | 69 | -15.7 | 16.1 | 29.5 | 0.85 | 0.45 | yes |
| MPI-ESM1-2-LR | 96x192 | 55 | 68 | -13.0 | 14.2 | 27.4 | 0.86 | 0.49 | yes |
| MRI-ESM2-0 | 160x320 | 66 | 67 | -1.0 | 6.7 | 17.4 | 0.94 | 0.66 | yes |
| NESM3 | 96x192 | 49 | 67 | -17.7 | 18.2 | 32.9 | 0.82 | 0.18 | **no** |
| UKESM1-0-LL | 144x192 | 62 | 68 | -6.0 | 8.8 | 19.6 | 0.92 | 0.35 | yes |

- **Dropped: ACCESS-CM2.** Its Christmas snowpack is ten times ERA5-Land's (median 646 kg m⁻²;
  at Chicago often more than 1 m of snow on Christmas Day): it practically never melts, so its future
  change is near zero by construction. Its frequency pattern alone looks fine, which is why the
  amount check exists.
- **Dropped: NESM3.** Snow amount 0.18 × ERA5-Land (a thin snowpack barely above the threshold),
  together with the weakest frequency pattern of all models (correlation 0.82, −18 pp bias).
- Most models have too little Christmas snow (biases mostly −5 to −15 pp), the usual CMIP6 warm/dry
  bias over Eurasian and North American mid-latitudes. Because only each model's *change* is used,
  a moderate bias is acceptable; the change is still computed where the model's own snow is
  uncertain. The snow-amount ratios cluster at 0.35–0.68, i.e. ERA5-Land December snow is on
  average lighter than the assumed 250 kg m⁻³ (or deeper than the models'), consistently.
- **19 models are used**, from 13 model families: six pairs share most of their code
  (EC-Earth3/-Veg, MPI-ESM1-2-HR/-LR, INM-CM4-8/5-0, GFDL-CM4/ESM4, HadGEM3/UKESM1,
  MIROC6/MIROC-ES2L). They are weighted equally for now; family weighting is a possible refinement.

### Sensitivity to threshold and day pooling

Christmas-Day log-odds change at +2 °C, all 21 models, cells where the models' median baseline
frequency is 10–90 %, Northern Hemisphere 25–75 °N on a 1° grid
(`scripts/projections/sensitivity.py`):

| SWE threshold (kg m⁻²) | Pooling | Median change | Model spread (p10–p90) | Noise (neighbour diff.) |
|---|---|---|---|---|
| 2.5 | none (Dec 25 only) | −0.554 | 1.71 | 0.106 |
| 2.5 | ± 3 days | −0.563 | 1.45 | 0.087 |
| **2.5** | **± 7 days (used)** | **−0.553** | **1.30** | **0.075** |
| 1.0 | ± 7 days | −0.552 | 1.24 | 0.068 |
| 5.0 | ± 7 days | −0.552 | 1.39 | 0.084 |

The typical change does not depend on the threshold or on pooling (−0.55 in every case: at 50 %
today, about 37 % at +2 °C). Pooling ± 7 days narrows the model spread by about a quarter and
cell-to-cell noise by about 30 %, which is the point of it: less of the uncertainty band is
sampling noise.

## Limitations

- **Coarse models.** Model grids are about 100 km (0.7°–2.8°). Mountains, valleys and coasts are
  smeared, so the change at a ski resort is the change of a 100 km box around it, applied to the
  resort's own 9 km ERA5-Land baseline.
- **Short windows.** 20-year windows are short. Natural year-to-year variability adds noise to
  every model's change; the model spread partly reflects that noise, not only model differences.
  Day pooling reduces it but cannot remove it.
- **One scenario path labels the decades.** The projection is for a warming level, not a date.
  "+2 °C (around the 2050s)" uses the SSP2-4.5 median; with faster or slower emission cuts the
  same warming level comes earlier or later.
- **Baseline offset.** Models use 1995–2014 (about +0.85 °C) as their baseline, ERA5-Land uses
  1996–2025 (about +1.0 °C). The projected change is therefore slightly too large, by roughly
  the change between those two periods (~0.15 °C of global warming). Hot models reach +1.5 °C
  during their baseline, so their +1.5 °C change is small.
- **Snow amount, not depth.** Models provide snow water equivalent; the 1 cm threshold is
  converted with an assumed density (§4). The change transfer makes the result insensitive to
  the exact value.
