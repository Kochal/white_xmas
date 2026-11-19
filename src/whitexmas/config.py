"""Pipeline configuration loaded from config/pipeline.yaml."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .paths import DEFAULT_CONFIG


@dataclass(frozen=True)
class Window:
    id: str
    label: str
    start: int
    end: int
    kind: str  # full | normal | decade

    @property
    def n_years(self) -> int:
        return self.end - self.start + 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "start": self.start,
            "end": self.end,
            "kind": self.kind,
        }


def _whole_cm(value: Any, name: str) -> int:
    f = float(value)
    if not f.is_integer() or f < 0:
        raise ValueError(f"{name} must be a whole number of centimetres, got {value!r}")
    return int(f)


def make_window(start: int, end: int, kind: str) -> Window:
    return Window(id=f"{start}_{end}", label=f"{start}–{end}", start=start, end=end, kind=kind)


@dataclass
class Config:
    raw: dict[str, Any]

    @classmethod
    def load(cls, path: str | Path | None = None) -> Config:
        p = Path(path) if path else DEFAULT_CONFIG
        with open(p, encoding="utf-8") as f:
            return cls(yaml.safe_load(f))

    # -- basics -------------------------------------------------------------
    @property
    def first_year(self) -> int:
        return int(self.raw["years"]["first"])

    @property
    def last_year(self) -> int:
        return int(self.raw["years"]["last"])

    @property
    def years(self) -> list[int]:
        return list(range(self.first_year, self.last_year + 1))

    @property
    def thresholds(self) -> list[dict[str, Any]]:
        """Snow-depth thresholds (contract v1.5), default first.

        Each: ``id``, ``cm`` (whole cm), ``default``, ``station_equivalent_cm`` (or None),
        ``label``, ``description`` (with ``{cm}``/``{station_equivalent_cm}`` filled in),
        ``layers`` ("full" | "minimal") and ``suffix`` ("" for the default, "__<id>" otherwise).
        Without a ``thresholds`` list, a single default is built from ``threshold_cm``.

        Whole cm only: the cube and point tiles store floored whole cm, so ``cube >= T`` equals
        ``source >= T`` only for whole T; a fractional value would silently act as the next cm.
        """
        raw = self.raw.get("thresholds")
        if not raw:
            raw = [{"id": "default", "cm": self.raw.get("threshold_cm", 1), "default": True,
                    "station_equivalent_cm": self.raw.get("station_equivalent_cm")}]  # fmt: skip
        defaults = [t for t in raw if t.get("default")] or raw[:1]
        if len(defaults) != 1:
            raise ValueError("exactly one threshold must be the default")
        out = []
        for t in sorted(raw, key=lambda t: t is not defaults[0]):
            cm = _whole_cm(t["cm"], f"thresholds[{t['id']}].cm")
            eq = t.get("station_equivalent_cm")
            eq = None if eq is None else _whole_cm(eq, "station_equivalent_cm")
            is_default = t is defaults[0]
            fmt = {"cm": cm, "station_equivalent_cm": eq}
            out.append({
                "id": str(t["id"]), "cm": cm, "default": is_default,
                "station_equivalent_cm": eq,
                "label": str(t.get("label", f"At least {cm} cm")).format(**fmt),
                "description": " ".join(str(t.get("description", "")).split()).format(**fmt),
                "layers": str(t.get("layers", "full")),
                "suffix": "" if is_default else f"__{t['id']}",
            })  # fmt: skip
        return out

    @property
    def default_threshold(self) -> dict[str, Any]:
        return self.thresholds[0]

    @property
    def threshold_cm(self) -> int:
        """The default threshold in whole centimetres (manifest.threshold_cm)."""
        return self.default_threshold["cm"]

    @property
    def station_equivalent_cm(self) -> int | None:
        """Contract v1.4: station depth that the default threshold was calibrated to match."""
        return self.default_threshold["station_equivalent_cm"]

    @property
    def download(self) -> dict[str, Any]:
        return self.raw["download"]

    @property
    def definitions(self) -> list[dict[str, Any]]:
        """Definitions with ``{threshold_cm}`` in their texts filled in from the config."""
        t = self.threshold_cm
        out = []
        for d in self.raw["definitions"]:
            out.append(
                {k: v.format(threshold_cm=t) if isinstance(v, str) else v for k, v in d.items()}
            )
        return out

    @property
    def definition_ids(self) -> list[str]:
        return [d["id"] for d in self.definitions]

    @property
    def default_definition(self) -> str:
        for d in self.definitions:
            if d.get("default"):
                return d["id"]
        return self.definitions[0]["id"]

    @property
    def export(self) -> dict[str, Any]:
        return self.raw.get("export", {})

    @property
    def glacier(self) -> dict[str, Any]:
        return self.raw.get("glacier", {})

    @property
    def trend_p(self) -> float:
        return float(self.raw.get("trend", {}).get("significance_p", 0.1))

    # -- windows ------------------------------------------------------------
    def windows(self) -> list[Window]:
        """Windows in contract order: full, normals, then decades from the latest backwards."""
        w = self.raw["windows"]
        out: list[Window] = []
        if w.get("full", True):
            out.append(make_window(self.first_year, self.last_year, "full"))
        for a, b in w.get("normals", []):
            if a >= self.first_year and b <= self.last_year:
                out.append(make_window(int(a), int(b), "normal"))
        if w.get("decades", True):
            end = self.last_year
            while end - 9 >= self.first_year:
                win = make_window(end - 9, end, "decade")
                if win.id not in {x.id for x in out}:
                    out.append(win)
                end -= 10
        return out

    def window(self, wid: str) -> Window:
        for w in self.windows():
            if w.id == wid:
                return w
        raise KeyError(wid)

    @property
    def change_pair(self) -> tuple[str, str]:
        c = self.raw["windows"].get("change", {})
        # str(): YAML 1.1 reads an unquoted 1961_1990 as the integer 19611990
        a, b = c.get("from", "1961_1990"), c.get("to", "1996_2025")
        if isinstance(a, int):
            a = f"{str(a)[:4]}_{str(a)[4:]}"
        if isinstance(b, int):
            b = f"{str(b)[:4]}_{str(b)[4:]}"
        return str(a), str(b)

    def full_window(self) -> Window:
        return next(w for w in self.windows() if w.kind == "full")

    # -- hashing ------------------------------------------------------------
    def section_hash(self, *keys: str) -> str:
        sub = {k: self.raw.get(k) for k in keys}  # missing keys hash as None
        blob = json.dumps(sub, sort_keys=True, default=str).encode()
        return hashlib.sha256(blob).hexdigest()[:16]
