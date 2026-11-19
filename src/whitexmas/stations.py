"""Station check: ERA5-Land white-Christmas frequency against weather stations.

For every station in ``config/pipeline.yaml`` (``stations.list``) we compare

- the **observed** frequency: GHCN-Daily snow depth (SNWD) on 25 December ≥ 1 cm
  (``obs_threshold_mm``), quality-flagged values dropped. US stations report whole inches, so
  there the effective rule is "≥ 1 inch as rounded by the observer", about ≥ 1.3 cm;
- the **model** frequency: the pipeline's own snow cube at the station's cell (contract rounding;
  the nearest land cell within 2 cells if that cell is water), daily-mean snow depth on
  25 December ≥ T cm, for each whole-cm T in ``thresholds_cm``. The cube stores floored whole
  centimetres, so ``cube >= T`` is exact for whole T;

over the years both cover within the configured period. Stations are listed but left out of the
calibration statistics when they are observed white in at least ``always_white_pct`` % of years
(every threshold agrees there), when their 25 December record covers less than ``min_coverage``
of their span (patchy SYNOP records often omit zero depths), or when the station lies more than
``max_elev_diff_m`` from its cell's mean elevation (a valley station under a mountain cell). The best threshold is the whole-cm T with the smallest mean
absolute bias across the calibration stations; a leave-one-out run repeats the choice without
each station in turn.

Run: ``whitexmas stations`` (writes ``products/sanity/snow_variable_check.html`` and
``stations.csv``; downloads station files from NOAA NCEI into ``external/ghcn/`` once).
"""

from __future__ import annotations

import gzip
import html
import json
import logging
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .config import Config
from .paths import DataPaths

log = logging.getLogger(__name__)

GHCN = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/"
USER_AGENT = "whitexmas-pipeline/0.1 (+https://github.com/Kochal/white_xmas)"


@dataclass
class Station:
    id: str
    name: str
    lat: float = float("nan")
    lon: float = float("nan")
    elev: float = float("nan")


def station_list(cfg: Config) -> list[Station]:
    return [Station(str(i), str(n)) for i, n in cfg.raw["stations"]["list"]]


def _get(url: str, target: Path) -> Path:
    if target.exists() and target.stat().st_size > 0:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = r.read()
    tmp = target.with_suffix(target.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(target)
    return target


def fetch(stations: list[Station], ext_dir: Path) -> None:
    """Station metadata and one CSV per station (cached under external/ghcn/)."""
    from concurrent.futures import ThreadPoolExecutor

    meta = _get(GHCN + "ghcnd-stations.txt", ext_dir / "ghcn" / "ghcnd-stations.txt")
    wanted = {s.id: s for s in stations}
    for line in open(meta, encoding="utf-8", errors="replace"):
        s = wanted.get(line[:11])
        if s:
            s.lat, s.lon, s.elev = float(line[12:20]), float(line[21:30]), float(line[31:37])
    with ThreadPoolExecutor(6) as ex:
        list(
            ex.map(
                lambda s: _get(f"{GHCN}by_station/{s.id}.csv.gz",
                               ext_dir / "ghcn" / f"{s.id}.csv.gz"),
                stations,
            )
        )  # fmt: skip


def read_snwd(path: Path) -> tuple[dict[int, int], float]:
    """{year: SNWD on 25 December in mm} and the share of December values that are 0."""
    dec25: dict[int, int] = {}
    dec_n = dec_zero = 0
    with gzip.open(path, "rt") as f:
        for line in f:
            p = line.rstrip("\n").split(",")
            if len(p) < 6 or p[2] != "SNWD" or p[5] != "":
                continue
            date = p[1]
            if date[4:6] != "12":
                continue
            v = int(p[3])
            dec_n += 1
            dec_zero += v == 0
            if date[6:8] == "25":
                dec25[int(date[:4])] = v
    return dec25, (dec_zero / dec_n if dec_n else float("nan"))


def station_rows(cfg: Config, paths: DataPaths, stations: list[Station]) -> list[dict]:
    import zarr

    from .export.places import cell_index, nearest_valid

    sc = cfg.raw["stations"]
    thresholds = [int(t) for t in sc["thresholds_cm"]]
    cube = zarr.open_group(str(paths.cube), mode="r")
    years = [int(y) for y in cube["year"][:]]
    land = cube["land"][:]
    oro = cube["orography_m"] if "orography_m" in cube else None
    rows = []
    for s in stations:
        p = paths.external / "ghcn" / f"{s.id}.csv.gz"
        if not p.exists() or not np.isfinite(s.lat):
            log.warning("%s (%s): no station data", s.id, s.name)
            continue
        obs, zero_share = read_snwd(p)
        j, i = cell_index(s.lat, s.lon)
        cell = nearest_valid(land, j, i)
        if cell is None:
            log.warning("%s: no land cell within 2 cells", s.name)
            continue
        model = cube["snow_depth_cm"][:, 1, cell[0], cell[1]]
        yrs = [y for y in years if y in obs and cfg.first_year <= y <= cfg.last_year]
        yrs = [y for y in yrs if model[years.index(y)] >= 0]
        if len(yrs) < int(sc.get("min_years", 15)):
            log.info("%s: only %d overlapping years; skipped", s.name, len(yrs))
            continue
        o = np.array([obs[y] >= int(sc.get("obs_threshold_mm", 10)) for y in yrs])
        m = np.array([model[years.index(y)] for y in yrs])
        row = {
            "id": s.id, "name": s.name, "lat": s.lat, "lon": s.lon, "elev_m": s.elev,
            "cell": [int(cell[0]), int(cell[1])], "cell_offset": [cell[0] - j, cell[1] - i],
            "cell_elev_m": float(oro[cell]) if oro is not None else float("nan"),
            "us_inches": s.id.startswith("US"), "years": len(yrs), "first": yrs[0],
            "last": yrs[-1], "dec_zero_share": zero_share, "obs_pct": 100 * o.mean(),
            "coverage": len(yrs) / (yrs[-1] - yrs[0] + 1),
            "model_pct": {t: 100 * float((m >= t).mean()) for t in thresholds},
            "agree_pct": {t: 100 * float(((m >= t) == o).mean()) for t in thresholds},
        }  # fmt: skip
        row["exclude"] = _exclusion(row, sc)
        rows.append(row)
    return rows


def _exclusion(row: dict, sc: dict) -> str | None:
    """Why a station is left out of the calibration statistics (None = used)."""
    if row["obs_pct"] >= float(sc.get("always_white_pct", 95)):
        return "always white"
    if row["coverage"] < float(sc.get("min_coverage", 0.8)):
        return f"patchy record ({row['coverage']:.0%} of years)"
    dz = row["cell_elev_m"] - row["elev_m"]
    if np.isfinite(dz) and abs(dz) > float(sc.get("max_elev_diff_m", 200)):
        return f"cell {dz:+.0f} m vs station"
    return None


def calibrate(rows: list[dict], thresholds: list[int], always_white_pct: float = 95) -> dict:
    """Per-threshold statistics over the calibration stations, best whole-cm T, leave-one-out."""
    cal = [
        r for r in rows
        if not r.get("exclude") and r["obs_pct"] < always_white_pct
    ]  # fmt: skip
    obs = np.array([r["obs_pct"] for r in cal])
    stats = {}
    for t in thresholds:
        mod = np.array([r["model_pct"][t] for r in cal])
        d = mod - obs
        stats[t] = {
            "bias_pp": float(d.mean()),
            "mae_pp": float(np.abs(d).mean()),
            "r": float(np.corrcoef(mod, obs)[0, 1]) if len(cal) > 2 else float("nan"),
            "agree_pct": float(np.mean([r["agree_pct"][t] for r in cal])),
        }

    def best(subset: list[dict]) -> int:
        o = np.array([r["obs_pct"] for r in subset])
        score = [(abs(np.mean([r["model_pct"][t] for r in subset] - o)),
                  np.mean(np.abs([r["model_pct"][t] for r in subset] - o)), t)
                 for t in thresholds]  # fmt: skip
        return min(score)[2]

    loo = [best([r for r in cal if r is not k]) for k in cal]
    return {
        "n_calibration": len(cal),
        "n_excluded": len(rows) - len(cal),
        "stats": stats,
        "best_cm": best(cal),
        "loo_counts": {t: loo.count(t) for t in sorted(set(loo))},
    }


def run(cfg: Config, paths: DataPaths, out_dir: Path | None = None) -> dict:
    stations = station_list(cfg)
    fetch(stations, paths.external)
    rows = station_rows(cfg, paths, stations)
    sc = cfg.raw["stations"]
    thresholds = [int(t) for t in sc["thresholds_cm"]]
    cal = calibrate(rows, thresholds, float(sc.get("always_white_pct", 95)))
    result = {
        "built": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "threshold_cm_in_use": cfg.threshold_cm,
        "years": [cfg.first_year, cfg.last_year],
        "stations": rows,
        "calibration": cal,
    }
    out_dir = out_dir or paths.products / "sanity"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "stations.json").write_text(json.dumps(result, indent=1, default=str))
    _write_csv(out_dir / "stations.csv", rows, thresholds)
    (out_dir / "snow_variable_check.html").write_text(
        render_html(result, thresholds), encoding="utf-8"
    )
    log.info(
        "stations: %d used (%d for calibration); best whole-cm threshold %d cm",
        len(rows), cal["n_calibration"], cal["best_cm"],
    )  # fmt: skip
    return result


def _write_csv(path: Path, rows: list[dict], thresholds: list[int]) -> None:
    import csv

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "lat", "lon", "elev_m", "cell_elev_m", "years", "first",
                    "last", "dec_zero_share", "us_inches", "obs_pct"]
                   + [f"model_ge_{t}cm_pct" for t in thresholds])  # fmt: skip
        for r in rows:
            w.writerow([r["id"], r["name"], r["lat"], r["lon"], r["elev_m"],
                        round(r["cell_elev_m"], 1), r["years"], r["first"], r["last"],
                        round(r["dec_zero_share"], 3), r["us_inches"], round(r["obs_pct"], 1)]
                       + [round(r["model_pct"][t], 1) for t in thresholds])  # fmt: skip


# --------------------------------------------------------------------------- report
STATIC_FINDINGS = """
<h2>What the variables are</h2>
<ul>
<li><b><code>sde</code>, snow depth (paramId 3066, m)</b>. In the IFS snow scheme used by ERA5-Land
(single layer, IFS Cy45r1) the prognostic variable is the snow mass <i>S</i> per unit grid-box
area; the depth over the <i>snow-covered</i> part is <i>D</i><sub>sn</sub> =
1000·<i>S</i>/(ρ<sub>sn</sub>·<i>c</i><sub>sn</sub>), "not a grid-averaged quantity" (IFS Cy45r1
Part IV, §8.4.1, Eq. 8.33). The published <code>sde</code>, however, behaves as the
<b>grid-box mean</b> 1000·<i>S</i>/ρ<sub>sn</sub>: in partly covered hours it equals snow cover ×
10 cm (median ratio 1.0 at Munich, Zurich and Chicago), not the fixed 10 cm that
<i>D</i><sub>sn</sub> would give. "<code>sde</code> ≥ T cm" therefore means "T cm spread over the
whole 9 km cell".</li>
<li><b><code>sd</code>, snow depth water equivalent (paramId 141, m w.e.)</b>: "the depth of snow from
the snow-covered area of a grid box … the depth the water would have if the snow melted and was
spread evenly over the whole grid box" (ECMWF parameter database). <code>sde</code> =
1000·<code>sd</code>/<code>rsn</code>.</li>
<li><b><code>snowc</code>, snow cover (paramId 260038, %)</b>: <i>c</i><sub>sn</sub> = min(1,
(1000·<i>S</i>/ρ<sub>sn</sub>)/0.10 m) (Cy45r1 Part IV, Eq. 8.2). In the data it saturates below
100 % under forest (88.9 % at Oslo under 0.5–2 m of snow), so "snow cover ≥ 50 %" is a
vegetation-dependent depth threshold.</li>
<li><b>Glaciers</b> carry a fixed 10 m of water equivalent (ERA5-Land documentation, known issues).</li>
</ul>
<p><b>Literature.</b> ERA5-Land overestimates winter snow accumulation in the Alps (Monteiro &amp;
Morin 2023); in Central Europe its snow-depth bias is mostly positive below 1000 m and it
underestimates snow in complex terrain higher up (Stachura &amp; Ustrnul 2026); reanalyses tend to
overestimate shallow snowpacks (Clim. Dyn. 2022, Tibetan Plateau); ERA5-Land grossly overestimates
positive snow-depth anomalies over Canada and Alaska (Sarpong &amp; Nazemi, preprint).</p>

<h2>Other checks (CDS point series, 25 of these stations, D-15)</h2>
<ul>
<li><b>Timing is not the cause.</b> Europe: the 06 UTC value (local morning) is as biased as the
UTC daily mean (+20.2 against +20.9 pp at 1 cm). North America: 12 and 13 UTC (local morning) give
+24.6 and +24.7 pp against +25.2 pp for the daily mean at 1 cm, and +1.8 / +2.0 against +1.6 pp at
4 cm (11 stations).</li>
<li><b>Other variables do no better</b> (25 stations): SWE ≥ 5 mm +4.3 pp bias, MAE 7.8;
snow cover ≥ 50 % −4.1 pp, MAE 6.0, r 0.98; both need a new global download.</li>
<li><b>Elevation</b> differences between station and cell do not explain the bias (r = 0.03).</li>
</ul>

<h2>Sources</h2>
<ul>
<li>ECMWF IFS Documentation Cy45r1, Part IV: Physical Processes, §8.4, Eqs. 8.2 and 8.33.
<a href="https://www.ecmwf.int/sites/default/files/elibrary/2018/18714-part-iv-physical-processes.pdf">ecmwf.int</a></li>
<li>ECMWF parameter database (141, 33, 3066, 260038). <a href="https://codes.ecmwf.int/grib/param-db/">codes.ecmwf.int</a></li>
<li>ERA5-Land data documentation. <a href="https://confluence.ecmwf.int/display/CKB/ERA5-Land%3A+data+documentation">confluence.ecmwf.int</a></li>
<li>Muñoz-Sabater, J. et al. (2021), ESSD 13, 4349–4383, doi:10.5194/essd-13-4349-2021</li>
<li>Monteiro, D. and Morin, S. (2023), The Cryosphere 17, 3617–3660.
<a href="https://tc.copernicus.org/articles/17/3617/2023/">doi:10.5194/tc-17-3617-2023</a></li>
<li>Stachura, G. and Ustrnul, Z. (2026), The Cryosphere 20, 2295–2315.
<a href="https://tc.copernicus.org/articles/20/2295/2026/">doi:10.5194/tc-20-2295-2026</a></li>
<li>Climate Dynamics (2022), snow depth over the Tibetan Plateau in reanalyses.
<a href="https://link.springer.com/article/10.1007/s00382-022-06376-0">doi:10.1007/s00382-022-06376-0</a></li>
<li>Sarpong &amp; Nazemi, EGUsphere preprint egusphere-2024-4150.</li>
<li>Menne, M. J. et al.: GHCN-Daily, NOAA NCEI. <a href="https://www.ncei.noaa.gov/pub/data/ghcn/daily/">ncei.noaa.gov</a></li>
</ul>
"""


def render_html(res: dict, thresholds: list[int]) -> str:
    cal = res["calibration"]
    st = cal["stats"]
    best = cal["best_cm"]
    rows = sorted(res["stations"], key=lambda r: r["obs_pct"])
    show = [t for t in (1, 2, 3, 4, 5, 6) if t in thresholds]

    def cls(v: float, o: float) -> str:
        return "hi" if v - o > 10 else "lo" if v - o < -10 else ""

    trs = ""
    for r in rows:
        aw = bool(r.get("exclude")) or r["obs_pct"] >= 95
        cells = "".join(
            f"<td class='{cls(r['model_pct'][t], r['obs_pct'])}'>{r['model_pct'][t]:.0f}</td>"
            for t in show
        )
        off = (
            ""
            if r["cell_offset"] == [0, 0]
            else f" ({r['cell_offset'][0]:+d},{r['cell_offset'][1]:+d})"
        )  # noqa: E501
        trs += (
            f"<tr{' class=aw' if aw else ''}><td>{html.escape(r['name'])}"
            f"{' ⁱ' if r['us_inches'] else ''}"
            f"{' (' + html.escape(r.get('exclude') or 'always white') + ')' if aw else ''}</td>"
            f"<td>{r['years']} ({r['first']}–{r['last']})</td>"
            f"<td>{r['elev_m']:.0f} / {r['cell_elev_m']:.0f}{off}</td>"
            f"<td><b>{r['obs_pct']:.0f}</b></td>{cells}</tr>"
        )
    srows = "".join(
        f"<tr{' class=best' if t == best else ''}><td>≥ {t} cm</td><td>{st[t]['bias_pp']:+.1f}</td>"
        f"<td>{st[t]['mae_pp']:.1f}</td><td>{st[t]['r']:.2f}</td><td>{st[t]['agree_pct']:.1f}</td></tr>"  # noqa: E501
        for t in thresholds
    )
    loo = ", ".join(f"{t} cm × {n}" for t, n in cal["loo_counts"].items())
    s1 = st.get(1, {})
    head = "".join(f"<th>≥ {t} cm</th>" for t in show)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Snow threshold check</title>
<style>
:root{{--bg:#fff;--fg:#1d2433;--mut:#5b6475;--line:#d9dde5;--hi:#fde2dc;--lo:#dbe9f6;--acc:#1d4e89;--aw:#f3f4f6}}
@media (prefers-color-scheme: dark){{:root{{--bg:#14171d;--fg:#e6e9ef;--mut:#9aa3b2;--line:#2c323d;
--hi:#5a2a24;--lo:#1f3a57;--acc:#8db8ea;--aw:#1c2028}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;margin:0 auto;max-width:1100px;padding:24px 16px}}
h1{{font-size:1.6em;margin:.2em 0}} h2{{margin-top:1.8em;border-bottom:1px solid var(--line)}}
.box{{border-left:4px solid var(--acc);padding:8px 14px;margin:14px 0}}
.wrap{{overflow-x:auto}} table{{border-collapse:collapse;margin:10px 0;font-size:13px}}
td,th{{border:1px solid var(--line);padding:3px 7px;text-align:right;white-space:nowrap}}
td:first-child,th:first-child{{text-align:left}} .hi{{background:var(--hi)}} .lo{{background:var(--lo)}}
tr.aw td{{background:var(--aw);color:var(--mut)}} tr.best td{{font-weight:700}} .mut{{color:var(--mut)}}
</style></head><body>
<h1>Which snow-depth threshold matches weather stations?</h1>
<p class="mut">Built {res["built"]} by <code>whitexmas stations</code>. Threshold currently in use:
{res["threshold_cm_in_use"]} cm. {len(rows)} GHCN-Daily stations, {cal["n_calibration"]} used for
calibration; {cal["n_excluded"]} are shown greyed and left out (always white, patchy record, or
more than 200 m below or above their cell's mean elevation).</p>
<div class="box"><b>Result.</b> At the current 1 cm, ERA5-Land's daily-mean snow depth gives a white
Christmas Day <b>{s1.get("bias_pp", float("nan")):+.0f} pp</b> more often than stations observe
≥ 1 cm (mean over the calibration stations; MAE {s1.get("mae_pp", float("nan")):.0f} pp). The
whole-centimetre threshold that matches the stations best is <b>{best} cm</b>: bias
{st[best]["bias_pp"]:+.1f} pp, MAE {st[best]["mae_pp"]:.1f} pp, r {st[best]["r"]:.2f},
white/green agreement in {st[best]["agree_pct"]:.0f} % of station-years. Leave-one-out picks
{loo}.<br><br><b>Scope.</b> Tested in Northern Hemisphere mid- and high-latitude climates:
lowland and Alpine Europe, Scandinavia, eastern and western North America, Hokkaido, the
Sea-of-Japan coast and Korea, at stations below about 1000 m (Hohenpeissenberg 977 m is the
highest). It is not tested for high mountains, the Arctic or the Southern Hemisphere.</div>

<h2>Calibration across stations</h2>
<table><tr><th>ERA5-Land rule</th><th>mean bias (pp)</th><th>MAE (pp)</th><th>r across stations</th>
<th>agreement (%)</th></tr>{srows}</table>

<h2>Stations</h2>
<p>Observed: SNWD on 25 December ≥ 10 mm, quality-flagged values dropped. ⁱ US stations report whole
inches, so their rule is "≥ 1 inch as rounded by the observer" (about ≥ 1.3 cm), which lowers
their observed frequency slightly. Model: the pipeline's cube at the station cell (contract
rounding; offset in cells shown where the station cell is water), daily-mean snow depth on
25 December (UTC day), same years. Red: model more than 10 pp above the station; blue: more than
10 pp below. Elevation: station / cell mean.</p>
<div class="wrap"><table><tr><th>station</th><th>years</th><th>elev. m</th><th>observed %</th>{head}</tr>
{trs}</table></div>
{STATIC_FINDINGS}
</body></html>"""
