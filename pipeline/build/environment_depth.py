"""Land-artificialization and CORINE environment-depth lenses."""

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .connectivity import shape_weights

REQUIRES = ["_world", "fr_boundaries", "fr_corine", "fr_land_consumption"]
PRODUCES = ["environment_depth.json"]
RAMP = ["#213b32", "#38654f", "#5f8f61", "#a8ba68", "#dfc46b"]


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def parent_code(code):
    if code.startswith("751"):
        return "75056"
    if code.startswith("132") and len(code) == 5:
        return "13055"
    if code.startswith("6938"):
        return "69123"
    return code


def lens(lens_id, name, emoji, unit, vals, desc, higher="neutral", source="fr_land_consumption"):
    return {
        "id": lens_id, "group": "environment_depth", "name": name, "icon": lens_id, "emoji": emoji,
        "unit": unit, "format": "pct", "scale": "linear", "domain": [percentile(vals, 2), percentile(vals, 98)],
        "ramp": RAMP, "higher_is": higher, "source": source, "description": desc, "values": vals,
    }


def build():
    world = load_interim("_world")
    boundaries = load_interim("fr_boundaries")
    consumption = load_interim("fr_land_consumption")
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    weights_by_commune = shape_weights(world, grid, proj, boundaries["communes"])

    keys = ["artificialized", "consumed_share", "recent_consumed_share", "housing_share"]
    acc = {k: defaultdict(float) for k in keys}
    valid = {k: defaultdict(float) for k in keys}
    den = defaultdict(float)
    matched = 0
    for raw_code, row in consumption["communes"].items():
        weights = weights_by_commune.get(parent_code(raw_code))
        if not weights:
            continue
        matched += 1
        for cell, weight in weights.items():
            den[cell] += weight
            for key in keys:
                if row.get(key) is not None:
                    acc[key][cell] += row[key] * weight
                    valid[key][cell] += weight

    vals = {}
    for key in keys:
        vals[key] = [round(acc[key][i] / valid[key][i], 5) if valid[key].get(i) else None for i in range(grid.size)]

    covered = [world["owner"][i] >= 0 and world["cover"][i] for i in range(grid.size)]
    wetland = [round(world["pct"]["wetland"][i] / 100, 5) if covered[i] else None for i in range(grid.size)]
    natural = []
    for i in range(grid.size):
        if not covered[i]:
            natural.append(None)
        else:
            share = sum(world["pct"][key][i] for key in ("forest", "grass", "shrub", "wetland")) / 100
            natural.append(round(min(1, share), 5))

    commune_note = " Commune values are distributed approximately over commune polygons at a 1 km lattice, so values are spatial indicators rather than parcel-level measurements."
    lenses = [
        lens("artificialized_land", "Artificialized land", "🏗️", "share of commune land", vals["artificialized"], "Share of commune surface artificialized by 2025 in the Cerema land-registry observatory. Artificialization is a legal/land-use measure broader than only continuous built-up cover." + commune_note, higher="worse"),
        lens("land_consumption", "Land consumed since 2011", "🚜", "share of commune land", vals["consumed_share"], "Natural, agricultural and forest land consumed between 1 January 2011 and 1 January 2025 as a share of commune surface. This is cumulative land-take flow, not the total artificialized stock." + commune_note, higher="worse"),
        lens("recent_land_consumption", "Recent land consumption", "📈", "share of commune land", vals["recent_consumed_share"], "Natural, agricultural and forest land consumed between 1 January 2021 and 1 January 2025 as a share of commune surface. The short period makes this a recent-pressure indicator." + commune_note, higher="worse"),
        lens("housing_land_consumption", "Housing-driven land take", "🏘️", "share of land consumption", vals["housing_share"], "Share of 2011–2025 natural/agricultural/forest land consumption assigned to housing use in the Cerema land-registry typology. Null where there was no measured consumption." + commune_note),
        lens("wetland_cover", "Wetland cover", "🪷", "share of land", wetland, "Share of each hex classified as inland or coastal wetland by CORINE Land Cover 2018. CORINE is a relatively coarse land-cover map and does not cover overseas territories in this extract.", source="fr_corine"),
        lens("natural_land_cover", "Natural and semi-natural land", "🌿", "share of land", natural, "Combined CORINE forest, natural grassland, shrubland and wetland share. This is a structural land-cover proxy for ecological continuity, not a validated green-and-blue-corridor network; overseas territories are outside the CORINE extract.", source="fr_corine"),
    ]
    write_web("environment_depth.json", {
        "version": 1,
        "vintage": "Cerema artificialization 2011–2025; CORINE Land Cover 2018",
        "sources": ["fr_land_consumption", "fr_corine"],
        "group": {"id": "environment_depth", "name": "Environment depth"},
        "matched_land_consumption_communes": matched,
        "source_communes": len(consumption["communes"]),
        "lenses": lenses,
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "environment_depth.json").read_text())
    assert len(doc["lenses"]) == 6 and doc["matched_land_consumption_communes"] > 30000
    vals = [v for v in doc["lenses"][0]["values"] if v is not None]
    assert len(vals) > 3000 and 0 < sum(vals) / len(vals) < 0.3 and max(vals) < 1
    return [("PASS", f"environment_depth.json: six artificialization and land-cover lenses over {len(vals)} cells")]
