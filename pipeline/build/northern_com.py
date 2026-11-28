"""Northern overseas collectivity commune-level census lenses."""

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, load_interim_payload, write_web
from .connectivity import shape_weights

REQUIRES = ["_world", "fr_boundaries", "fr_northern_com"]
PRODUCES = ["northern_com.json"]
RAMP = ["#1b1035", "#4b2377", "#9a3b8a", "#e0645e", "#f9b24a", "#fff3a8"]
SPECS = [
    ("children", "population", "north_children", "Northern collectivity children", "🧒", "share of residents", "Residents aged 0–17 as a share of all residents."),
    ("seniors", "population", "north_seniors", "Northern collectivity residents 65+", "👵", "share of residents", "Residents aged 65 or older as a share of all residents."),
    ("unemployed", "labour", "north_unemployment", "Northern collectivity unemployment", "🧭", "share of labour force", "Census unemployed residents as a share of employed plus unemployed residents aged 15 or older."),
    ("higher_education", "adults15", "north_higher_education", "Northern collectivity higher education", "🎓", "share of non-scolarized residents 15+", "Non-scolarized residents aged 15 or older whose highest diploma is in higher education."),
    ("second_homes", "dwellings", "north_second_homes", "Northern collectivity second homes", "🏖️", "share of dwellings", "Secondary and occasional residences as a share of all dwellings."),
    ("vacant", "dwellings", "north_vacancy", "Northern collectivity vacant homes", "⬜", "share of dwellings", "Vacant dwellings as a share of all dwellings."),
    ("owner_homes", "main_homes", "north_homeownership", "Northern collectivity homeownership", "🏠", "share of main homes", "Owner-occupied main residences."),
    ("social_homes", "main_homes", "north_social_housing", "Northern collectivity social housing", "🏘️", "share of main homes", "Main residences rented in the unfurnished social-housing stock."),
]


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def lens(lens_id, name, emoji, unit, vals, desc):
    return {"id": lens_id, "group": "overseas", "name": name, "icon": lens_id, "emoji": emoji, "unit": unit,
            "format": "pct", "scale": "linear", "domain": [percentile(vals, 2), percentile(vals, 98)], "ramp": RAMP,
            "higher_is": "neutral", "encoding": "sparse-index-v1", "source": "fr_northern_com", "description": desc,
            "values": {str(i): v for i, v in enumerate(vals) if v is not None}}


def build():
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    census = load_interim("fr_northern_com")
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    weights = shape_weights(world, grid, proj, bounds["communes"])
    rows = census["communes"]
    acc = defaultdict(lambda: defaultdict(float))
    matched = 0
    for c in bounds["communes"]:
        row = rows.get(c["code"])
        wts = weights.get(c["code"])
        if not row or not wts:
            continue
        matched += 1
        labour = row.get("employed", 0) + row.get("unemployed", 0)
        for cell, weight in wts.items():
            seen_denominators = set()
            for num, den, *_ in SPECS:
                den_value = labour if den == "labour" else row.get(den)
                if row.get(num) is None or not den_value:
                    continue
                acc[cell][num] += row[num] * weight
                if den not in seen_denominators:
                    acc[cell][den] += den_value * weight
                    seen_denominators.add(den)
    method = "Commune-level counts from the 2023 census are distributed over commune polygons and summed within each hex. Values cover only Saint-Pierre-et-Miquelon, Saint-Barthélemy and Saint-Martin; the rest of France is null because these are territory-specific detailed census tables."
    lenses = []
    for num, den, lens_id, name, emoji, unit, desc in SPECS:
        vals = []
        for i in range(grid.size):
            a = acc.get(i)
            vals.append(round(a[num] / a[den], 4) if a and a[den] else None)
        lenses.append(lens(lens_id, name, emoji, unit, vals, desc + " " + method))
    write_web("northern_com.json", {
        "version": 1, "vintage": load_interim_payload("fr_northern_com")["vintage"], "sources": ["fr_northern_com"], "matched_communes": matched, "methodology": method,
        "group": {"id": "overseas", "name": "Overseas detail"},
        "lenses": lenses,
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "northern_com.json").read_text())
    assert len(doc["lenses"]) == 8 and doc["matched_communes"] == 4
    for lens_doc in doc["lenses"]:
        vals = [v for v in (lens_doc["values"].values() if isinstance(lens_doc["values"], dict) else lens_doc["values"]) if v is not None]
        assert 2 <= len(vals) <= 60 and min(vals) >= 0 and max(vals) <= 1
    return [("PASS", "northern_com.json: eight northern-collectivity census lenses")]
