# Methodology

This page explains where the numbers on the map come from, what they mean and where they can
mislead. Everything is computed by the open-source pipeline in this repository, so anyone can
reproduce it.

## The data: ERA5-Land

We use **ERA5-Land**, a global reanalysis of the land surface produced by the European Centre for
Medium-Range Weather Forecasts (ECMWF) for the Copernicus Climate Change Service (C3S). A
reanalysis combines a weather model with millions of past observations to reconstruct the weather
everywhere on Earth, hour by hour, back to 1950.

- **Grid:** 0.1° × 0.1°, about 9 km by 11 km in mid-latitudes (cells get narrower towards the
  poles). The map shows one colour per grid cell.
- **Years:** every December from **1950 to 2025** (76 years). A new year is added each January
  once the December data is published.
- **Variable:** snow depth, in centimetres of snow (not its water equivalent). ERA5-Land's snow
  depth is an **average over the whole 9 km cell**: when only part of the cell is snow-covered,
  the published depth is the snow spread over the whole cell. "5 cm" therefore means "5 cm of
  snow on average across the cell", which is not the same as a ruler reading at one spot.
- **Daily values:** we download the official *daily statistics* product
  (`derived-era5-land-daily-statistics`), which averages the 24 hourly values of each day. A day
  is a **UTC calendar day** (see limitations).
- **Days:** 24, 25 and 26 December.
- **Land only:** ERA5-Land also simulates snow on lakes and coastal water. Cells that are mostly
  sea or lake (land-sea mask below 0.5, or lake cover of 0.5 or more) are left blank, so Lake
  Michigan or Lake Ladoga show as water rather than as land with little snow.

Snow depth is stored rounded *down* to whole centimetres, and thresholds are whole centimetres,
so "at least 5 cm" means exactly that.

## What counts as a white Christmas

A grid cell has a white Christmas in a given year when ERA5-Land's daily-mean snow depth reaches a
**threshold**. The site offers two thresholds and three rules.

### The threshold: 5 cm, calibrated to weather stations (default), or the raw 1 cm

Most people mean "snow on the ground", and weather services count that as at least 1 cm on a
snow ruler. Taken literally, ERA5-Land at ≥ 1 cm is far too snowy: compared with weather stations
it gives a white Christmas Day about **24 percentage points too often** (Munich 72 % against about
34 % measured, Chicago 72 % against 39 %; see the station check below). ERA5-Land carries too much
thin, patchy snow in the lowlands, a bias also reported in the scientific literature.

So the **default threshold is 5 cm in ERA5-Land**, the whole-centimetre value that best matches
"at least 1 cm measured at a weather station". You can switch to the **raw 1 cm** view, which is
ERA5-Land exactly as published. We show both because the calibrated view is the better estimate of
what you would have seen outside, while the raw view is the unadjusted reanalysis that other
studies and datasets use, and the difference between the two is itself a measure of the
uncertainty. Future projections use the calibrated threshold only.

### The three rules

| Rule | Condition | Notes |
| --- | --- | --- |
| **Snow on Christmas Day** (default) | on 25 December | "Snow on the ground on Christmas Day." |
| **Snow on all three days** | on each of 24, 25 and 26 December | The German Weather Service (DWD) rule; the strictest. |
| **Snow on any of the three days** | on at least one of 24, 25 or 26 December | The most lenient. |

The **probability** of a white Christmas is the share of years in a period that were white. For
example, 30 % over 1996–2025 means 9 of those 30 Christmases were white.

## Checked against weather stations

We compare ERA5-Land with weather stations that measured snow depth on 25 December for decades,
from NOAA's Global Historical Climatology Network (GHCN-Daily). The check is part of the pipeline
(`whitexmas stations`), with the station list in `config/pipeline.yaml`, and it writes a full
report (`snow_variable_check.html`).

- **Observed:** a station has a white Christmas Day when its snow depth on 25 December is at least
  1 cm. US stations report whole inches, so for them it is "at least 1 inch as rounded by the
  observer", about 1.3 cm.
- **ERA5-Land:** the same grid cell the map uses for that location, daily-mean snow depth on
  25 December, over exactly the years the station covers.
- **Stations:** 46 with at least 15 overlapping years. 30 are used for the calibration. Left out:
  9 that are white almost every year (every threshold agrees there), 4 with patchy records (often
  reporting snow only when there is some, which inflates their frequency), and 3 whose cell is more
  than 200 m higher or lower than the station (valley towns under a mountain cell, such as Sion).
- **Result:**

  | ERA5-Land threshold | Mean difference to stations | Typical error per station |
  | --- | --- | --- |
  | ≥ 1 cm (raw) | +24.3 percentage points | 24.3 pp |
  | ≥ 4 cm | +4.6 pp | 9.0 pp |
  | **≥ 5 cm (default)** | **+0.3 pp** | **8.1 pp** |
  | ≥ 6 cm | −2.4 pp | 8.4 pp |

  At 5 cm, ERA5-Land and the station agree on white or green in 84 % of station-years. Repeating
  the choice 30 times, each time leaving one station out, picks 5 cm 29 times and 6 cm once.
- **Timing is not the cause:** using the morning value instead of the daily mean (06 UTC in Europe,
  12–13 UTC in North America) changes the difference by less than one percentage point.
- **Scope:** the 30 stations are in Europe and North America, between 40° and 70° N, from sea level
  to 1,611 m (Denver). The calibration is not tested for high mountains, other climates or the
  Southern Hemisphere, where 25 December is midsummer. Individual places can still be off by about
  8 percentage points either way, more in the semi-arid interior of North America, where ERA5-Land
  stays too snowy even at 5 cm.

## Periods

- **1950–2025:** the full record.
- **1961–1990 and 1996–2025:** two 30-year "climate normals", for a *then versus now* comparison.
- **Decades** ending in the latest year: 2016–2025, 2006–2015, …, 1956–1965.

A probability is shown only where at least 80 % of the years in the period have data, which in
practice means every land cell.

## Change and trend

- **Change** is the difference between the two normals, 1996–2025 minus 1961–1990, in percentage
  points (pp). From 40 % to 25 % is a change of −15 pp.
- **Trend** is a straight line fitted (ordinary least squares) through the 76 yearly white/green
  outcomes, expressed in percentage points per decade.
- **Is the trend real?** Whether a Christmas is white depends heavily on the weather of a few days,
  so the yearly series is very noisy. We test each cell with the **Mann-Kendall test**, a standard
  test for a monotonic trend that makes no assumption about the distribution (with the correction
  for tied values, which matters for a series of zeros and ones). Where the test gives p ≥ 0.1, the
  trend could easily be chance, and the trend map **hatches** the cell. Cities in the search list
  show a trend only when p < 0.1.
- We do **not** show trends for single decades: a slope through ten yes/no values is mostly noise.
  For decades we show the probability itself, so you can compare them.

## Glaciers and ice sheets

On glaciers and ice sheets (Greenland, Antarctica, Svalbard, high mountains) ERA5-Land carries a
permanent, very deep snowpack (a fixed 10 m of water equivalent), so every Christmas is "white".
Shown as 100 %, these areas would dominate the map and say nothing about Christmas weather. A cell
is treated as **glacier** when both:

1. ERA5-Land's own glacier mask covers at least half of the cell, and
2. it had at least 1 cm of snow on at least one of the three days in **every** year from 1950 to
   2025 (the same rule for both thresholds, so the glacier areas do not change when you switch).

Glacier cells are drawn **hatched grey** on every map layer and flagged in the place panel, and they
are left out of the country averages.

## Countries

Country figures average all land cells inside each country (Natural Earth borders at 1:10 million),
weighting each cell by its area (cells shrink towards the poles, by the cosine of latitude), with
glacier cells excluded. Countries are identified by their ISO 3166 three-letter code. Where Natural
Earth draws a country as several pieces with the same code (for example Kazakhstan and the leased
Baikonur area, or Australia and its small island territories), the pieces are counted together.

## Places

The search list uses all places with at least 15,000 inhabitants from GeoNames. Each place takes the
value of the grid cell it lies in. A coastal place whose cell is classed as sea or lake uses the
nearest land cell within two cells (about 20 km); places with no land cell that close are left out.

## Limitations: read this before quoting a number

- **A 9 km cell is not your garden.** The value describes the average over the whole cell. Your
  street can differ, especially near coasts, lakes and in cities, which are warmer than their
  surroundings.
- **Mountains are smoothed.** Each cell has one average height. A deep valley and the peaks around
  it share a cell, so valley towns can look snowier than they are, and summits less snowy. In the
  station check, Sion in the Rhône valley sits under a cell almost 1,000 m higher, and ERA5-Land
  calls every Christmas there white.
- **The calibration is an average.** 5 cm matches the stations on average; at a single place the
  difference is typically about 8 percentage points either way (see the station check).
- **The day is a UTC day.** Daily means run from midnight to midnight UTC. In Europe that is within
  an hour or two of local time, but in North America the "25 December" average runs from the
  evening of the 24th to the evening of the 25th local time, and in East Asia from the morning of
  the 25th to the morning of the 26th. The station check found this changes the numbers by less
  than one percentage point.
- **A reanalysis is a model.** ERA5-Land's snow is not measured directly: it is simulated from
  ERA5 weather, which assimilates observations. It tends to be less reliable where few weather
  stations exist.
- **Earlier years are less certain.** Fewer observations went into the reanalysis in the 1950s and
  1960s, especially outside Europe and North America.
- **The old maps are not comparable.** An earlier version of this analysis counted a single hour
  with 1 cm of snow at any time over the three days, and counted the sea as 0 %. Its numbers are
  higher and should not be compared with these.

## Licence and citation

- Data on this site: **CC BY 4.0**. Code: **MIT**. Source code and data downloads:
  <https://github.com/Kochal/white_xmas>.
- Contains modified Copernicus Climate Change Service information (ERA5-Land). Neither the European
  Commission nor ECMWF is responsible for any use that may be made of the Copernicus information or
  data it contains.
- ERA5-Land: Muñoz Sabater, J. (2019): ERA5-Land hourly data from 1950 to present. Copernicus
  Climate Change Service (C3S) Climate Data Store (CDS). DOI: 10.24381/cds.e2161bac. Muñoz-Sabater,
  J. et al. (2021): ERA5-Land: a state-of-the-art global reanalysis dataset for land applications.
  *Earth System Science Data* 13, 4349–4383. DOI: 10.5194/essd-13-4349-2021.
- Snow-depth bias of ERA5-Land in the literature: Monteiro, D. and Morin, S. (2023), *The
  Cryosphere* 17, 3617–3660, DOI: 10.5194/tc-17-3617-2023; Stachura, G. and Ustrnul, Z. (2026),
  *The Cryosphere* 20, 2295–2315, DOI: 10.5194/tc-20-2295-2026.
- Weather stations: Menne, M. J. et al., Global Historical Climatology Network – Daily
  (GHCN-Daily), NOAA National Centers for Environmental Information.
- Places: GeoNames (CC BY 4.0). Borders: Natural Earth (public domain).

To cite this dataset: *White Christmas: probability of snow at Christmas from ERA5-Land, 1950–2025,
data version as shown on the site. https://github.com/Kochal/white_xmas*.
