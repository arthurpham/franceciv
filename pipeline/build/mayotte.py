"""Mayotte commune-level census lenses."""

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, load_interim_payload, write_web
from .connectivity import shape_weights

REQUIRES = ["_world", "fr_boundaries", "fr_mayotte"]
PRODUCES = ["mayotte.json"]
RAMP = ["#1b1035", "#4b2377", "#9a3b8a", "#e0645e", "#f9b24a", "#fff3a8"]


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def lens(lens_id, name, emoji, unit, vals, desc):
    return {"id": lens_id, "group": "overseas", "name": name, "icon": lens_id, "emoji": emoji, "unit": unit,
            "format": "pct", "scale": "linear", "domain": [percentile(vals, 2), percentile(vals, 98)], "ramp": RAMP,
            "higher_is": "neutral", "encoding": "sparse-index-v1", "source": "fr_mayotte", "description": desc,
            "values": {str(i): v for i, v in enumerate(vals) if v is not None}}


def build():
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    mayotte = load_interim("fr_mayotte")
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    weights = shape_weights(world, grid, proj, bounds["communes"])
    rows = mayotte["communes"]
    acc = defaultdict(lambda: defaultdict(float))
    matched = 0
    specs = [
        ("children", "population", "mayotte_children"), ("seniors", "population", "mayotte_seniors"),
        ("unemployed", "labour", "mayotte_unemployment"), ("higher_education", "adults15", "mayotte_higher_education"),
        ("fragile_homes", "dwellings", "mayotte_fragile_housing"), ("vacant", "dwellings", "mayotte_vacancy"),
        ("earth_floor", "main_homes", "mayotte_earth_floors"), ("owner_homes", "main_homes", "mayotte_homeownership"),
        ("no_car", "main_homes", "mayotte_no_car"), ("no_indoor_wc", "main_homes", "mayotte_no_indoor_wc"),
        ("no_electricity", "main_homes", "mayotte_no_electricity"), ("internet", "main_homes", "mayotte_internet"),
    ]
    for c in bounds["communes"]:
        if c.get("department") != "976":
            continue
        row = rows.get(c["code"])
        wts = weights.get(c["code"])
        if not row or not wts:
            continue
        matched += 1
        labour = row.get("employed", 0) + row.get("unemployed", 0)
        for cell, weight in wts.items():
            seen_denominators = set()
            for num, den, key in specs:
                den_value = labour if den == "labour" else row.get(den)
                if row.get(num) is None or not den_value:
                    continue
                acc[cell][num] += row[num] * weight
                if den not in seen_denominators:
                    acc[cell][den] += den_value * weight
                    seen_denominators.add(den)
    series = {}
    for num, den, key in specs:
        vals = []
        for i in range(grid.size):
            a = acc.get(i)
            vals.append(round(a[num] / a[den], 4) if a and a[den] else None)
        series[key] = vals
    method = "Commune-level counts from the 2017 Mayotte census are distributed over commune polygons and summed within each hex. Values cover only Mayotte; the rest of France is null because these are territory-specific census tables. Higher education is measured among non-scolarized residents aged 15 or older."
    write_web("mayotte.json", {
        "version": 1, "vintage": load_interim_payload("fr_mayotte")["vintage"], "sources": ["fr_mayotte"], "matched_communes": matched, "methodology": method,
        "group": {"id": "overseas", "name": "Overseas detail"},
        "lenses": [
            lens("mayotte_children", "Mayotte children", "🧒", "share of residents", series["mayotte_children"], "Residents aged 0–17 as a share of all residents. " + method),
            lens("mayotte_seniors", "Mayotte residents 65+", "👵", "share of residents", series["mayotte_seniors"], "Residents aged 65 or older as a share of all residents. " + method),
            lens("mayotte_unemployment", "Mayotte unemployment", "🧭", "share of labour force", series["mayotte_unemployment"], "Census unemployed residents as a share of employed plus unemployed residents aged 15 or older. " + method),
            lens("mayotte_higher_education", "Mayotte higher education", "🎓", "share of non-scolarized residents 15+", series["mayotte_higher_education"], "Non-scolarized residents aged 15 or older whose highest diploma is bac+2 or above. " + method),
            lens("mayotte_fragile_housing", "Mayotte fragile housing", "🏚️", "share of dwellings", series["mayotte_fragile_housing"], "Sheet-metal, wood, plant-material or earth houses as a share of all dwellings. " + method),
            lens("mayotte_vacancy", "Mayotte vacant homes", "⬜", "share of dwellings", series["mayotte_vacancy"], "Vacant dwellings as a share of all dwellings. " + method),
            lens("mayotte_earth_floors", "Mayotte earth floors", "🟫", "share of main homes", series["mayotte_earth_floors"], "Main residences with beaten-earth floors. " + method),
            lens("mayotte_homeownership", "Mayotte homeownership", "🏠", "share of main homes", series["mayotte_homeownership"], "Owner-occupied main residences, including owners of both land and dwelling. " + method),
            lens("mayotte_no_car", "Mayotte homes without cars", "🚗", "share of main homes", series["mayotte_no_car"], "Main residences with no car. " + method),
            lens("mayotte_no_indoor_wc", "Mayotte homes without indoor WC", "🚽", "share of main homes", series["mayotte_no_indoor_wc"], "Main residences without an indoor toilet. " + method),
            lens("mayotte_no_electricity", "Mayotte homes without electricity", "⚡", "share of main homes", series["mayotte_no_electricity"], "Main residences without electricity. " + method),
            lens("mayotte_internet", "Mayotte household internet", "🌐", "share of main homes", series["mayotte_internet"], "Main residences reporting an internet connection. " + method),
        ],
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "mayotte.json").read_text())
    assert len(doc["lenses"]) == 12 and doc["matched_communes"] == 17
    for lens_doc in doc["lenses"]:
        vals = [v for v in lens_doc["values"].values() if v is not None]
        assert 3 <= len(vals) <= 60 and min(vals) >= 0 and max(vals) <= 1
        assert len(set(vals)) > 3
    return [("PASS", "mayotte.json: twelve Mayotte commune-detail lenses")]
