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
- **Variable:** snow depth (the actual thickness of the snowpack, in metres, not its water
  equivalent).
- **Daily values:** we download the official *daily statistics* product
  (`derived-era5-land-daily-statistics`), which averages the 24 hourly values of each day. A day
  is a **UTC calendar day** (see limitations).
- **Days:** 24, 25 and 26 December.
- **Land only:** ERA5-Land also simulates snow on lakes and coastal water. Cells that are mostly
  sea or lake (land-sea mask below 0.5, or lake cover of 0.5 or more) are left blank, so Lake
  Michigan or Lake Ladoga show as water rather than as land with little snow.

Daily-mean snow depth is stored rounded *down* to whole centimetres, so "at least 1 cm" means
exactly that.

## What counts as a white Christmas

There is no single official definition, so the site offers three. A grid cell has a white
Christmas in a given year when the daily-mean snow depth is at least **1 cm**:

| Rule | Condition | Notes |
| --- | --- | --- |
| **Snow on Christmas Day** (default) | on 25 December | "Snow on the ground on Christmas Day." |
| **Snow on all three days** | on each of 24, 25 and 26 December | The German Weather Service (DWD) rule; the strictest. |
| **Snow on any of the three days** | on at least one of 24, 25 or 26 December | The most lenient. |

The **probability** of a white Christmas is the share of years in a period that were white. For
example, 30 % over 1996–2025 means 9 of those 30 Christmases were white.

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
permanent, very deep snowpack, so every Christmas is "white". Shown as 100 %, these areas would
dominate the map and say nothing about Christmas weather. A cell is treated as **glacier** when
both:

1. ERA5-Land's own glacier mask covers at least half of the cell, and
2. it had snow on at least one of the three days in **every** year from 1950 to 2025.

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
value of the grid cell it lies in. A coastal place whose cell is classed as sea uses the nearest land
cell within two cells (about 20 km); places with no land cell that close are left out.

## Limitations: read this before quoting a number

- **A 9 km cell is not your garden.** The value describes the average over the whole cell. Your
  street can differ, especially near coasts, lakes and in cities, which are warmer than their
  surroundings.
- **Mountains are smoothed.** Each cell has one average height. A deep valley and the peaks around
  it share a cell, so valley towns can look snowier than they are, and summits less snowy.
- **The day is a UTC day.** Daily means run from midnight to midnight UTC. In Europe that is within
  an hour or two of local time, but in North America the "25 December" average runs from the
  evening of the 24th to the evening of the 25th local time, and in East Asia from the morning of
  the 25th to the morning of the 26th.
- **A daily mean is not a snapshot.** Snow that falls in the evening and melts by morning may not
  lift the daily mean to 1 cm; a snowpack that melts during the day can still count. Definitions
  based on a morning observation (such as the US weather service's "1 inch on Christmas morning")
  can give different numbers.
- **A reanalysis is a model.** ERA5-Land's snow is not measured directly: it is simulated from
  ERA5 weather, which assimilates observations. It can be too deep or too shallow in places, and
  it tends to be less reliable where few weather stations exist. Compared with station records,
  numbers can differ by several percentage points.
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
- Places: GeoNames (CC BY 4.0). Borders: Natural Earth (public domain).

To cite this dataset: *White Christmas: probability of snow at Christmas from ERA5-Land, 1950–2025,
data version as shown on the site. https://github.com/Kochal/white_xmas*.
