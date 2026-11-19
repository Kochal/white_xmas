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
it gives a white Christmas Day about **20 percentage points too often** across 827 stations
(on the original hand-picked list, for example, Munich 72 % against about 34 % measured and Chicago
72 % against 39 %; see the station check below). ERA5-Land carries too much
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
(`whitexmas stations`): it picks the stations itself, applies the same rules everywhere and writes
a full report (`snow_variable_check.html`) and a table of every station it looked at
(`stations_global.csv`). Differences are given in **percentage points (pp)**: if ERA5-Land is
white in 40 % of years and the station in 35 %, the difference is +5 pp.

- **Observed:** a station has a white Christmas Day when its snow depth on 25 December is at least
  1 cm. US stations report whole inches, so for them it means a reported depth of at least 1 inch;
  observers round, so that is in effect at least half an inch (about 1.3 cm).
- **ERA5-Land:** the same grid cell the map uses for that location (the nearest land cell within
  two cells for a coastal station whose own cell is water), daily-mean snow depth on 25 December,
  over exactly the years the station covers. Each station and year is one comparison, a
  *station-year*.

### Which stations

Every Northern-Hemisphere GHCN-Daily station whose snow-depth record spans at least 15 years of
1950–2025 is a candidate: 24,049 stations with a land cell nearby. To stop dense networks (the
United States, Canada, Sweden, Germany) from drowning out everything else, we keep **one station
per 1° × 1° box**: the one with the longest record (ties: main weather-service stations before
volunteer networks, then the station closest to its cell's elevation). If it fails a quality rule,
the next one in the box is tried, up to six.

The quality rules matter more than anything else here, because many snow-depth records have gaps
that are not random:

- Values flagged by NOAA's quality control are dropped.
- **Snow depth must be reported every day the station reported anything.** A year counts only if
  the station gave a snow depth on at least 90 % of the December days on which it reported
  precipitation or temperature. Many records, especially those built from international weather
  reports, give a snow depth only when snow lies and leave snow-free days blank. Counted naively,
  such a station loses its green Christmases and looks white every year. A station where more
  than 20 % of years fail this test is left out.
- **Snow depth must not be filled with zeros.** A station is left out when, in more than 20 % of
  the Decembers in which it measured at least 20 cm of snowfall, it never reported any snow on the
  ground.
- At least 15 usable years, covering at least 80 % of the station's span.
- Kept in the table but left out of the statistics: stations white in 95 % of years or more (every
  threshold agrees there), stations where both the station and ERA5-Land at 1 cm are white in
  fewer than 5 % of years (they say nothing about the threshold), and stations more than 200 m
  above or below the mean elevation of their cell.
- Flagged, not dropped: coastal stations, US stations (whole inches), stations where the station
  or its cell lies at or above 1,500 m, stations whose cell is more than 30 % lake, and records
  that come mostly from international weather reports (GHCN source "GSOD", which omits zero
  depths).

Of 3,504 boxes with candidates, 1,563 have a station that passes the quality rules. We examined
5,665 stations; **827 are used** (46,653 station-years), from sea level to 3,031 m and from 31° to
70° N. The most common reasons for leaving a station out: snow depth reported only when snow lies
(1,406), a patchy record (1,115), snow depth missing on other observing days (594), and no
25 December snow depth at all (520).

### Result

| ERA5-Land threshold | ERA5-Land minus stations | Typical size of the difference |
| --- | --- | --- |
| ≥ 1 cm (raw) | +20.2 pp | 20.3 pp |
| ≥ 4 cm | +4.7 pp | 8.7 pp |
| **≥ 5 cm (default)** | **+1.6 pp** (−1.2 to +5.1) | **8.6 pp** |
| ≥ 6 cm | −1.2 pp | 9.3 pp |

Positive means ERA5-Land is white more often than the station; the typical size is the average
difference per station, ignoring its sign. The range in brackets is a 95 % uncertainty interval.
It comes from re-drawing, many times over, both the stations (in 10° × 10° blocks) and the
calendar years (a *two-way bootstrap*): neighbouring stations share the same weather, and all
stations share the same Christmases, so neither counts as fully independent evidence. Drawing
only stations in 5° blocks, as an earlier version did, gives an interval about a third narrower.
At 5 cm, ERA5-Land and the station agree on white or green in 86.5 % of station-years.

**Judged by the mean difference alone, 6 cm fits the full set of stations slightly better:**
−1.2 against +1.6 pp, and the threshold at which the mean difference would be exactly zero lies at
5.6 cm (4.6 to 7.1). Judged per station, 5 cm does better: its typical difference is the smallest
(8.6 pp, against 8.7 at 4 cm and 9.3 at 6 cm), and its median difference is exactly 0 (−2.6 pp at
6 cm). The mean is pulled up by the Rockies and the Pacific side of North America, where ERA5-Land
is far too snowy. Counting every region once instead of every station, 5 cm is +3.2 pp (+0.9 to
+5.3) too snowy and the zero point lies at 6.2 cm (5.4 to 7.2); that interval holds the six regions
themselves fixed. Two more checks point towards 5 cm or lower:

- **Stations below their cell.** The difference is larger where the cell's mean elevation lies
  above the station: by about **7 pp per 100 m** (4 to 10 pp) among stations of the same region
  within the 200 m limit. That is what one expects when a town in a valley shares a cell with
  higher, snowier ground, but it is a correlation, and it is lopsided: the few stations that lie
  above their cell are not too green. For the 611 stations within 50 m of their cell's elevation,
  the difference at 5 cm is −1.4 pp (−3.7 to +1.2) and the zero point lies at 4.5 cm (3.9 to 5.5):
  between 4 and 5 cm (4 cm has the smaller typical difference, 6.4 against 6.9 pp).
- **Out of sample** (below), re-fitting a single threshold does not beat the fixed 5 cm.

So the best single threshold depends on which stations one trusts to represent their cell: about
4.5 cm for stations at their cell's elevation, 5.6 to 6.2 cm for all stations. 5 cm lies within
that range. The numbers also depend on the rules: keeping the stations more than 200 m from their
cell's elevation raises the difference at 5 cm to +3.8 pp (best fit 7 cm), relaxing the record
requirements to 10 years and 50 % coverage to +2.8 pp; keeping only stations within 100 m of their
cell's elevation lowers it to +0.2 pp, and keeping the always-white and almost-never-white stations
to +1.0 pp.

### Where 5 cm is consistent with the stations, and where it is not

Difference at 5 cm, ERA5-Land minus stations (pp), with the 95 % interval; second column: only the
stations within 50 m of their cell's elevation.

| Region (stations) | All stations | At cell elevation |
| --- | --- | --- |
| Eastern North America (306) | −0.8 (−4.3 to +2.9) | −2.4 (259) |
| Great Plains & Prairies (197) | −1.7 (−5.3 to +3.1) | −2.4 (172) |
| Rockies & Intermountain West (106) | **+10.7** (+6.0 to +16.9) | +11.3 (43) |
| Western & Central Europe (78) | **−5.3** (−9.3 to −0.7) | −6.6 (68) |
| Pacific North America (70) | **+12.7** (+8.8 to +17.8) | +6.1 (32) |
| Nordic countries (57) | +3.5 (−4.9 to +9.4) | −3.5 (31) |

- **Consistent:** the eastern half of North America and the Great Plains and Prairies, where most
  of the stations are (zero points between 4.5 and 4.7 cm); among their stations at cell
  elevation, ERA5-Land at 5 cm is about 2 pp too green, within the uncertainty. The Nordic
  countries are consistent too, but with a wide interval.
- **Too snowy:** the Rocky Mountains, the Intermountain West and the Pacific side of North America,
  about 11 to 13 pp. The Rockies would need more than 8 cm (still +2 pp too snowy at 8 cm); the
  Pacific side is still 6.5 pp too snowy at 8 cm. In the Rockies even stations at their cell's
  elevation are 11 pp too snowy, so elevation does not explain it there.
- **Too green:** the lowlands of western and central Europe (mostly Germany, the Netherlands and
  the United Kingdom), where about 3 cm would match.
- **Is one threshold for the whole world justified?** We held out each 10° × 10° block of stations
  in turn and chose the whole-centimetre threshold with the smallest mean difference on the
  others. That re-fitted threshold is 6 cm in 38 of 41 blocks. On the held-out stations it brings
  the mean difference closer to zero than the fixed 5 cm (−0.8 against +1.6 pp) but makes the
  typical difference per station larger (9.5 against 8.6 pp) and the typical regional difference
  larger (6.4 against 5.8 pp). A separate threshold per region would cut the typical regional
  difference to about 2 pp and the typical difference per station to 8.0 pp. (5 cm itself was
  chosen earlier on 30 stations, 17 of which are among the 827 here, so the comparison is not
  entirely independent.)
- **Scatter per station.** At a single station, ERA5-Land at 5 cm is typically about 9 pp off
  either way. Chance alone (a station has only a few decades of Christmases) would give about
  4 pp, so most of the scatter is real local difference, not noise. The largest differences are
  named in the report: Geneva-Cointrin (+62 pp, under a cell 120 m higher than the airport), two
  stations in dry basins of the Rocky Mountain West (about +58 pp), and Milwaukee (−36 pp, under a
  cell that is more than a third Lake Michigan).
- **Time of day.** The ERA5-Land value is a UTC daily mean, while stations measure once a day,
  usually in the morning. On 25 of the original 30 hand-picked stations, using the morning value
  instead changed the difference by less than one percentage point; this was not repeated for the
  827 stations, because the pipeline keeps daily means only.

### What is untested

- **Most of Eurasia.** GHCN-Daily snow depth from Russia, Central Asia, China, Mongolia, Japan,
  Korea, Turkey, Eastern Europe and the Alps comes almost entirely from international weather
  reports that leave snow-free days blank, so those stations fail the rules above. Fewer than
  eight usable stations remain in Alaska and northern Canada (5), Eastern Europe (4), the Alps (2),
  Japan (1, Yokota Air Base) and Korea (1, Camp Red Cloud), both US military stations; none in
  European Russia, Siberia, Central Asia, China, Mongolia, the
  Tibetan Plateau, the Middle East or the Arctic islands. Of the 827 stations, 684 are in the
  United States and Canada.
- **High mountains** are tested only in the Rockies: 56 stations where the station or its cell lies
  at or above 1,500 m; ERA5-Land at 5 cm is 11 pp too snowy there (8 to 16).
- **The Southern Hemisphere** is out of scope: 25 December is midsummer there.
- Other national archives with daily snow depth and open licences could fill some gaps (Finland's
  FMI, Japan's JMA, NSIDC's historical daily snow depth for the former Soviet Union up to 1995,
  MeteoSwiss and several Italian Alpine services). They are not used yet.

### What it means for the 5 cm default

The default stays at 5 cm for now. It has the smallest typical difference per station and a
median difference of zero, it lies inside the range of best-fitting single thresholds (about
4.5 cm for stations at their cell's elevation, 5.6 to 6.2 cm for all stations by the mean), and a
re-fitted 6 cm does not do better on held-out stations except in the mean. What a single
threshold cannot fix is regional: about 11 to 13 pp too snowy in western North America and about
5 pp too green in the lowlands of western and central Europe, and there is no usable station
data for most of Eurasia.

The original calibration (decision D-17 in the project's decision log) used 30 hand-picked
stations in Europe and North America and found +0.3 pp at 5 cm. Under the rules above, 29 of those
30 still qualify and give +0.3 pp (typical difference 8.1 pp). The hand-picked list is still
available (`whitexmas stations --mode list`) and reproduces the D-17 numbers unchanged.

### Station files

`products/stations/stations_global.csv` has one row per examined station: id, name, latitude,
longitude, elevation, country and US or Canadian state, region, the ERA5-Land cell and its
elevation, years used, observed share and ERA5-Land share at every threshold, station-year counts
at 5 cm, status, reason and flags. `stations_global.json` is a compact copy for web use (schema
`wx-stations-v1`): `fields` names the columns, and `rows` holds one array per station that passes
the quality rules, with `id`, `name`, `lat`, `lon`, `elev_m`, `country` (GHCN code), `region`,
`years`, `first`, `last`, `obs_pct` (share of years with at least 1 cm observed), `era5_1cm_pct`,
`era5_5cm_pct`, `status` (`used` or `separated`) and `flags` (`us_inches`, `coastal`,
`high_mountain`, `elev_mismatch`, `lake`, `gsod_sourced`). "Always white" stations whose record
comes mostly from GSOD are left out of it: their green years would not have been reported.

The station values come from GHCN-Daily, which NOAA distributes without use restrictions; some of
them reached GHCN from national services or from ECA&D, and the statistics here rely on GHCN's
redistribution terms. GHCN-Daily changes daily, so a fresh run on another day differs slightly:
`stations.json` records the examined station ids and checksums of the metadata files, and
`stations.auto.pin` reruns on exactly those stations. The downloaded station files take about
2.6 GB.

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
  calls every Christmas there white. Across the station check, stations lying below their cell's
  mean elevation tend to be too snowy, by about 7 percentage points per 100 m.
- **The calibration is an average.** 5 cm matches the stations on average; at a single place the
  difference is typically about 9 percentage points either way. ERA5-Land at 5 cm is still too
  snowy in western North America and too green in the lowlands of western and central Europe, and
  the calibration is untested for most of Eurasia (see the station check).
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
- Weather stations: Menne, M. J., I. Durre, R. S. Vose, B. E. Gleason and T. G. Houston (2012):
  An overview of the Global Historical Climatology Network-Daily Database. *Journal of Atmospheric
  and Oceanic Technology* 29, 897–910, DOI: 10.1175/JTECH-D-11-00103.1. Data: GHCN-Daily, NOAA
  National Centers for Environmental Information, DOI: 10.7289/V5D21VHZ (accessed November 2026).
- Places: GeoNames (CC BY 4.0). Borders: Natural Earth (public domain).

To cite this dataset: *White Christmas: probability of snow at Christmas from ERA5-Land, 1950–2025,
data version as shown on the site. https://github.com/Kochal/white_xmas*.
