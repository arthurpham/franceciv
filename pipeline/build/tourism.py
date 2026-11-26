"""Tourism lenses."""

from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web

REQUIRES = ["_world", "fr_tourism", "fr_boundaries"]
PRODUCES = ["tourism.json"]
RAMP = ["#26324a", "#355d7a", "#4b907e", "#b8ad59", "#e2c35b"]


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def build():
    world = load_interim("_world")
    tourism = load_interim("fr_tourism")
    boundaries = load_interim("fr_boundaries")
    nights = {d["code"]: d["hotel_nights"] for d in tourism["departments"]}
    population = {}
    for c in boundaries["communes"]:
        population[c["department"]] = population.get(c["department"], 0) + (c.get("population") or 0)
    per_resident = {dep: nights[dep] / population[dep] for dep in nights if dep in population and population[dep]}
    vals = []
    counties = world["counties"]
    for ci in world["county"]:
        dep = counties[ci] if ci >= 0 else None
        vals.append(round(per_resident.get(dep, 0), 3) if dep in per_resident else None)
    write_web("tourism.json", {
        "version": 1, "vintage": "INSEE tourist accommodation occupancy, 2024", "sources": ["fr_tourism"],
        "group": {"id": "tourism", "name": "Tourism"},
        "lenses": [{
            "id": "hotel_tourism", "group": "tourism", "name": "Hotel tourism", "icon": "tourism", "emoji": "🏨",
            "unit": "hotel nights per resident", "format": "float", "scale": "linear",
            "domain": [percentile(vals, 2), percentile(vals, 98)], "ramp": RAMP, "higher_is": "neutral",
            "source": "fr_tourism",
            "description": "Hotel nights spent in 2024 per department resident, from INSEE monthly hotel-occupancy statistics. This measures hotel tourism intensity, not all accommodation.",
            "values": vals,
        }],
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "tourism.json").read_text())
    vals = [v for v in doc["lenses"][0]["values"] if v is not None]
    assert len(vals) > 2500 and 0 < sum(vals) / len(vals) < 20
    return [("PASS", f"tourism.json: hotel-tourism lens over {len(vals)} cells")]
