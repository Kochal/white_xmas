# Legacy code (reference only)

These files are the original white-Christmas analysis, kept unchanged for reference. They are
**not** part of the pipeline and are not run by CI. Notebook outputs were stripped.

- `download_era5land.py`: hourly `reanalysis-era5-land` download for Dec 10–26, 1980–2024,
  0–90°N, with t2m, snow depth and total precipitation (about 2 GB per year).
- `calc_era_prob.ipynb`: probability, trend and valid-years GeoTIFFs (§1–3); an unfinished snow
  model (§4–5) and CMIP6 projections that never ran (§6–8).

## Known bugs (do not reuse the published GeoTIFFs as they are)

1. **Ocean and missing cells count as 0 % white.** `(sd_year_max >= threshold).astype("float32")`
   turns NaN into False, so every sea cell has probability 0 %, trend 0 and a constant
   `valid_years`; map means are diluted by the ocean and the land/sea mask is lost.
2. **"All three days" counts hours, not days.** `days_present >= 3` sums hourly non-null values
   (up to 72), so it is true wherever any data exists.
3. **Very lenient definition.** "Any single hour of Dec 24–26 with ≥ 1 cm" counts a brief dusting
   on the evening of the 26th as a white Christmas.
4. **Ten-year trend maps are noise.** An OLS slope over ten 0/1 values has no statistical meaning;
   there is no significance test.
5. **Most of the download is unused**: Dec 10–23, t2m and precipitation only fed the unfinished model.
6. **Modelling and CMIP6 (§4–8)**: the "bias-corrected" future adds the change twice
   (`cmip6_future + anomaly` instead of ERA5 climatology + anomaly); same-day temperature is used as
   a predictor (a nowcast, not a projection); inconsistent units in the degree-day model; a
   monthly-mean delta cannot represent changes in snowfall days.
7. **Smaller points**: `np.float` monkey-patches, hard-coded Windows paths, Northern Hemisphere
   only, glaciers and ice sheets shown as 100 %, hand-shifted longitudes for static fields.

The new pipeline in `src/whitexmas/` fixes all of these; see `docs/methodology.md`.
