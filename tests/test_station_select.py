"""Auto station selection and quality rules on small synthetic GHCN-Daily files (no network)."""

import gzip
import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from whitexmas import ghcn
from whitexmas import station_select as sel
from whitexmas import station_stats as ss

RULES = sel.Rules(min_years=15, thresholds_cm=(1, 2, 3, 4, 5, 6, 7, 8))
YEARS = list(range(1950, 2026))


def write_station(
    path: Path,
    sid: str,
    dec25: dict[int, int],
    omit_zeros: bool = False,
    other_dec_snwd: int = 0,
    tmax: float = 2.0,
    extra: list[str] | None = None,
) -> Path:
    """A station reporting PRCP/TMAX/TMIN every December day, SNWD on 25 Dec = dec25[year].

    Other December days carry SNWD ``other_dec_snwd``. With ``omit_zeros`` every SNWD value of 0
    is left out (as GSOD-derived records do).
    """
    lines = []
    for y, v25 in dec25.items():
        for d in range(1, 32):
            ds = f"{y}12{d:02d}"
            for el, val in (("PRCP", 0), ("TMAX", int(tmax * 10)), ("TMIN", int(tmax * 10) - 60)):
                lines.append(f"{sid},{ds},{el},{val},,,E,")
            v = v25 if d in (24, 25, 26) else other_dec_snwd
            if not (omit_zeros and v == 0):
                lines.append(f"{sid},{ds},SNWD,{v},,,E,")
        day = date(y, 7, 1)
        while day.month == 7:  # July temperatures for the continentality proxy
            ds = day.strftime("%Y%m%d")
            lines.append(f"{sid},{ds},TMAX,250,,,E,")
            lines.append(f"{sid},{ds},TMIN,150,,,E,")
            day += timedelta(days=1)
    lines += extra or []
    with gzip.open(path, "wt") as f:
        f.write("\n".join(lines) + "\n")
    return path


def meta(sid="XX000000001", lat=50.0, lon=10.0, elev=300.0, name="Test"):
    return ghcn.StationMeta(id=sid, name=name, lat=lat, lon=lon, elev=elev)


def model_from(white_years: set[int], depth=10) -> np.ndarray:
    m = np.zeros((len(YEARS), 3), dtype=np.int16)
    for k, y in enumerate(YEARS):
        if y in white_years:
            m[k] = depth
    return m


def evaluate(path, m=None, model=None, cell_elev=300.0, offset=(0, 0)):
    rec = ghcn.read_station(path)
    return sel.evaluate_station(
        m or meta(), rec, model if model is not None else model_from(set()), YEARS, (400, 1900),
        offset, cell_elev, RULES,
    )  # fmt: skip


# --------------------------------------------------------------------------- reading
def test_read_station_completeness_qflag_and_temperatures(tmp_path):
    extra = [
        "XX000000001,19601225,SNWD,999,,G,E,",  # quality-flagged duplicate: dropped
        "XX000000001,19610115,SNWD,50,,,E,",  # January: not part of the December record
    ]
    obs = {1960: 30, 1961: 0, 1962: 0, 1963: 0, 1964: 0, 1965: 0}  # 6 Decembers: >= 150 days
    p = write_station(tmp_path / "a.csv.gz", "XX000000001", obs, extra=extra)
    r = ghcn.read_station(p)
    assert r.snwd[1960] == {24: 30, 25: 30, 26: 30}
    assert r.snwd[1961][25] == 0
    assert r.qflag_dropped == 1
    assert r.dec_completeness(1960) == 1.0
    assert r.dec_zero_share == pytest.approx(1 - 3 / (6 * 31))  # 3 non-zero days
    assert r.tmean[12] == pytest.approx(-1.0)  # (2 + -4) / 2
    assert r.tmean[7] == pytest.approx(20.0)


def test_read_station_without_zeros_is_incomplete(tmp_path):
    p = write_station(tmp_path / "b.csv.gz", "XX000000002", {1970: 0, 1971: 40}, omit_zeros=True)
    r = ghcn.read_station(p)
    assert 1970 not in r.snwd  # no SNWD on 25 Dec at all
    assert r.dec_completeness(1970) == 0.0
    assert r.dec_completeness(1971) == pytest.approx(3 / 31)  # only the three snowy days


def test_read_station_ignores_other_years(tmp_path):
    p = write_station(tmp_path / "c.csv.gz", "XX000000003", {1940: 10, 1960: 10})
    assert set(ghcn.read_station(p, 1950, 2025).snwd) == {1960}


# --------------------------------------------------------------------------- rules
def white_every(k: int) -> dict[int, int]:
    """Observed white (30 mm) in every k-th year, else 0."""
    return {y: (30 if y % k == 0 else 0) for y in YEARS}


def test_good_station_is_used_with_correct_frequencies(tmp_path):
    obs = white_every(3)
    p = write_station(tmp_path / "g.csv.gz", "XX000000004", obs)
    white = {y for y, v in obs.items() if v}
    row = evaluate(p, model=model_from(white | {1951}, depth=6))
    assert row["status"] == "used", row["reason"]
    assert row["years"] == 76 and row["coverage"] == 1.0
    assert row["obs_pct"] == pytest.approx(100 * len(white) / 76)
    assert row["model_pct"][6] == pytest.approx(100 * (len(white) + 1) / 76)
    assert row["model_pct"][7] == 0.0
    h, mi, fa, cn = row["table"][6]
    assert (h, mi, fa) == (len(white), 0, 1) and h + mi + fa + cn == 76
    assert row["any3_obs_pct"] == row["obs_pct"]
    assert row["climate"] == "−5 to 0 °C"


def test_station_omitting_zeros_is_excluded_not_always_white(tmp_path):
    obs = white_every(3)
    p = write_station(tmp_path / "z.csv.gz", "XX000000005", obs, omit_zeros=True)
    row = evaluate(p)
    # Only white years have a 25 December value, and their Decembers are incomplete.
    assert row["status"] == "excluded"
    assert row["reason"].startswith("zeros not reported")


def test_station_omitting_zeros_in_snowy_decembers_still_caught(tmp_path):
    # White Decembers fully reported (snow every day), green ones blank: the complete years look
    # "always white"; the incomplete green years give it away.
    obs = white_every(2)
    p = write_station(tmp_path / "z2.csv.gz", "XX000000006", obs, omit_zeros=True)
    lines = gzip.open(p, "rt").read().splitlines()
    # make the white Decembers snowy on every day
    fixed = [
        ln.replace(",SNWD,0,", ",SNWD,30,") if ln.split(",")[1][:4] in
        {str(y) for y, v in obs.items() if v} else ln
        for ln in lines
    ]  # fmt: skip
    for y, v in obs.items():
        if v:
            fixed += [f"XX000000006,{y}12{d:02d},SNWD,30,,,E," for d in range(1, 32)
                      if d not in (24, 25, 26)]  # fmt: skip
    with gzip.open(p, "wt") as f:
        f.write("\n".join(fixed) + "\n")
    row = evaluate(p)
    assert row["years"] == 38 and row["obs_pct"] == 100.0
    assert row["status"] == "excluded"  # not "separated: always white"


def test_patchy_and_short_records(tmp_path):
    obs = {y: 0 for y in range(1950, 2026, 2)}  # every other year: coverage 50 %
    row = evaluate(write_station(tmp_path / "p.csv.gz", "XX000000007", obs))
    assert row["status"] == "excluded" and row["reason"].startswith("patchy")
    short = {y: 30 * (y % 2) for y in range(2010, 2020)}
    row = evaluate(write_station(tmp_path / "s.csv.gz", "XX000000008", short))
    assert row["reason"] == "only 10 usable years"


def test_always_never_white_and_elevation_are_separated(tmp_path):
    allw = {y: 50 for y in YEARS}
    p = write_station(tmp_path / "w.csv.gz", "XX000000009", allw, other_dec_snwd=50)
    assert evaluate(p)["reason"] == "always white"
    green = {y: 0 for y in YEARS}
    p = write_station(tmp_path / "n.csv.gz", "XX000000010", green)
    assert evaluate(p)["reason"] == "almost never white"
    # ...but not when ERA5-Land is often white there: that is a real (and informative) bias
    assert evaluate(p, model=model_from(set(YEARS[::2])))["status"] == "used"
    p = write_station(tmp_path / "e.csv.gz", "XX000000011", white_every(3))
    row = evaluate(p, cell_elev=900.0)
    assert row["status"] == "separated" and row["reason"] == "cell +600 m vs station"
    assert "elev_mismatch" in row["flags"]


def test_flags_us_coastal_high_mountain(tmp_path):
    p = write_station(tmp_path / "u.csv.gz", "USC00000001", white_every(3))
    row = evaluate(p, m=meta("USC00000001", elev=1600.0), cell_elev=1650.0, offset=(1, -1))
    assert set(row["flags"]) == {"us_inches", "coastal", "high_mountain"}
    assert row["status"] == "used"


def test_us_whole_inch_values_use_the_same_mm_threshold(tmp_path):
    # GHCN stores US inches as mm: 1 inch = 25 mm counts as white, a trace (0) does not.
    obs = {y: (25 if y % 4 == 0 else 0) for y in YEARS}
    row = evaluate(write_station(tmp_path / "i.csv.gz", "USC00000002", obs))
    assert row["obs_pct"] == pytest.approx(100 * 19 / 76)


# --------------------------------------------------------------------------- selection
def test_candidate_boxes_rank_and_filters():
    stations = {
        "USW00000001": meta("USW00000001", 45.2, -93.3),
        "USC00000002": meta("USC00000002", 45.7, -93.9),  # same box, co-operative
        "USC00000003": meta("USC00000003", 45.5, -93.5),  # longer record
        "XX000000004": meta("XX000000004", -30.0, 20.0),  # Southern Hemisphere
        "XX000000005": meta("XX000000005", 60.0, 10.0),  # too short
        "XX000000006": meta("XX000000006", 61.0, 11.0),  # no land cell
    }
    inv = {
        "USW00000001": (1950, 2025), "USC00000002": (1950, 2025), "USC00000003": (1900, 2030),
        "XX000000004": (1950, 2025), "XX000000005": (2015, 2025), "XX000000006": (1950, 2025),
    }  # fmt: skip

    def cell_of(m):
        return None if m.id == "XX000000006" else ((0, 0), m.elev)

    boxes = sel.candidate_boxes(stations, inv, 1950, 2025, RULES, sel.AutoSettings(), cell_of)
    assert boxes == {(45, -94): ["USW00000001", "USC00000002", "USC00000003"]}
    # spans inside 1950-2025 are equal (76 years), so the network decides; then elevation, id.
    boxes2 = sel.candidate_boxes(
        stations, {**inv, "USC00000003": (1950, 2025), "USW00000001": (1960, 2025)}, 1950, 2025,
        RULES, sel.AutoSettings(), cell_of,
    )  # fmt: skip
    assert boxes2[(45, -94)][0] == "USC00000002"
    assert sel.candidate_boxes(stations, inv, 1950, 2025, RULES, sel.AutoSettings(box_deg=2.0),
                               cell_of).keys() == {(22, -47)}  # fmt: skip


def test_regions():
    assert sel.region_of(47.0, 11.4, 1500, "AU") == "Alps"
    assert sel.region_of(48.1, 11.6, 520, "GM") == "Western & Central Europe"
    assert sel.region_of(39.7, -105.0, 1650, "US") == "Rocky Mountains & Intermountain West"
    assert sel.region_of(41.9, -87.9, 200, "US") == "Eastern North America"
    assert sel.region_of(44.9, -93.2, 260, "US") == "Eastern North America"
    assert sel.region_of(46.8, -100.8, 500, "US") == "Great Plains & Prairies"
    assert sel.region_of(47.4, -122.3, 100, "US") == "Pacific North America"
    assert sel.region_of(64.8, -147.7, 150, "US") == "Alaska & northern Canada"
    assert sel.region_of(55.8, 37.6, 150, "RS") == "European Russia"
    assert sel.region_of(62.0, 129.7, 100, "RS") == "Siberia & Russian Far East"
    assert sel.region_of(29.7, 91.1, 4000, "CH") == "Tibetan Plateau"
    assert sel.region_of(43.1, 141.3, 20, "JA") == "Japan"
    assert sel.region_of(59.9, 10.7, 90, "NO") == "Nordic countries"
    assert sel.region_of(78.2, 15.6, 30, "SV") == "Arctic islands"
    assert sel.region_of(18.4, -66.0, 10, "RQ") == "Other (subtropics)"


def test_select_and_examine_falls_back_within_a_box(tmp_path, monkeypatch, cfg):
    """End to end without network: the first station of the box omits zeros, the second is used."""
    from whitexmas import station_global as sg
    from whitexmas.paths import DataPaths

    gdir = tmp_path / "external" / "ghcn"
    gdir.mkdir(parents=True)
    st = [("XX000000001", 50.2, 10.2, 300.0, "Bad"), ("XX000000002", 50.6, 10.7, 310.0, "Good")]
    with open(gdir / "ghcnd-stations.txt", "w") as f:
        for sid, lat, lon, el, name in st:
            f.write(f"{sid} {lat:8.4f} {lon:9.4f} {el:6.1f}    {name:<30}\n")
    with open(gdir / "ghcnd-inventory.txt", "w") as f:
        f.write(f"XX000000001 {50.2:8.4f} {10.2:9.4f} SNWD 1940 2025\n")
        f.write(f"XX000000002 {50.6:8.4f} {10.7:9.4f} SNWD 1950 2025\n")
    (gdir / "ghcnd-countries.txt").write_text("XX Testland\n")
    write_station(gdir / "XX000000001.csv.gz", "XX000000001", white_every(3), omit_zeros=True)
    write_station(gdir / "XX000000002.csv.gz", "XX000000002", white_every(3))
    monkeypatch.setattr(ghcn, "fetch_stations", lambda *a, **k: 0)

    class FakeCube:
        years = YEARS

        def cell_of(self, m):
            return (400, 1900), (0, 0), 300.0

        def column(self, j, i):
            return model_from({y for y in YEARS if y % 3 == 0}, depth=5)

    rows, info = sg.select_and_examine(cfg, DataPaths(tmp_path), FakeCube())
    assert [(r["id"], r["status"]) for r in rows] == [
        ("XX000000001", "excluded"), ("XX000000002", "used"),
    ]  # fmt: skip
    assert rows[1]["rank_in_box"] == 2 and info["boxes"] == 1
    assert info["boxes_without_usable_station"] == 0
    assert rows[1]["model_pct"][5] == pytest.approx(rows[1]["obs_pct"])

    stats = sg.assess(rows, [1, 5], n_boot=50)
    assert stats["n_used"] == 1 and stats["overall"]["bias_pp"][5] == pytest.approx(0.0)
    sg.write_csv(tmp_path / "s.csv", rows, [1, 5], {"XX": "Testland"})
    header = (tmp_path / "s.csv").read_text().splitlines()[0].split(",")
    assert header[:4] == ["id", "name", "lat", "lon"] and "era5_ge_5cm_pct" in header
    web = sg.web_json(rows, {"built": "x"})
    assert web["schema"] == "wx-stations-v1" and len(web["rows"]) == 1  # excluded left out
    rec = dict(zip(web["fields"], web["rows"][0], strict=True))
    assert rec["id"] == "XX000000002" and rec["status"] == "used"
    json.dumps(sg._clean(web))


# --------------------------------------------------------------------------- statistics
def _row(obs, model, lat=50.0, lon=10.0, region="A", n=40):
    """A synthetic used row with a consistent contingency table at every threshold."""
    table = {}
    for t, m in model.items():
        h = round(n * min(obs, m) / 100)
        fa = round(n * m / 100) - h
        mi = round(n * obs / 100) - h
        table[t] = [h, mi, fa, n - h - mi - fa]
    return {"obs_pct": obs, "model_pct": model, "agree_pct": dict.fromkeys(model, 90.0),
            "table": table, "lat": lat, "lon": lon, "region": region, "years": n}  # fmt: skip


def test_t_star_interpolates_and_reports_open_ends():
    assert ss.t_star({1: 20.0, 2: 10.0, 3: -10.0}) == pytest.approx(2.5)
    assert ss.t_star({1: -1.0, 2: -5.0}) == -math.inf
    assert ss.t_star({1: 9.0, 2: 1.0}) == math.inf


def test_best_whole_and_station_se():
    rows = [_row(30, {1: 60, 2: 40, 3: 30}), _row(50, {1: 80, 2: 60, 3: 52})]
    assert ss.best_whole(rows, [1, 2, 3]) == 3
    r = _row(50, {1: 50})  # 20 hits, 20 correct negatives: no discordant years
    assert ss.station_se(r, 1) == 0.0
    r = {"table": {1: [10, 10, 10, 10]}}  # d = +1, -1 in 10 years each of 40
    assert ss.station_se(r, 1) == pytest.approx(100 * math.sqrt(0.5 * 40 / 39 / 40))
    assert ss.mcnemar_p({"table": {1: [10, 0, 10, 20]}}, 1) < 0.01


def test_contingency_scores():
    c = ss.contingency([{"table": {5: [30, 10, 10, 50]}}], 5)
    assert c["hit_rate"] == 0.75 and c["false_alarm_ratio"] == 0.25
    assert c["accuracy"] == 0.8 and 0 < c["heidke"] < 1


def test_bootstrap_and_cv_detect_a_regional_offset():
    T = [1, 2, 3, 4, 5, 6, 7, 8]
    rng = np.random.default_rng(1)
    rows = []
    for k in range(40):  # region A: unbiased at 5 cm; region B: unbiased at 2 cm
        reg, opt = ("A", 5) if k < 20 else ("B", 2)
        lat, lon = (45 + rng.uniform(0, 20), (0 if reg == "A" else 100) + rng.uniform(0, 30))
        model = {t: float(np.clip(30 + 8 * (opt - t), 0, 100)) for t in T}
        rows.append(_row(30, model, lat, lon, reg))
    s = ss.summarize([r for r in rows if r["region"] == "A"], T, n_boot=200)
    assert s["best_whole_cm"] == 5 and s["t_star_cm"] == pytest.approx(5.0)
    lo, hi = s["bias_ci"][5]
    assert lo <= 0 <= hi
    rb = ss.region_balanced(rows, T, min_n=8, n_boot=200)
    assert rb["t_star_cm"] == pytest.approx(3.5)
    cv = ss.blocked_cv(rows, T, min_region_n=8)
    assert cv["regional"]["mae_pp"] < cv["global"]["mae_pp"]
    lo = {x["region"]: x for x in ss.leave_one_region_out(rows, T, 8)}
    assert lo["A"]["t_chosen_without"] == 2 and lo["A"]["bias_at_chosen_pp"] > 0


def test_zero_filled_snow_depth_despite_snowfall_is_excluded(tmp_path):
    """Snow depth reported as 0 every day although the station measured lots of snowfall."""
    obs = {y: 0 for y in YEARS}
    snow = [f"XX000000012,{y}1210,SNOW,300,,,E," for y in YEARS[::2]]  # 30 cm, every other year
    p = write_station(tmp_path / "f.csv.gz", "XX000000012", obs, extra=snow)
    row = evaluate(p, model=model_from(set(YEARS[::3])))
    assert row["snowy_decembers"] == 38 and row["snowfall_without_depth"] == 38
    assert row["status"] == "excluded" and row["reason"].startswith("zero snow depth despite")
    # the same snowfall with snow on the ground afterwards is fine
    p = write_station(tmp_path / "f2.csv.gz", "XX000000013", obs, other_dec_snwd=20, extra=snow)
    row = evaluate(p, model=model_from(set(YEARS[::3])))
    assert row["snowfall_without_depth"] == 0


def test_classify_follows_the_rules_it_is_given(tmp_path):
    """Sensitivity variants re-classify stored rows, so the rules must not be baked into flags."""
    import dataclasses

    p = write_station(tmp_path / "v.csv.gz", "XX000000014", white_every(3))
    row = evaluate(p, cell_elev=900.0)
    assert row["status"] == "separated"
    loose = dataclasses.replace(RULES, max_elev_diff_m=float("inf"))
    assert sel.classify(row, loose) == ("used", "")
