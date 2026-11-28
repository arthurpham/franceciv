"""Wallis-et-Futuna census-detail lenses."""

from collections import defaultdict
import unicodedata

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, load_interim_payload, write_web
from .connectivity import shape_weights

REQUIRES = ["_world", "fr_boundaries", "fr_wallis_futuna"]
PRODUCES = ["wallis_futuna.json"]
RAMP = ["#1b1035", "#4b2377", "#9a3b8a", "#e0645e", "#f9b24a", "#fff3a8"]


def norm(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "")).lower() if c.isalnum())


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def lens(lens_id, name, emoji, unit, vals, desc, fmt="pct"):
    return {"id": lens_id, "group": "overseas", "name": name, "icon": lens_id, "emoji": emoji, "unit": unit,
            "format": fmt, "scale": "linear", "domain": [percentile(vals, 2), percentile(vals, 98)], "ramp": RAMP,
            "higher_is": "neutral", "source": "fr_wallis_futuna", "description": desc, "values": vals}


def build():
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    wf = load_interim("fr_wallis_futuna")
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    weights = shape_weights(world, grid, proj, bounds["communes"])
    rows = wf["circonscriptions"]
    keys = ["change_2018_2023", "change_2003_2023", "median_age", "children", "seniors", "employment", "unemployment"]
    acc = defaultdict(lambda: defaultdict(float))
    matched = 0
    for c in bounds["communes"]:
        if c.get("department") != "986":
            continue
        row = rows.get(norm(c["name"]))
        wts = weights.get(c["code"])
        if not row or not wts:
            continue
        matched += 1
        for cell, weight in wts.items():
            acc[cell]["weight"] += weight
            for key in keys:
                if row.get(key) is not None:
                    acc[cell][key] += row[key] * weight
    series = {}
    for key in keys:
        vals = []
        for i in range(grid.size):
            a = acc.get(i)
            vals.append(round(a[key] / a["weight"], 4) if a and a["weight"] else None)
        series[key] = vals
    method = "Wallis-et-Futuna's three circonscriptions are distributed over commune polygons and weighted within hexes. Population-change rates are circonscription-level; age and labour-market indicators are published at island level, so Alo and Sigave share the Futuna value. The rest of France is null because these are territory-specific census tables."
    write_web("wallis_futuna.json", {
        "version": 1, "vintage": load_interim_payload("fr_wallis_futuna")["vintage"], "sources": ["fr_wallis_futuna"], "matched_communes": matched, "methodology": method,
        "group": {"id": "overseas", "name": "Overseas detail"},
        "lenses": [
            lens("wf_population_change_recent", "Wallis-et-Futuna population change 2018–2023", "📉", "population change", series["change_2018_2023"], "Population change between the 2018 and 2023 censuses. " + method),
            lens("wf_population_change_long", "Wallis-et-Futuna population change 2003–2023", "🧭", "population change", series["change_2003_2023"], "Population change between the 2003 and 2023 censuses. " + method),
            lens("wf_median_age", "Wallis-et-Futuna median age", "⏳", "years", series["median_age"], "Median age in 2023. " + method, fmt="number"),
            lens("wf_children", "Wallis-et-Futuna children", "🧒", "share of residents", series["children"], "Residents aged 0–14 as a share of all residents in 2023. " + method),
            lens("wf_seniors", "Wallis-et-Futuna residents 65+", "👵", "share of residents", series["seniors"], "Residents aged 65 or older as a share of all residents in 2023. " + method),
            lens("wf_employment", "Wallis-et-Futuna employment rate", "💼", "employment rate", series["employment"], "Census employment rate in 2023. " + method),
            lens("wf_unemployment", "Wallis-et-Futuna unemployment", "🧭", "share of labour force", series["unemployment"], "Census unemployment rate in 2023. " + method),
        ],
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "wallis_futuna.json").read_text())
    assert len(doc["lenses"]) == 7 and doc["matched_communes"] == 3
    for lens_doc in doc["lenses"]:
        vals = [v for v in lens_doc["values"] if v is not None]
        assert 2 <= len(vals) <= 30 and len(set(vals)) >= 2
    return [("PASS", "wallis_futuna.json: seven Wallis-et-Futuna census-detail lenses")]
