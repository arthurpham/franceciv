"""New Caledonia commune-level census lenses."""

from collections import defaultdict
import unicodedata

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, load_interim_payload, write_web
from .connectivity import shape_weights

REQUIRES = ["_world", "fr_boundaries", "fr_new_caledonia"]
PRODUCES = ["new_caledonia.json"]
RAMP = ["#1b1035", "#4b2377", "#9a3b8a", "#e0645e", "#f9b24a", "#fff3a8"]


def norm(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "")).lower() if c.isalnum())


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def lens(lens_id, group, name, emoji, unit, vals, desc):
    return {"id": lens_id, "group": group, "name": name, "icon": lens_id, "emoji": emoji, "unit": unit,
            "format": "pct", "scale": "linear", "domain": [percentile(vals, 2), percentile(vals, 98)], "ramp": RAMP,
            "higher_is": "neutral", "source": "fr_new_caledonia", "description": desc, "values": vals}


def build():
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    nc = load_interim("fr_new_caledonia")
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    weights = shape_weights(world, grid, proj, bounds["communes"])
    rows = nc["communes"]
    acc = defaultdict(lambda: defaultdict(float))
    matched = 0
    specs = [
        ("seniors", "population", "nc_seniors"), ("higher_education", "adults15", "nc_higher_education"),
        ("unemployed", "labour", "nc_unemployment"), ("agriculture", "sector_jobs", "nc_agriculture"),
        ("second_homes", "dwellings", "nc_second_homes"), ("vacant", "dwellings", "nc_vacancy"),
        ("owner_homes", "main_homes", "nc_homeownership"), ("no_running_water", "water_homes", "nc_no_running_water"),
        ("internet_households", "households", "nc_internet_access"),
    ]
    for c in bounds["communes"]:
        if c.get("department") != "988":
            continue
        row = rows.get(norm(c["name"]))
        wts = weights.get(c["code"])
        if not row or not wts:
            continue
        matched += 1
        labour = (row.get("employed") or 0) + (row.get("unemployed") or 0)
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
    method = "Commune-level counts from the 2019 New Caledonia census are distributed over commune polygons and summed within each hex. Values cover only New Caledonia; the rest of France is null because these are territory-specific census tables."
    write_web("new_caledonia.json", {
        "version": 1, "vintage": load_interim_payload("fr_new_caledonia")["vintage"], "sources": ["fr_new_caledonia"], "matched_communes": matched, "methodology": method,
        "group": {"id": "overseas", "name": "Overseas detail"},
        "lenses": [
            lens("nc_seniors", "overseas", "New Caledonia residents 65+", "👵", "share of residents", series["nc_seniors"], "Residents aged 65 or older as a share of all residents. " + method),
            lens("nc_higher_education", "overseas", "New Caledonia higher education", "🎓", "share of residents 15+", series["nc_higher_education"], "Residents aged 15 or older whose highest diploma is a first-cycle or advanced higher-education qualification. " + method),
            lens("nc_unemployment", "overseas", "New Caledonia unemployment", "🧭", "share of labour force", series["nc_unemployment"], "Census unemployed residents as a share of employed plus unemployed residents aged 15 or older. " + method),
            lens("nc_agriculture", "overseas", "New Caledonia agricultural employment", "🌾", "share of employment", series["nc_agriculture"], "Agricultural work as a share of employment among residents aged 15 or older. " + method),
            lens("nc_second_homes", "overseas", "New Caledonia second homes", "🏡", "share of dwellings", series["nc_second_homes"], "Secondary and occasional homes as a share of all dwellings. " + method),
            lens("nc_vacancy", "overseas", "New Caledonia vacant homes", "⬜", "share of dwellings", series["nc_vacancy"], "Vacant dwellings as a share of all dwellings. " + method),
            lens("nc_homeownership", "overseas", "New Caledonia homeownership", "🏠", "share of main homes", series["nc_homeownership"], "Owner-occupied main residences as a share of main residences. " + method),
            lens("nc_no_running_water", "overseas", "New Caledonia homes without running water", "🚰", "share of main homes", series["nc_no_running_water"], "Main residences without running water as a share of main residences. " + method),
            lens("nc_internet_access", "overseas", "New Caledonia household internet", "🌐", "share of households", series["nc_internet_access"], "Ordinary households reporting internet access. " + method),
        ],
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "new_caledonia.json").read_text())
    assert len(doc["lenses"]) == 9 and doc["matched_communes"] == 33
    for lens_doc in doc["lenses"]:
        vals = [v for v in lens_doc["values"] if v is not None]
        assert 5 <= len(vals) <= 100 and min(vals) >= 0 and max(vals) <= 1
        assert len(set(vals)) > 5
    return [("PASS", "new_caledonia.json: nine New Caledonia commune-detail lenses")]
