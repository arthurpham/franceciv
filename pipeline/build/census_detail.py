"""Commune-level census detail lenses from INSEE Melodi tables."""

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .connectivity import shape_weights

REQUIRES = ["_world", "fr_boundaries", "fr_insee_stats"]
PRODUCES = ["census_detail.json"]
RAMP = ["#1b1035", "#4b2377", "#9a3b8a", "#e0645e", "#f9b24a", "#fff3a8"]


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def lens(lens_id, group, name, emoji, unit, vals, desc):
    return {"id": lens_id, "group": group, "name": name, "icon": lens_id, "emoji": emoji, "unit": unit,
            "format": "pct", "scale": "linear", "domain": [percentile(vals, 2), percentile(vals, 98)], "ramp": RAMP,
            "higher_is": "neutral", "source": "fr_insee_stats", "description": desc, "values": vals}


def add_ratio(acc, weights, row, numerator_keys, denominator_keys, num_key, den_key):
    den = sum(row.get(k) or 0 for k in denominator_keys)
    if not den:
        return
    num = sum(row.get(k) or 0 for k in numerator_keys)
    for cell, weight in weights.items():
        acc[cell][num_key] += num * weight
        acc[cell][den_key] += den * weight


def build():
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    stats = load_interim("fr_insee_stats")
    datasets = stats["datasets"]
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    weights_by_commune = shape_weights(world, grid, proj, bounds["communes"])
    acc = defaultdict(lambda: defaultdict(float))
    matched = {key: 0 for key in ["activity", "education", "population_age", "commuting", "immigration"]}

    for c in bounds["communes"]:
        weights = weights_by_commune.get(c["code"])
        if not weights:
            continue
        row = datasets.get("activity", {}).get("COM", {}).get(c["code"])
        if row:
            matched["activity"] += 1
            add_ratio(acc, weights, row, ["EMPSTA_ENQ=2|AGE=Y15T64"], ["EMPSTA_ENQ=1|AGE=Y15T64", "EMPSTA_ENQ=2|AGE=Y15T64"], "unemployed", "labour")
        row = datasets.get("education", {}).get("COM", {}).get(c["code"])
        if row:
            matched["education"] += 1
            add_ratio(acc, weights, row, ["AGE=Y_GE15|EDUC=500T702_RP"], ["AGE=Y_GE15"], "higher", "adults")
        row = datasets.get("population_age", {}).get("COM", {}).get(c["code"])
        if row:
            matched["population_age"] += 1
            add_ratio(acc, weights, row, ["AGE=Y_GE65"], ["_T"], "seniors", "residents")
        row = datasets.get("commuting", {}).get("COM", {}).get(c["code"])
        if row:
            matched["commuting"] += 1
            add_ratio(acc, weights, row, ["TRANS=6|AGE=Y_GE15|EMPSTA_ENQ=1"], ["AGE=Y_GE15|EMPSTA_ENQ=1"], "transit", "transit_workers")
            add_ratio(acc, weights, row, ["TRANS=5|AGE=Y_GE15|EMPSTA_ENQ=1"], ["AGE=Y_GE15|EMPSTA_ENQ=1"], "car", "car_workers")
        row = datasets.get("immigration", {}).get("COM", {}).get(c["code"])
        if row:
            matched["immigration"] += 1
            add_ratio(acc, weights, row, ["IMMI=1"], ["_T"], "immigrants", "population")

    def values(num_key, den_key):
        out = []
        for i in range(grid.size):
            a = acc.get(i)
            out.append(round(a[num_key] / a[den_key], 4) if a and a[den_key] else None)
        return out

    unemployment = values("unemployed", "labour")
    higher_education = values("higher", "adults")
    seniors = values("seniors", "residents")
    transit = values("transit", "transit_workers")
    car = values("car", "car_workers")
    immigration = values("immigrants", "population")
    method = ("Commune-level INSEE census 2023 counts are distributed over current commune polygons on a 1 km lattice and summed within each hex. "
              "Rows are census estimates, including fractional values; missing communes remain null rather than zero. The detailed Melodi commune extract covers metropolitan France and Guadeloupe, Martinique, Guyane and La Réunion, but not the additional overseas collectivities.")
    write_web("census_detail.json", {
        "version": 1,
        "vintage": f"INSEE census {stats['year']}, detailed commune tables",
        "sources": ["fr_insee_stats"],
        "matched_communes": matched,
        "methodology": method,
        "lenses": [
            lens("commune_unemployment", "prosperity", "Commune unemployment", "🧭", "share of labour force", unemployment,
                 "Unemployed census residents aged 15–64 as a share of the active population aged 15–64, using commune-level census counts rather than the department-level headline lens. " + method),
            lens("commune_higher_education", "people", "Commune higher education", "🎓", "share of out-of-school residents 15+", higher_education,
                 "Residents aged 15 or older whose highest diploma is in higher education, using commune-level census counts rather than the department-level headline lens. " + method),
            lens("commune_seniors", "people", "Commune residents 65+", "👵", "share of residents", seniors,
                 "Residents aged 65 or older as a share of all residents, using commune-level census counts rather than the department-level headline lens. " + method),
            lens("commune_public_transit", "people", "Commune public-transport commuting", "🚊", "share of employed residents", transit,
                 "Employed residents whose main home-to-work mode is public transport, using commune-level census counts rather than the department-level headline lens. " + method),
            lens("commune_car_commuting", "people", "Commune car commuting", "🚗", "share of employed residents", car,
                 "Employed residents whose main home-to-work mode is a car, van or truck, using commune-level census counts rather than the department-level headline lens. " + method),
            lens("commune_immigration", "people", "Commune immigration", "🌍", "share of residents", immigration,
                 "Immigrants as a share of all residents, using commune-level census counts rather than the department-level headline lens. INSEE defines an immigrant as a person born abroad who was not born a French national. " + method),
        ],
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "census_detail.json").read_text())
    assert len(doc["lenses"]) == 6
    for lens_doc in doc["lenses"]:
        vals = [v for v in lens_doc["values"] if v is not None]
        assert len(vals) > 2500 and min(vals) >= 0 and max(vals) <= 1
        assert len(set(vals)) > 200
    seniors = next(l for l in doc["lenses"] if l["id"] == "commune_seniors")["values"]
    assert any((v or 0) > 0.3 for v in seniors)
    return [("PASS", "census_detail.json: six commune-level census lenses")]
