# Future projections: white Christmas at +1.5, +2 and +3 °C

Status: **Phase 1 (data spike) done, downloads running. Phase 2 (change transfer) in progress.**
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

## Method (Phase 2, in progress)

1. **Per model, per year:** white yes/no on 25 December from `snw ≥ 2.5 kg m⁻²`, on the model's
   own grid, land cells only (`sftlf`).
2. **Frequencies** in the baseline (1995–2014) and in each warming-level window (20 years each).
3. **Change in log-odds** with Jeffreys smoothing, `q = (k + ½)/(n + 1)`, so 0 % and 100 % stay
   finite: `Δ = logit(q_future) − logit(q_baseline)`.
4. **Regrid** each model's `Δ` bilinearly to the 0.1° ERA5-Land grid (model ocean cells are first
   filled from the nearest model land cell so coasts get a value).
5. **Apply** to the ERA5-Land baseline `p` (1996–2025, `n` = 30 years) in the same smoothed space
   and map back: `p' = ((n+1)·expit(logit((p·n + ½)/(n+1)) + Δ) − ½)/n`, clipped to 0–100 %. With
   no change this returns `p` exactly, and a 100 % cell can still decline.
6. **Ensemble:** median, 10th and 90th percentile of `p'` across models; a cell is flagged where at
   least two thirds of the models agree on the sign of the change.

Code: `src/whitexmas/projections/` (`transfer.py`, `regrid.py`, …), tests in `tests/projections/`.

## Limitations (draft)

- Model grids are about 100 km (0.7°–2.8°). Mountains, valleys and coasts are smeared, so the
  change at a ski resort is the change of a 100 km box around it.
- 20-year windows are short. Natural year-to-year variability in each window adds noise to every
  model's change; the model spread partly reflects that noise, not only model differences.
- The warming levels are labelled with the decade they are reached under SSP2-4.5, but the
  projection itself is for a warming level, not a date.
