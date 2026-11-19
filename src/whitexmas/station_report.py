"""HTML report of the global station assessment (``products/stations/snow_variable_check.html``).

Static HTML (no scripts): summary first, then the regional tables, a map and scatter plots of the
bias at each station (inline SVG, native tooltips), and the per-station tables in collapsible
sections. Light and dark themes follow the reader's system setting.
"""

from __future__ import annotations

import html
import math

import numpy as np

from . import station_stats as ss

E = html.escape
NAN = float("nan")

# Diverging bins for the bias (pp): blue = ERA5-Land too green, red = too snowy, grey = close.
BIAS_EDGES = [-30, -15, -5, 5, 15, 30]
BIAS_LABELS = ["< −30", "−30 to −15", "−15 to −5", "−5 to 5", "5 to 15", "15 to 30", "> 30"]
BIAS_VARS = ["--b3", "--b2", "--b1", "--n0", "--r1", "--r2", "--r3"]


def _f(v, nd: int = 1, sign: bool = False) -> str:
    if v is None:
        return "–"
    if isinstance(v, str):
        return v
    if isinstance(v, float) and math.isinf(v):
        return "> max" if v > 0 else "< min"
    if not np.isfinite(v):
        return "–"
    return f"{v:+.{nd}f}" if sign else f"{v:.{nd}f}"


def _ci(ci, nd: int = 1) -> str:
    if not ci:
        return ""
    lo, hi = ci

    def one(x):
        if isinstance(x, float) and math.isinf(x):
            return "<1" if x < 0 else ">8"
        return _f(x, nd, sign=False) if x is not None else "–"

    return f"<span class=ci>[{one(lo)}, {one(hi)}]</span>"


def _tstar(v) -> str:
    if isinstance(v, float) and math.isinf(v):
        return "< 1" if v < 0 else "> 8"
    return _f(v, 1)


def _bin(v: float) -> int:
    for k, e in enumerate(BIAS_EDGES):
        if v < e:
            return k
    return len(BIAS_EDGES)


def verdict(s: dict, t: int) -> str:
    """Plain words for the mean bias at T and its 95 % interval."""
    ci = s.get("bias_ci", {}).get(t)
    b = s["bias_pp"][t]
    if not ci:
        return "too few stations"
    lo, hi = ci
    if lo > 0:
        return f"too snowy ({b:+.0f} pp)"
    if hi < 0:
        return f"too green ({b:+.0f} pp)"
    return f"consistent ({b:+.0f} pp)"


# --------------------------------------------------------------------------- figures
LON0, LON1, LAT0, LAT1 = -170.0, 180.0, 20.0, 80.0
MAP_W = 1000.0
KX = MAP_W / (LON1 - LON0)
KY = KX * 1.25  # mild vertical stretch so mid-latitudes are not squashed
MAP_H = (LAT1 - LAT0) * KY


def _xy(lon: float, lat: float) -> tuple[float, float]:
    return (lon - LON0) * KX, (LAT1 - lat) * KY


def _outlines(paths) -> str:
    """Simplified Natural Earth country outlines as one SVG path (empty if unavailable)."""
    z = paths.external / "ne_10m_admin_0_countries.zip" if paths is not None else None
    if z is None or not z.exists():
        return ""
    try:
        from shapely import box, simplify

        from .export.regions import read_countries

        clip = box(LON0, LAT0, LON1, LAT1)
        parts = []
        for c in read_countries(z):
            g = c["geom"]
            if g is None:
                continue
            g = simplify(g.intersection(clip), 0.3)
            if g.is_empty:
                continue
            polys = getattr(g, "geoms", [g])
            for p in polys:
                if p.geom_type != "Polygon" or p.area < 0.5:
                    continue
                pts = [_xy(x, y) for x, y in p.exterior.coords]
                parts.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
        return f"<path class=land d='{''.join(parts)}'/>"
    except Exception:  # the map still works without outlines
        return ""


def _dot_title(r: dict, t: int) -> str:
    return E(
        f"{r['name']} ({r['id']}), {r['region']}: station {r['obs_pct']:.0f} %, "
        f"ERA5-Land ≥ {t} cm {r['model_pct'][t]:.0f} % ({ss.bias(r, t):+.0f} pp), "
        f"{r['years']} years, {r['elev_m']:.0f} m"
    )


def _map(rows: list[dict], t: int, paths) -> str:
    dots = []
    for r in sorted(rows, key=lambda r: abs(ss.bias(r, t))):
        x, y = _xy(r["lon"], r["lat"])
        if not (0 <= x <= MAP_W and 0 <= y <= MAP_H):
            continue
        k = _bin(ss.bias(r, t))
        dots.append(
            f"<circle cx='{x:.1f}' cy='{y:.1f}' r='3.2' style='fill:var({BIAS_VARS[k]})'>"
            f"<title>{_dot_title(r, t)}</title></circle>"
        )
    return (
        f"<svg class=map viewBox='0 0 {MAP_W:.0f} {MAP_H:.0f}' role=img "
        f"aria-label='Map of stations coloured by bias at {t} cm'>"
        f"{_outlines(paths)}<g class=dots>{''.join(dots)}</g></svg>"
    )


def _legend() -> str:
    items = "".join(
        f"<span><i style='background:var({v})'></i>{E(lab)}</span>"
        for v, lab in zip(BIAS_VARS, BIAS_LABELS, strict=True)
    )
    return (
        "<div class=legend><b>ERA5-Land minus station, pp:</b> "
        f"{items}<span class=mut>blue: ERA5-Land too green · red: too snowy</span></div>"
    )


def _scatter(
    rows: list[dict], x_of, y_of, xlab: str, ylab: str, xr, yr, diag: bool, t: int, zero_y=False
) -> str:
    W, H, L, B, R, T = 460, 340, 48, 40, 12, 10
    pw, ph = W - L - R, H - T - B

    def sx(v):
        return L + (min(max(v, xr[0]), xr[1]) - xr[0]) / (xr[1] - xr[0]) * pw

    def sy(v):
        return T + ph - (min(max(v, yr[0]), yr[1]) - yr[0]) / (yr[1] - yr[0]) * ph

    ticks = []
    for v in np.linspace(xr[0], xr[1], 5):
        ticks.append(f"<text x='{sx(v):.0f}' y='{H - B + 16}' class=tk text-anchor=middle>"
                     f"{v:.0f}</text>")  # fmt: skip
    for v in np.linspace(yr[0], yr[1], 5):
        ticks.append(f"<line x1='{L}' x2='{W - R}' y1='{sy(v):.1f}' y2='{sy(v):.1f}' class='grid'/>"
                     f"<text x='{L - 6}' y='{sy(v) + 4:.1f}' class=tk text-anchor=end>{v:.0f}</text>")  # fmt: skip
    ref = ""
    if diag:
        ref = f"<line x1='{sx(xr[0])}' y1='{sy(yr[0])}' x2='{sx(xr[1])}' y2='{sy(yr[1])}' class='ref'/>"
    if zero_y:
        ref = f"<line x1='{L}' x2='{W - R}' y1='{sy(0):.1f}' y2='{sy(0):.1f}' class='ref'/>"
    dots = "".join(
        f"<circle cx='{sx(x_of(r)):.1f}' cy='{sy(y_of(r)):.1f}' r='3' "
        f"style='fill:var({BIAS_VARS[_bin(ss.bias(r, t))]})'><title>{_dot_title(r, t)}</title></circle>"
        for r in rows
        if np.isfinite(x_of(r)) and np.isfinite(y_of(r))
    )
    return (
        f"<svg class=sc viewBox='0 0 {W} {H}' role=img aria-label='{E(ylab)} against {E(xlab)}'>"
        f"{''.join(ticks)}{ref}<g class=dots>{dots}</g>"
        f"<text x='{L + pw / 2}' y='{H - 6}' class=ax text-anchor=middle>{E(xlab)}</text>"
        f"<text transform='translate(13 {T + ph / 2}) rotate(-90)' class=ax "
        f"text-anchor=middle>{E(ylab)}</text></svg>"
    )


# --------------------------------------------------------------------------- tables
def _group_table(groups: dict, t: int, loro: dict | None = None, min_n: int = 8) -> str:
    head = (
        "<tr><th>group</th><th>stations</th><th>station-years</th><th>observed %</th>"
        "<th>bias ≥ 1 cm</th><th>bias ≥ 4 cm</th>"
        f"<th>bias ≥ {t} cm [95 % CI]</th><th>bias ≥ 6 cm</th><th>MAE ≥ {t} cm</th>"
        f"<th>hit rate</th><th>false-alarm ratio</th><th>Heidke</th>"
        "<th>best whole cm</th><th>crossing T* [95 % CI]</th>"
        + ("<th>T chosen without it → bias</th>" if loro is not None else "")
        + "</tr>"
    )
    trs = []
    for name, s in sorted(groups.items(), key=lambda kv: -kv[1].get("n", 0)):
        if not s.get("n"):
            continue
        few = s["n"] < min_n
        c = s["contingency"]
        lo = ""
        if loro is not None:
            x = loro.get(name)
            lo = (f"<td>{x['t_chosen_without']} cm → {x['bias_at_chosen_pp']:+.1f}</td>"
                  if x else "<td>–</td>")  # fmt: skip
        trs.append(
            f"<tr{' class=few' if few else ''}><td>{E(name)}</td><td>{s['n']}</td>"
            f"<td>{s['station_years']:,}</td><td>{s['obs_pct']:.0f}</td>"
            f"<td>{_f(s['bias_pp'][1], 1, True)}</td><td>{_f(s['bias_pp'][4], 1, True)}</td>"
            f"<td><b>{_f(s['bias_pp'][t], 1, True)}</b> {_ci(s.get('bias_ci', {}).get(t))}</td>"
            f"<td>{_f(s['bias_pp'][6], 1, True)}</td><td>{_f(s['mae_pp'][t])}</td>"
            f"<td>{_f(c['hit_rate'] * 100, 0)} %</td><td>{_f(c['false_alarm_ratio'] * 100, 0)} %</td>"
            f"<td>{_f(c['heidke'], 2)}</td><td>{s['best_whole_cm']} cm</td>"
            f"<td>{_tstar(s['t_star_cm'])} {_ci(s.get('t_star_ci'))}</td>{lo}</tr>"
        )
    return f"<div class=wrap><table>{head}{''.join(trs)}</table></div>"


def _station_table(rows: list[dict], t: int) -> str:
    head = (
        "<tr><th>station</th><th>id</th><th>years</th><th>elev. m (station / cell)</th>"
        f"<th>observed %</th><th>ERA5 ≥ 1 cm</th><th>ERA5 ≥ {t} cm</th><th>bias</th>"
        "<th>status</th><th>flags</th></tr>"
    )
    trs = []
    for r in sorted(rows, key=lambda r: (r["status"] != "used", r["name"])):
        mp = r.get("model_pct")
        rng = f"{r['years']} ({r['first']}–{r['last']})" if r["first"] else str(r["years"])
        b = ss.bias(r, t) if mp else NAN
        cls = "" if r["status"] == "used" else " class=aw"
        trs.append(
            f"<tr{cls}><td>{E(r['name'])}</td><td>{E(r['id'])}</td><td>{rng}</td>"
            f"<td>{_f(r['elev_m'], 0)} / {_f(r['cell_elev_m'], 0)}</td>"
            f"<td>{_f(r.get('obs_pct'), 0)}</td><td>{_f(mp[1], 0) if mp else '–'}</td>"
            f"<td>{_f(mp[t], 0) if mp else '–'}</td><td>{_f(b, 0, True)}</td>"
            f"<td>{E(r['status'])}{': ' + E(r['reason']) if r['reason'] else ''}</td>"
            f"<td>{E(', '.join(r['flags']))}</td></tr>"
        )
    return f"<div class=wrap><table class=st>{head}{''.join(trs)}</table></div>"


def _threshold_table(ov: dict, rb: dict, thresholds: list[int], focus: int) -> str:
    trs = []
    for t in thresholds:
        ci = ov.get("bias_ci", {}).get(t)
        rci = rb.get("bias_ci", {}).get(t) if rb else None
        trs.append(
            f"<tr{' class=best' if t == focus else ''}><td>≥ {t} cm</td>"
            f"<td>{_f(ov['bias_pp'][t], 1, True)} {_ci(ci)}</td><td>{_f(ov['mae_pp'][t])}</td>"
            f"<td>{_f(rb['bias_pp'][t], 1, True) if rb else '–'} {_ci(rci)}</td></tr>"
        )
    return (
        "<div class=wrap><table><tr><th>ERA5-Land threshold</th>"
        "<th>mean bias, every station counts once (pp) [95 % CI]</th><th>MAE (pp)</th>"
        "<th>mean bias, every region counts once (pp) [95 % CI]</th></tr>"
        f"{''.join(trs)}</table></div>"
    )


def _funnel(res: dict) -> str:
    sel = res["selection"]
    rows = res["stations"]
    by: dict[str, int] = {}
    for r in rows:
        key = f"{r['status']}: {r['reason'] or 'calibration'}"
        key = key.split(" (")[0] if key.startswith("excluded: patchy") else key
        if key.startswith("excluded: only"):
            key = "excluded: fewer than the minimum usable years"
        if key.startswith("separated: cell"):
            key = "separated: cell elevation differs from the station by more than 200 m"
        by[key] = by.get(key, 0) + 1
    lines = "".join(f"<tr><td>{E(k)}</td><td>{v:,}</td></tr>" for k, v in sorted(by.items()))
    return f"""<div class=wrap><table>
<tr><td>Northern-Hemisphere stations with snow depth in the GHCN-Daily inventory</td><td>{sel["inventory_snwd_stations"]:,}</td></tr>
<tr><td>… with a snow-depth record spanning ≥ {res["rules"]["min_years"]} years inside {res["years"][0]}–{res["years"][1]}</td><td>{sel["with_min_span"]:,}</td></tr>
<tr><td>… and an ERA5-Land land cell within 2 cells (candidates)</td><td>{sel["candidates_with_land_cell"]:,}</td></tr>
<tr><td>{sel["box_deg"]:g}° × {sel["box_deg"]:g}° boxes holding candidates</td><td>{sel["boxes"]:,}</td></tr>
<tr><td>stations downloaded and examined (up to {sel["max_tries"]} per box)</td><td>{len(rows):,}</td></tr>
{lines}
<tr><td>boxes with no station passing the data-quality rules</td><td>{sel["boxes_without_usable_station"]:,}</td></tr>
</table></div>"""


CSS = """
:root{--bg:#fcfcfb;--fg:#0b0b0b;--mut:#52514e;--line:#dcdbd5;--acc:#2a78d6;--aw:#f3f2ee;
--land:#e9e8e3;--b3:#184f95;--b2:#3987e5;--b1:#9ec5f4;--n0:#c9c8c2;--r1:#f4b6a5;--r2:#e0583c;
--r3:#a3261b;--ring:#fcfcfb}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#1a1a19;--fg:#f0efec;
--mut:#c3c2b7;--line:#3a3a37;--acc:#6da7ec;--aw:#232321;--land:#2b2b29;--b3:#86b6ef;--b2:#3987e5;
--b1:#1c5cab;--n0:#5d5c57;--r1:#8f3524;--r2:#e0583c;--r3:#f4b6a5;--ring:#1a1a19}}
:root[data-theme="dark"]{--bg:#1a1a19;--fg:#f0efec;--mut:#c3c2b7;--line:#3a3a37;--acc:#6da7ec;
--aw:#232321;--land:#2b2b29;--b3:#86b6ef;--b2:#3987e5;--b1:#1c5cab;--n0:#5d5c57;--r1:#8f3524;
--r2:#e0583c;--r3:#f4b6a5;--ring:#1a1a19}
body{background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,sans-serif;margin:0 auto;
max-width:1120px;padding:24px 16px}
h1{font-size:1.6em;margin:.2em 0}h2{margin-top:2em;border-bottom:1px solid var(--line)}
h3{margin-top:1.4em}.mut,.ci{color:var(--mut)}.ci{font-size:.92em}
.box{border-left:4px solid var(--acc);padding:8px 14px;margin:14px 0}
.box li{margin:.25em 0}.wrap{overflow-x:auto}
table{border-collapse:collapse;margin:10px 0;font-size:13px}
td,th{border:1px solid var(--line);padding:3px 7px;text-align:right;white-space:nowrap}
td:first-child,th:first-child{text-align:left}th{font-weight:600}
tr.aw td,tr.few td{color:var(--mut)}tr.aw td{background:var(--aw)}tr.best td{font-weight:700}
table.st td:nth-child(9){white-space:normal;min-width:16em;text-align:left}
svg{width:100%;height:auto;display:block}.land{fill:var(--land);stroke:var(--bg);stroke-width:.6}
.dots circle{stroke:var(--ring);stroke-width:1}.grid{stroke:var(--line);stroke-width:1}
.ref{stroke:var(--mut);stroke-width:1.2;stroke-dasharray:4 3}.tk{fill:var(--mut);font-size:11px}
.ax{fill:var(--fg);font-size:12px}.figs{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:13px;margin:6px 0}
.legend i{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:5px;vertical-align:-1px}
details{margin:6px 0}summary{cursor:pointer}code{font-size:.92em}
"""


def render(res: dict, paths=None) -> str:
    from .stations import STATIC_FINDINGS

    static = STATIC_FINDINGS.replace(
        "<li><b>Elevation</b> differences between station and cell do not explain the bias (r = 0.03).</li>",
        "<li><b>Elevation</b>: on those 25 stations the elevation difference to the cell did not explain the "
        "bias (r = 0.03); the global check above, with far more hill and valley stations, finds that it "
        "does.</li>",
    ).replace("25 of these stations, D-15", "25 stations of the D-17 list, D-15")

    st = res["stats"]
    t = res["focus_cm"]
    thresholds = res["thresholds_cm"]
    rows = res["stations"]
    used = [r for r in rows if r["status"] == "used"]
    if not used:
        return "<!doctype html><title>Station check</title><p>No station passed the rules.</p>"
    ov, rb = st["overall"], st.get("region_balanced", {})
    regions = st["groups"]["region"]
    loro = {x["region"]: x for x in st["loro"]}
    min_n = 8
    tested = {k: v for k, v in regions.items() if v["n"] >= min_n}
    thin = {k: v for k, v in regions.items() if v["n"] < min_n}
    cv = st["cv"]
    sp = ov.get("spread", {})
    el = st.get("elevation", {})
    lats = [r["lat"] for r in used]
    elevs = [r["elev_m"] for r in used if np.isfinite(r["elev_m"])]
    d17 = res.get("d17_list", {})

    fl = st.get("flat", {})
    flo, flrb, flreg = fl.get("overall", {}), fl.get("region_balanced", {}), fl.get("regions", {})
    wr = st.get("elevation_within_region", {})

    def flat_txt(k: str) -> str:
        v = flreg.get(k)
        if not v or v["n"] < min_n:
            return f"; at their cell's elevation: {v['n'] if v else 0} stations, too few"
        return (f"; the {v['n']} at their cell's elevation: {verdict(v, t)} "
                f"{_ci(v.get('bias_ci', {}).get(t))}, T* {_tstar(v['t_star_cm'])} cm")  # fmt: skip

    verdicts = "".join(
        f"<li><b>{E(k)}</b>: all {v['n']} stations {verdict(v, t)} "
        f"{_ci(v.get('bias_ci', {}).get(t))}, T* {_tstar(v['t_star_cm'])} cm "
        f"{_ci(v.get('t_star_ci'))}{flat_txt(k)}</li>"
        for k, v in sorted(tested.items(), key=lambda kv: kv[1]["bias_pp"][t])
    )
    sens = "".join(
        f"<tr><td>{E(x['variant'])}</td><td>{x['n']}</td>"
        + (
            f"<td>{_f(x['bias_pp'][t], 1, True)} {_ci(x['bias_ci'].get(t))}</td>"
            f"<td>{_f(x['region_balanced_bias_pp'].get(t), 1, True)}</td>"
            f"<td>{x['best_whole_cm']} cm</td><td>{_tstar(x['t_star_cm'])} {_ci(x['t_star_ci'])}</td>"
            if "bias_pp" in x
            else "<td colspan=4>too few stations</td>"
        )
        + "</tr>"
        for x in st.get("sensitivity", [])
    )
    thin_txt = ", ".join(f"{E(k)} ({v['n']})" for k, v in sorted(thin.items())) or "none"
    hm = st.get("high_mountain", {})
    any3 = st.get("any3", {})

    by_region_tables = "".join(
        f"<details><summary>{E(reg)}: {sum(1 for r in rs if r['status'] == 'used')} used of "
        f"{len(rs)} examined</summary>{_station_table(rs, t)}</details>"
        for reg, rs in sorted(ss.group_by(rows, lambda r: r["region"]).items())
    )
    dims = [("latitude", "Latitude"), ("elevation", "Station elevation"),
            ("climate", "December mean temperature at the station (climate proxy)"),
            ("snowiness", "How often the station is white"), ("record", "Record length"),
            ("units", "Reporting units")]  # fmt: skip
    other_groups = "".join(
        f"<h3>{E(lab)}</h3>{_group_table(st['groups'][dim], t, None, min_n)}" for dim, lab in dims
    )
    elev_bins = "".join(
        f"<tr><td>{E(b['bin'])}</td><td>{b['n']}</td><td>{b['bias_pp']:+.1f}</td>"
        f"<td>{b['mae_pp']:.1f}</td></tr>"
        for b in el.get("bins", [])
    )

    def cvrow(name, k):
        s = cv[k]
        return (f"<tr><td>{name}</td><td>{s['mean_bias_pp']:+.1f}</td><td>{s['mae_pp']:.1f}</td>"
                f"<td>{s['rmse_pp']:.1f}</td><td>{_f(s['region_mean_abs_bias_pp'])}</td></tr>")  # fmt: skip

    sel = res["selection"]
    snap = ", ".join(f"{k} {v}" for k, v in sel.get("snapshot", {}).items())
    d17s = d17.get("summary") or {}
    d17_out = [x for x in d17.get("rows", []) if x["status"] != "used"]
    d17_txt = "".join(
        f"<li>{E(x['name'])}: {E(x['status'])}, {E(x['reason'])}</li>" for x in d17_out
    )
    cnt = ov["contingency"]
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Snow threshold check</title>
<style>{CSS}</style></head><body>
<h1>Does ERA5-Land's 5 cm match weather stations worldwide?</h1>
<p class=mut>Built {E(res["built"])} by <code>whitexmas stations</code> (automatic selection).
GHCN-Daily metadata snapshot: {E(snap)}. Threshold in use: {res["threshold_cm_in_use"]} cm.
Station-year: 25 December; observed white = snow depth ≥ 1 cm.</p>

<div class=box><b>Summary.</b>
<ul>
<li><b>{len(used):,} stations</b> pass every rule and are used ({ov["station_years"]:,}
station-years), out of {len(rows):,} examined in {sel["boxes"]:,} one-degree boxes. They lie between
{min(lats):.0f}° and {max(lats):.0f}° N and from {min(elevs):,.0f} to {max(elevs):,.0f} m.</li>
<li>At the shipped <b>{t} cm</b>, ERA5-Land is white on 25 December
<b>{ov["bias_pp"][t]:+.1f} pp</b> {_ci(ov["bias_ci"][t])} more often than the stations
(every station counts once; MAE {ov["mae_pp"][t]:.1f} pp). With every region counting once:
<b>{_f(rb.get("bias_pp", {}).get(t), 1, True)} pp</b> {_ci(rb.get("bias_ci", {}).get(t))}.
At the raw 1 cm: {ov["bias_pp"][1]:+.1f} pp.</li>
<li>The whole-cm threshold with the smallest mean bias is <b>{ov["best_whole_cm"]} cm</b>
(every station once) and <b>{rb.get("best_whole_cm", "–")} cm</b> (every region once); the bias
crosses zero at {_tstar(ov["t_star_cm"])} cm {_ci(ov.get("t_star_ci"))} and
{_tstar(rb.get("t_star_cm", NAN))} cm {_ci(rb.get("t_star_ci"))} respectively.</li>
<li><b>Most of that excess comes from stations lying below their cell.</b> For the
{flo.get("n", 0)} stations within 50 m of their ERA5-Land cell's mean elevation, the bias at {t} cm
is <b>{_f(flo.get("bias_pp", {}).get(t), 1, True)} pp</b> {_ci(flo.get("bias_ci", {}).get(t))}
(every region once: {_f(flrb.get("bias_pp", {}).get(t), 1, True)} pp
{_ci(flrb.get("bias_ci", {}).get(t))}), crossing zero at {_tstar(flo.get("t_star_cm", NAN))} cm
{_ci(flo.get("t_star_ci"))}. Within a region, the bias rises by
{_f(wr.get("slope_pp_per_100m"), 1, True)} pp {_ci(wr.get("slope_ci"))} for every 100 m the cell
lies above the station: a town in a valley gets the snowier climate of the hills around it.</li>
<li>Station-years at {t} cm: hit rate {cnt["hit_rate"]:.0%}, false-alarm ratio
{cnt["false_alarm_ratio"]:.0%}, agreement {cnt["accuracy"]:.0%}, Heidke skill
{cnt["heidke"]:.2f}.</li>
<li>Per station the bias scatters (MAE {sp.get("mae_pp", NAN):.1f} pp); sampling noise alone
would give about {sp.get("mae_noise_only_pp", NAN):.1f} pp, so most of the scatter is real: the
station-to-station spread is about ±{sp.get("tau_pp", NAN):.0f} pp (1 s.d.).</li>
<li>Out of sample (leave one 10° block out), one global whole-cm threshold gives MAE
{cv["global"]["mae_pp"]:.1f} pp and leaves regional mean biases of
{cv["global"]["region_mean_abs_bias_pp"]:.1f} pp on average; a threshold per region gives
{cv["regional"]["mae_pp"]:.1f} pp and {cv["regional"]["region_mean_abs_bias_pp"]:.1f} pp; the
fixed {t} cm gives {cv["fixed"]["mae_pp"]:.1f} pp and {
        cv["fixed"]["region_mean_abs_bias_pp"]:.1f} pp.</li>
</ul>
<b>By region</b> (bias at {t} cm with 95 % spatial block-bootstrap interval; "consistent" = the
interval includes 0; T* = where the mean bias crosses zero):<ul>{verdicts}</ul>
<b>Untested or barely tested</b> (fewer than {min_n} usable stations): {thin_txt}. Almost all
GHCN-Daily snow depth from Russia, Central Asia, China, Japan, Korea, Turkey, Eastern Europe and
the Alps comes from weather reports that leave snow-free days blank, so those stations fail the
completeness rule (see the table of reasons). The Southern Hemisphere is out of scope: 25 December
is midsummer there.</div>

<h2>How the stations were chosen</h2>
<p>Every Northern-Hemisphere GHCN-Daily station that reports snow depth is a candidate. In each
{sel["box_deg"]:g}° × {sel["box_deg"]:g}° box the station with the longest snow-depth record is
downloaded first (ties: first-order/WMO before co-operative networks, then the smaller elevation
difference to its ERA5-Land cell); if it fails a data-quality rule, the next one is tried. One
station per box keeps dense networks (the United States, Canada, Sweden, Germany) from swamping
the rest, and the "every region counts once" figures go further.</p>
{_funnel(res)}
<p><b>Rules.</b> Quality-flagged values are dropped. A year counts only if the station reported snow
depth on at least {res["rules"]["min_dec_completeness"]:.0%} of the December days on which it
reported precipitation or temperature: stations that report snow depth only when snow lies leave
the snow-free days blank, so their green Christmases would be lost and they would look "always
white". A station needs ≥ {res["rules"]["min_years"]} usable years covering ≥
{res["rules"]["min_coverage"]:.0%} of its span. Stations white in ≥
{res["rules"]["always_white_pct"]:g} % of years (every threshold agrees), stations where both the
station and ERA5-Land at 1 cm are white in &lt; {res["rules"]["never_white_pct"]:g} % (no
information), and stations more than {res["rules"]["max_elev_diff_m"]:g} m above or below their
cell's mean elevation are kept in the tables but left out of the statistics. Coastal stations whose
cell is water use the nearest land cell within 2 cells. US stations report whole inches, so their
rule is "≥ 1 inch", about 1.3 cm. Stations at or above {res["rules"]["high_mountain_m"]:g} m (or
under such a cell) are flagged, not dropped.</p>

<h2>Which threshold matches?</h2>
{_threshold_table(ov, rb, thresholds, t)}

<h3>Stations at their cell's elevation (within 50 m)</h3>
{_threshold_table(flo, flrb, thresholds, t) if flo else "<p>Too few stations.</p>"}
{_group_table(flreg, t, None, min_n) if flreg else ""}

<h3>Sensitivity to the rules</h3>
<p>One station per box throughout. A relaxed rule re-examines the stations already downloaded.</p>
<div class=wrap><table><tr><th>variant</th><th>stations</th><th>bias ≥ {t} cm [95 % CI]</th>
<th>every region once</th><th>best whole cm</th><th>T* [95 % CI]</th></tr>{sens}</table></div>

<h2>By region</h2>
<p>Greyed rows have fewer than {min_n} stations; their numbers are shown but not interpreted.
Hit rate = share of observed white Christmases that ERA5-Land also calls white; false-alarm ratio
= share of ERA5-Land's white Christmases that the station saw green; Heidke = skill against chance
(1 perfect, 0 no skill). T* = the threshold at which the regional mean bias crosses zero
(interpolated between whole centimetres). Last column: the whole-cm threshold chosen from all
other regions, and the bias it leaves in this one (leave one region out).</p>
{_group_table(regions, t, loro, min_n)}
<h3>Map: bias at {t} cm</h3>{_legend()}{_map(used, t, paths)}
<p class=mut>Hover a dot for the station. Map: Natural Earth.</p>
<div class=figs><div>{
        _scatter(
            used,
            lambda r: r["obs_pct"],
            lambda r: r["model_pct"][t],
            "station: white Christmases (%)",
            f"ERA5-Land ≥ {t} cm (%)",
            (0, 100),
            (0, 100),
            True,
            t,
        )
    }</div>
<div>{
        _scatter(
            used,
            lambda r: r["obs_pct"],
            lambda r: ss.bias(r, t),
            "station: white Christmases (%)",
            f"bias at {t} cm (pp)",
            (0, 100),
            (-60, 60),
            False,
            t,
            True,
        )
    }</div></div>

<h2>Is one global threshold justified?</h2>
<p>Each 10° × 10° block of stations is held out in turn ({cv["n_blocks"]} blocks); the threshold
is chosen on the others and scored on the held-out stations. "Per region" chooses a threshold
from the other stations of the same region (the global choice where fewer than {min_n} remain).
Whole centimetres only, as the pipeline stores whole cm.</p>
<div class=wrap><table><tr><th>threshold rule (out of sample)</th><th>mean bias (pp)</th>
<th>MAE (pp)</th><th>RMSE (pp)</th><th>mean |regional bias| (pp)</th></tr>
{cvrow(f"fixed {t} cm (shipped)", "fixed")}{cvrow("one global threshold", "global")}
{cvrow("one threshold per region", "regional")}</table></div>
<p>Global threshold chosen across the folds: {
        ", ".join(f"{k} cm × {v}" for k, v in cv["global_threshold_counts"].items())
    }.</p>
<p><b>How much of the per-station error is noise?</b> A station's own frequency over n years has
sampling error: at {t} cm the root-mean-square standard error of the station biases is
{sp.get("rms_se_pp", NAN):.1f} pp, against an observed spread (s.d.) of
{sp.get("sd_bias_pp", NAN):.1f} pp, leaving a real between-station spread of about
{sp.get("tau_pp", NAN):.1f} pp. {ov.get("n_significant_bias", 0)} of {ov["n"]} stations
({ov.get("n_significant_bias", 0) / ov["n"]:.0%}) have a bias at {t} cm that is significant on
its own (exact McNemar test, p &lt; 0.05; about 5 % would be by chance alone).</p>

<h2>Elevation</h2>
<p>Bias at {t} cm against the elevation of the ERA5-Land cell minus the station, over
{el.get("n", 0)} stations that pass the data-quality rules (including those separated for a
mismatch): {_f(el.get("slope_pp_per_100m"), 2, True)} pp per 100 m {_ci(el.get("slope_ci"), 2)},
r = {_f(el.get("r"), 2)}. Within regions, over the stations used:
{_f(wr.get("slope_pp_per_100m"), 1, True)} pp per 100 m {_ci(wr.get("slope_ci"))}. A cell higher
than its station is colder and snowier than the station's site, so a positive slope is expected;
its size is the surprise: even inside the ±{res["rules"]["max_elev_diff_m"]:g} m tolerance it
moves the bias by about as much as one centimetre of threshold.</p>
<div class=wrap><table><tr><th>cell − station (m)</th><th>stations</th><th>mean bias (pp)</th>
<th>MAE (pp)</th></tr>{elev_bins}</table></div>
<p>High-mountain stations (station or cell ≥ {res["rules"]["high_mountain_m"]:g} m) used in the
statistics: {hm.get("n", 0)}, mean bias at {t} cm {_f(hm.get("bias_pp", {}).get(t), 1, True)} pp
{_ci(hm.get("bias_ci", {}).get(t))}.</p>
<div class=figs><div>{
        _scatter(
            [r for r in used if np.isfinite(r["elev_diff_m"])],
            lambda r: r["elev_diff_m"],
            lambda r: ss.bias(r, t),
            "cell − station elevation (m)",
            f"bias at {t} cm (pp)",
            (-200, 200),
            (-60, 60),
            False,
            t,
            True,
        )
    }</div></div>

<h2>Other groupings</h2>{other_groups}

<h2>24–26 December, "any of the three days"</h2>
<p>Over {any3.get("n", 0)} stations with all three days in ≥ 10 years: observed
{_f(any3.get("obs_pct"), 0)} %; ERA5-Land bias {_f(any3.get("bias_pp", {}).get(1), 1, True)} pp
at 1 cm and {_f(any3.get("bias_pp", {}).get(t), 1, True)} pp at {t} cm (MAE
{_f(any3.get("mae_pp", {}).get(t))} pp). Context only: the default definition is 25 December.</p>

<h2>The earlier hand-picked list under these rules</h2>
<p>Of the {d17.get("n", 0)} D-17 stations, {d17.get("n_used", 0)} pass the new rules; their mean
bias at {t} cm is {_f(d17s.get("bias_pp", {}).get(t), 1, True)} pp (MAE
{_f(d17s.get("mae_pp", {}).get(t))} pp). Not used now:</p><ul>{d17_txt}</ul>

<h2>Stations</h2>
<p>Every examined station, by region. Greyed: not in the statistics (reason given). Elevation:
station / ERA5-Land cell mean. Also in <code>stations_global.csv</code>.</p>
{by_region_tables}
{static}
</body></html>"""
