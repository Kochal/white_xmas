# /// script
# requires-python = ">=3.12"
# dependencies = ["intake-esgf>=2025.1", "pandas", "requests"]
# ///
"""Select CMIP6 models, members and files for the White Christmas projections.

Standalone (Phase 1 of the projections track). Run with::

    uv run scripts/projections/cmip6_select.py

What it does

1. Searches ESGF (STAC index via ``intake-esgf``, plus the DKRZ Solr index for
   extra European replicas) for daily snow amount ``snw`` (table ``day``) in
   ``historical``, ``ssp245`` and ``ssp585``, and for the land fraction ``sftlf``.
2. Reads the per-model warming-level windows of Hauser et al.
   (``mathause/cmip_warming_levels``, 20-year windows relative to 1850-1900).
3. Picks one member per model that has historical + ssp245 daily snw and
   warming-level windows; ssp585 is added when ssp245 does not reach +3 degC.
4. Keeps only files that overlap the years we need, and writes
   ``$WHITEXMAS_DATA/cmip6/plan.json`` (consumed by ``cmip6_download.py``).
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import warnings
from collections import defaultdict
from pathlib import Path

import pandas as pd
import requests

DATA = Path(
    os.environ.get("WHITEXMAS_DATA", r"C:\Users\AlexanderKoch\TransparentEarth\white_xmas_data")
)
OUT = DATA / "cmip6"

HAUSER_COMMIT = "f9aa658a7753546187c66a5431d0ae9cdc8dc7e4"
HAUSER_URL = (
    "https://raw.githubusercontent.com/mathause/cmip_warming_levels/"
    f"{HAUSER_COMMIT}/warming_levels/cmip6_all_ens/csv/cmip6_warming_levels_all_ens_1850_1900.csv"
)
DKRZ_SOLR = "https://esgf-data.dkrz.de/esg-search/search"

GWLS = (1.5, 2.0, 3.0)
HIST_FIRST_YEAR = 1960  # baseline 1995-2014; 1961-1990 for the hindcast check
EXPERIMENTS = ("historical", "ssp245", "ssp585")

# Hosts in order of preference. Hosts that were unreachable from the build
# machine during the spike (2026-11-18) go last; the downloader still tries them.
HOST_ORDER = [
    "esgf3.dkrz.de",
    "esgf-node.ornl.gov",
    "vesg.ipsl.upmc.fr",
    "dpesgf03.nccs.nasa.gov",
    "esgdata.gfdl.noaa.gov",
    "esgf-data2.llnl.gov",
    "aims3.llnl.gov",
]
SLOW_OR_BLOCKED = {"esgf.ceda.ac.uk", "esgf.ichec.ie", "esg1.umr-cnrm.fr", "esgf.dwd.de"}


def host_rank(url: str) -> tuple[int, str]:
    host = url.split("/")[2]
    if host in HOST_ORDER:
        return (HOST_ORDER.index(host), url)
    if "globus.org" in host:
        return (90, url)
    if host in SLOW_OR_BLOCKED:
        return (95, url)
    return (50, url)


def file_years(name: str) -> tuple[int, int] | None:
    m = re.search(r"_(\d{4})\d*-(\d{4})\d*\.nc$", name)
    return (int(m[1]), int(m[2])) if m else None


def load_hauser() -> pd.DataFrame:
    txt = requests.get(HAUSER_URL, timeout=60).text
    df = pd.read_csv(io.StringIO(txt), comment="#", skipinitialspace=True)
    df.columns = [c.strip() for c in df.columns]
    return df


def member_key(m: str) -> tuple[int, ...]:
    """Sort key for variant labels: r1i1p1f1 first, then lowest r, i, p, f."""
    return tuple(int(x) for x in re.findall(r"\d+", m))


def stac_search(**facets) -> pd.DataFrame | None:
    from intake_esgf import ESGFCatalog
    from intake_esgf.exceptions import NoSearchResults

    cat = ESGFCatalog()
    try:
        cat.search(project="CMIP6", latest=True, quiet=True, **facets)
    except NoSearchResults:
        return None
    return cat


def solr_files(**facets) -> list[dict]:
    rows, start = [], 0
    while True:
        p = dict(
            project="CMIP6",
            type="File",
            format="application/solr+json",
            limit=5000,
            offset=start,
            distrib="true",
            latest="true",
            fields="source_id,member_id,experiment_id,variable_id,size,url,data_node,title,checksum,checksum_type,version,grid_label",
        )
        p.update(facets)
        j = requests.get(DKRZ_SOLR, params=p, timeout=900).json()
        docs = j["response"]["docs"]
        rows += docs
        start += len(docs)
        if start >= j["response"]["numFound"] or not docs:
            return rows


def first(x):
    return x[0] if isinstance(x, list) else x


def main() -> int:
    warnings.filterwarnings("ignore")
    OUT.mkdir(parents=True, exist_ok=True)

    print("searching STAC index for snw/day ...", flush=True)
    cat = stac_search(variable_id="snw", table_id="day", experiment_id=list(EXPERIMENTS))
    df = cat.df
    avail = defaultdict(lambda: defaultdict(set))  # model -> exp -> members
    for _, r in df.iterrows():
        avail[r.source_id][r.experiment_id].add(r.member_id)

    hauser = load_hauser()
    wl = defaultdict(dict)  # (model, member) -> {(exp, gwl): (y0, y1)}
    for _, r in hauser.iterrows():
        wl[(r.model, r.ensemble)][(r.exp, float(r.warming_level))] = (
            int(r.start_year),
            int(r.end_year),
        )

    selection = {}
    for model in sorted(avail):
        exps = avail[model]
        common = exps.get("historical", set()) & exps.get("ssp245", set())
        cands = sorted((m for m in common if (model, m) in wl), key=member_key)
        if not cands:
            if common:
                print(
                    f"  skip {model}: no warming-level windows in Hauser et al. "
                    f"for {sorted(common)[:3]}"
                )
            continue
        member = cands[0]
        w = wl[(model, member)]
        windows = {}
        for g in GWLS:
            if ("ssp245", g) in w:
                windows[str(g)] = {
                    "experiment": "ssp245",
                    "start": w[("ssp245", g)][0],
                    "end": w[("ssp245", g)][1],
                }
            elif ("ssp585", g) in w and member in exps.get("ssp585", set()):
                windows[str(g)] = {
                    "experiment": "ssp585",
                    "start": w[("ssp585", g)][0],
                    "end": w[("ssp585", g)][1],
                }
        selection[model] = {
            "member": member,
            "windows": windows,
            "n_members": {e: len(exps.get(e, ())) for e in EXPERIMENTS},
        }
        print(
            f"  {model:18s} {member:10s} "
            + " ".join(
                f"{g}:{v['experiment'][3:]}:{v['start']}-{v['end']}" for g, v in windows.items()
            ),
            flush=True,
        )

    # file info, restricted to the chosen members
    print("collecting file info ...", flush=True)
    files = {}

    def add_files(c, variable: str, table: str) -> None:
        for info in c._get_file_info(quiet=True):
            name = Path(info["path"]).name
            parts = name.split("_")
            ck = info.get("checksum") or ""
            sha = (
                ck[4:]
                if ck.startswith("1220") and len(ck) == 68
                else (ck if len(ck) == 64 else None)
            )
            files[name] = {
                "model": parts[2],
                "member": parts[4],
                "experiment": parts[3],
                "variable": variable,
                "table": table,
                "file": name,
                "size": info.get("size"),
                "sha256": sha,
                "urls": list(info["HTTPServer"]),
                "dataset_id": info["dataset_id"].split("|")[0],
            }

    wanted = {
        (m, s["member"], e)
        for m, s in selection.items()
        for e in {"historical", "ssp245"} | {v["experiment"] for v in s["windows"].values()}
    }
    cat.df = cat.df[
        [(r.source_id, r.member_id, r.experiment_id) in wanted for r in cat.df.itertuples()]
    ].reset_index(drop=True)
    add_files(cat, "snw", "day")

    # land fraction (fx): one dataset per model, historical and the chosen member preferred
    fx = stac_search(variable_id="sftlf", table_id="fx", source_id=sorted(selection))
    if fx is not None:
        d = fx.df.copy()
        # present-day land-sea mask only; paleo experiments (lig127k, ...) have other coastlines
        exp_rank = {
            "historical": 0,
            "piControl": 1,
            "ssp245": 2,
            "ssp585": 3,
            "amip": 4,
            "hist-resIPO": 5,
            "1pctCO2": 6,
            "abrupt-4xCO2": 7,
        }
        d = d[d.experiment_id.isin(exp_rank)]
        d["rank"] = [
            (
                exp_rank[r.experiment_id],
                r.member_id != selection[r.source_id]["member"],
                member_key(r.member_id),
            )
            for r in d.itertuples()
        ]
        fx.df = d.sort_values("rank").groupby("source_id").head(1).drop(columns="rank")
        fx.df = fx.df.reset_index(drop=True)
        add_files(fx, "sftlf", "fx")

    print("adding DKRZ replicas ...", flush=True)
    try:
        for r in solr_files(variable_id="snw", table_id="day"):
            name = first(r["title"])
            if name in files:
                for u in r["url"]:
                    if u.endswith("HTTPServer"):
                        files[name]["urls"].append(u.split("|")[0])
                if (
                    not files[name]["sha256"]
                    and first(r.get("checksum_type", "")).upper() == "SHA256"
                ):
                    files[name]["sha256"] = first(r["checksum"])
    except Exception as e:  # noqa: BLE001 - replicas are optional
        print("  DKRZ replica lookup failed:", e)

    # one grid per model: the ssp245 grid (GFDL-CM4 publishes historical on gr1 and gr2)
    grid_of = {}
    for f in files.values():
        if f["variable"] == "snw" and f["experiment"] == "ssp245":
            grid_of.setdefault(f["model"], f["file"].split("_")[5])
    files = {
        k: f
        for k, f in files.items()
        if f["variable"] != "snw" or f["file"].split("_")[5] == grid_of.get(f["model"])
    }

    # keep only the years we need
    keep = []
    for f in files.values():
        sel = selection[f["model"]]
        f["urls"] = sorted(set(f["urls"]), key=host_rank)
        if f["variable"] == "sftlf":
            keep.append(f)
            continue
        yrs = file_years(f["file"])
        if yrs is None:
            continue
        f["start"], f["end"] = yrs
        if f["experiment"] == "historical":
            lo, hi = HIST_FIRST_YEAR, 2014
        elif f["experiment"] == "ssp245":
            lo, hi = 2015, 2100
        else:  # ssp585: only the windows that use it
            ws = [w for w in sel["windows"].values() if w["experiment"] == "ssp585"]
            if not ws:
                continue
            lo, hi = 2015, max(w["end"] for w in ws)
        if yrs[1] >= lo and yrs[0] <= hi:
            keep.append(f)

    plan = {
        "hauser_commit": HAUSER_COMMIT,
        "hist_first_year": HIST_FIRST_YEAR,
        "models": selection,
        "files": sorted(keep, key=lambda f: (f["model"], f["experiment"], f["file"])),
    }
    (OUT / "plan.json").write_text(json.dumps(plan, indent=1))
    tot = sum(f["size"] or 0 for f in keep) / 1e9
    print(f"wrote {OUT / 'plan.json'}: {len(selection)} models, {len(keep)} files, {tot:.1f} GB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
