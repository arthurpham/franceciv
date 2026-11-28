"""French Polynesia commune-level census lenses."""

from collections import defaultdict
import unicodedata

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, load_interim_payload, write_web
from .connectivity import shape_weights

REQUIRES = ["_world", "fr_boundaries", "fr_polynesia"]
PRODUCES = ["polynesia.json"]
RAMP = ["#1b1035", "#4b2377", "#9a3b8a", "#e0645e", "#f9b24a", "#fff3a8"]


def norm(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "")).lower() if c.isalnum())


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def lens(lens_id, name, emoji, unit, vals, desc):
    return {"id": lens_id, "group": "overseas", "name": name, "icon": lens_id, "emoji": emoji, "unit": unit,
            "format": "pct", "scale": "linear", "domain": [percentile(vals, 2), percentile(vals, 98)], "ramp": RAMP,
            "higher_is": "neutral", "encoding": "sparse-index-v1", "source": "fr_polynesia", "description": desc, "values": {str(i): v for i, v in enumerate(vals) if v is not None}}


def build():
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    pf = load_interim("fr_polynesia")
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    weights = shape_weights(world, grid, proj, bounds["communes"])
    rows = pf["communes"]
    acc = defaultdict(lambda: defaultdict(float))
    matched = 0
    specs = [
        ("seniors60", "population", "pf_seniors"), ("higher_education", "adults15", "pf_higher_education"),
        ("unemployment", "labour_force", "pf_unemployment"), ("agriculture", "employed", "pf_agriculture"),
        ("second_homes", "dwellings", "pf_second_homes"), ("vacant", "dwellings", "pf_vacancy"),
        ("owner_homes", "main_homes", "pf_homeownership"), ("outside_commute", "workers", "pf_outside_commuting"),
        ("no_car", "main_homes", "pf_no_car"), ("boat_access", "main_homes", "pf_boat_access"),
    ]
    direct = {"higher_education", "unemployment", "agriculture", "no_car", "boat_access"}
    for c in bounds["communes"]:
        if c.get("department") != "987":
            continue
        row = rows.get(norm(c["name"]))
        wts = weights.get(c["code"])
        if not row or not wts:
            continue
        matched += 1
        for cell, weight in wts.items():
            seen_denominators = set()
            for num, den, key in specs:
                den_value = row.get(den)
                numerator = row.get(num)
                if numerator is None or not den_value:
                    continue
                numerator = numerator * den_value if num in direct else numerator
                acc[cell][num] += numerator * weight
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
    method = "Commune-level tables from the 2022 French Polynesia census geographic workbooks are distributed over commune polygons and summed within each hex. Values cover only French Polynesia; the rest of France is null because these are territory-specific tables."
    write_web("polynesia.json", {
        "version": 1, "vintage": load_interim_payload("fr_polynesia")["vintage"], "sources": ["fr_polynesia"], "matched_communes": matched, "methodology": method,
        "group": {"id": "overseas", "name": "Overseas detail"},
        "lenses": [
            lens("pf_seniors", "French Polynesia residents 60+", "👵", "share of residents", series["pf_seniors"], "Residents aged 60 or older as a share of all residents. " + method),
            lens("pf_higher_education", "French Polynesia higher education", "🎓", "share of residents 15+", series["pf_higher_education"], "Residents aged 15 or older with a first-cycle or advanced higher-education diploma. " + method),
            lens("pf_unemployment", "French Polynesia unemployment", "🧭", "share of labour force", series["pf_unemployment"], "Census unemployment rate among the labour force. " + method),
            lens("pf_agriculture", "French Polynesia agricultural employment", "🌾", "share of employment", series["pf_agriculture"], "Agricultural workers as a share of employed active residents. " + method),
            lens("pf_second_homes", "French Polynesia second homes", "🏡", "share of dwellings", series["pf_second_homes"], "Secondary and occasional homes as a share of all dwellings. " + method),
            lens("pf_vacancy", "French Polynesia vacant homes", "⬜", "share of dwellings", series["pf_vacancy"], "Vacant dwellings as a share of all dwellings. " + method),
            lens("pf_homeownership", "French Polynesia homeownership", "🏠", "share of main homes", series["pf_homeownership"], "Owner-occupied main residences as a share of main residences. " + method),
            lens("pf_outside_commuting", "French Polynesia intercommunal commuting", "🛶", "share of workers", series["pf_outside_commuting"], "Employed residents working outside their commune of residence. " + method),
            lens("pf_no_car", "French Polynesia homes without cars", "🚗", "share of main homes", series["pf_no_car"], "Main residences reporting no car. " + method),
            lens("pf_boat_access", "French Polynesia household boats", "⛵", "share of main homes", series["pf_boat_access"], "Main residences reporting access to at least one boat. " + method),
        ],
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "polynesia.json").read_text())
    assert len(doc["lenses"]) == 10 and doc["matched_communes"] == 48
    for lens_doc in doc["lenses"]:
        vals = [v for v in lens_doc["values"].values() if v is not None]
        assert 5 <= len(vals) <= 150 and min(vals) >= 0 and max(vals) <= 1
        assert len(set(vals)) > 5
    return [("PASS", "polynesia.json: ten French Polynesia commune-detail lenses")]
