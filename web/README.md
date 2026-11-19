# White Christmas: website

A static, map-first site that shows how likely a white Christmas is anywhere on Earth, how that
changed since 1950 and how it changes in a warmer world. It is a SvelteKit app built with
`@sveltejs/adapter-static`, using MapLibre GL JS with PMTiles for the map and plain SVG for the charts.

The site reads only the files described in the **web data contract** (`manifest.json`,
`tiles/*.pmtiles`, `points/`, `proj/`, `places.json`, `regions.json` and, optionally, `admin1/`). The pipeline
(`src/whitexmas/export/`) writes them, and the site never assumes anything the manifest doesn't list.

## Quick start

```sh
cd web
npm ci
npm run fixtures   # writes a small FAKE dataset to fixtures/data/
npm run dev        # http://localhost:$PANE_PORT (or 5173), using the fixtures
```

## Data

| Where                          | Used by                      | How                                                                                                 |
| ------------------------------ | ---------------------------- | --------------------------------------------------------------------------------------------------- |
| `fixtures/data/` (git-ignored) | `npm run dev`, tests         | `npm run fixtures`; the dev server serves it at `<base>/__fixtures/data/`                           |
| `static/data/` (git-ignored)   | a local build with real data | `whitexmas export --web-out web/static/data` (pipeline); adapter-static copies it into `build/data` |
| `build/data/` on GitHub Pages  | production                   | `pages.yml` unpacks the release bundle `whitexmas-web-data-<version>.tar.gz` there                  |

The app fetches data from `PUBLIC_DATA_BASE`. It defaults to `<base>/data` in a build and to the
fixtures in `vite dev`. To develop against real pipeline output, fill `static/data/` (from
`whitexmas export --web-out web/static/data`, or by copying an export), put
`PUBLIC_DATA_BASE=/data` in `web/.env.local` (git-ignored), and run `npm run dev`. A variable set
on the command line is lost when the dev server regenerates its env module, and Git Bash rewrites
`/data` into a Windows path unless `MSYS_NO_PATHCONV=1` is set. Remove `.env.local` again before
building for a base path.

The fixture data is obviously fake: a smooth latitude gradient with made-up mountains, lakes and a
glacier, over 17 point tiles in central Europe and around the Great Lakes, 56 real city names
(GeoNames) with fake values, 11 regions and 19 layers: both thresholds of contract v1.5 (a
"calibrated" 5 cm default and the raw 1 cm view, with a made-up calibration), and projections. When the
`data_version` contains `fixture`, the site shows a "fixture data" banner.
`node scripts/make-fixture-data.mjs --no-projections` writes a dataset without projections.

States and provinces (contract v1.6, see `docs/admin1.md`): the fixtures copy the pipeline's own
sample, `tests/fixtures/admin1_sample/admin1/` (real Natural Earth outlines for Austria, Germany,
Finland, Italy, Liechtenstein and the Cyprus buffer zone with made-up values), and list it in the
manifest's `admin1` block. `--no-admin1` leaves it out; a manifest without the block hides every
region feature.

## States and provinces

Optional (the manifest lists `admin1`); everything loads lazily, so the first load is unchanged:

| What                      | Loaded when                                                                  | Size (gzip) |
| ------------------------- | ---------------------------------------------------------------------------- | ----------- |
| `admin1/index.json`       | the layer is switched on, the search box gets focus, the rankings page opens | ~130 kB     |
| `admin1/boundaries.json`  | the layer is switched on, or a `#/region/<id>` link opens                    | ~1.4 MB     |
| `admin1/c/<country>.json` | a region of that country is opened                                           | ≤ ~150 kB   |

- **Map:** the "States and provinces" switch in the layer controls shows faint borders, names from
  a zoom that depends on the region's size, a hover highlight and click-to-select
  (`src/lib/map/regions-layer.ts`). It replaces the basemap's own state borders and names while on.
- **Panel** (`src/lib/panel/RegionPanel.svelte`): headline for the selected threshold, definition
  and period (the same two-threshold behaviour as the place panel), the population-weighted
  value, then vs now, decades, the yearly series with the fitted trend and its significance mark,
  the spread inside the region, projections at +1.5/+2/+3 °C and a plain note for small
  (low-resolution) regions. All numbers come from the country file; `src/lib/data/region-view.ts`
  holds the logic.
- **Deep link:** `#/region/<id>` (an ISO 3166-2 code such as `DE-BY`), also after a reload;
  `?regions=1` switches the borders on without selecting anything (`src/lib/url-state.ts`).
- **Search:** the box finds regions next to places (`src/lib/data/admin1-search.ts`).
- **Rankings:** `/rankings` lists the snowiest, least snowy and biggest-decline regions for the
  world or one country, and has a find box (`src/lib/admin1-rankings.ts`). The world lists leave
  out low-resolution regions.

## Scripts

| Script                           | What it does                                                                 |
| -------------------------------- | ---------------------------------------------------------------------------- |
| `npm run dev`                    | Dev server with the fixtures                                                 |
| `npm run build`                  | Static build into `build/` (set `BASE_PATH=/white_xmas` for Pages)           |
| `npm run build:fixtures`         | Build, then copy the fixtures into `build/data/`                             |
| `npm run preview`                | Serve `build/` like GitHub Pages (base path, 404.html, range requests)       |
| `npm run check`                  | `svelte-check` (TypeScript)                                                  |
| `npm run lint`                   | Prettier and ESLint                                                          |
| `npx vitest run`                 | Unit tests (data layer, decoders, statistics, fixture writer)                |
| `npm run test:e2e`               | Playwright smoke test against the built site and fixtures (desktop + mobile) |
| `E2E_REAL=1 npx playwright test` | The same smoke test against real data in `static/data/`                      |
| `npm run fixtures`               | Regenerate `fixtures/data/`                                                  |

On Windows Git Bash, prefix `BASE_PATH=/white_xmas` with `MSYS_NO_PATHCONV=1` so the path isn't rewritten.

## Configuration (build-time environment variables)

| Variable               | Default                                         | Purpose                                     |
| ---------------------- | ----------------------------------------------- | ------------------------------------------- |
| `BASE_PATH`            | `''`                                            | `paths.base`; `/white_xmas` on GitHub Pages |
| `PUBLIC_DATA_BASE`     | `<base>/data` (build), fixtures (dev)           | Base URL of the web data; may be absolute   |
| `PUBLIC_SITE_URL`      | `https://kochal.github.io/white_xmas`           | Absolute URL for social preview tags        |
| `PUBLIC_DOWNLOADS_URL` | `https://github.com/Kochal/white_xmas/releases` | Downloads page links                        |

## Performance

First-load JS is about 70 KB gzipped and the page CSS is inlined. MapLibre (about 293 KB gzipped,
plus its 155 KB worker) loads after the first paint. The map starts with a plain background and
the climate layer, then switches to a slimmed basemap (no buildings, POIs, road labels or minor
roads; see `src/lib/map/basemap.ts`).

Lighthouse on the built site with the fixtures, served locally with gzip
(`npm run build:fixtures && npm run preview`, then `npx lighthouse http://localhost:4173/`):

- desktop: performance 99–100;
- mobile (simulated slow 4G, 4× CPU): about 80 (FCP 1.6 s, LCP 1.7 s), where the remaining
  blocking time is MapLibre's own evaluation and the first GL renders;
- accessibility, best practices and SEO: 100.

Place search over the full ~34k-place list takes about 1–10 ms per keystroke on a desktop
(`src/lib/data/search.bench.spec.ts`).

## Deploying to GitHub Pages

`.github/workflows/pages.yml` builds the site with `BASE_PATH=/white_xmas`, downloads
`whitexmas-web-data-<version>.tar.gz` from the release tagged `data-<version>`, unpacks it into
`build/data/` and deploys with `actions/deploy-pages`. It runs on manual dispatch, and on pushes to
`main` only when the repo variable `PAGES_ENABLED` is `true`.

One-time setup, done by the repository owner:

1. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
2. **Settings → Environments → `github-pages`**: allow deployments from `main` (the default rule
   created with Pages usually does this already).
3. Optionally, under **Settings → Secrets and variables → Actions → Variables**, set:
   - `PAGES_ENABLED` = `true` to deploy on every push to `main`;
   - `DATA_VERSION` (e.g. `2026.1`) to pin the data bundle; otherwise the latest `data-*` release is used;
   - `PAGES_BASE_PATH` and `PAGES_SITE_URL` only for a custom domain (`''` and `https://…`).
4. Create the data release (pipeline side): tag `data-<version>` with the asset
   `whitexmas-web-data-<version>.tar.gz`.
5. **Actions → pages → Run workflow.** Before a data release exists, untick `require_data` to
   deploy the site alone as a placeholder.

The bundle may contain the data tree at its root or inside one folder; the workflow uses the
shallowest `manifest.json` and checks that `schema_version` is `1`.

## Layout

```
web/
  src/lib/data/       manifest, point-tile decoders, derivations, places, regions, states and
                      provinces (admin1), cache (unit-tested)
  src/lib/map/        MapLibre + PMTiles map, layer selection, legend, region layer
  src/lib/panel/      place panel, region panel, year strip, charts
  src/lib/components/ search, header
  src/routes/         / (map), /rankings, /methodology, /downloads, /about
  scripts/            fixture generator, Pages-like static server, OG image
  e2e/                Playwright smoke test
```

## Credits

Climate data: ERA5-Land (Copernicus Climate Change Service), processed by the pipeline in this
repository. Place names: GeoNames (CC BY 4.0). Country boundaries: Natural Earth. Basemap:
OpenFreeMap, © OpenMapTiles, data © OpenStreetMap contributors.
