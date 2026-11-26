"""Electricity-consumption lens."""

from ..core.store import load_interim, write_web

REQUIRES = ["_world", "fr_electricity", "fr_boundaries"]
PRODUCES = ["electricity.json"]
RAMP = ["#252a3f", "#365070", "#457a76", "#a69b53", "#e1c55e"]


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def build():
    world = load_interim("_world")
    electricity = load_interim("fr_electricity")
    boundaries = load_interim("fr_boundaries")
    consumption = {d["code"]: d["consumption_mwh"] for d in electricity["departments"] if d.get("consumption_mwh") and d.get("rows")}
    population = {}
    for c in boundaries["communes"]:
        population[c["department"]] = population.get(c["department"], 0) + (c.get("population") or 0)
    per_resident = {dep: consumption[dep] / population[dep] for dep in consumption if dep in population and population[dep]}
    vals = []
    counties = world["counties"]
    for ci in world["county"]:
        dep = counties[ci] if ci >= 0 else None
        vals.append(round(per_resident.get(dep, 0), 3) if dep in per_resident else None)
    write_web("electricity.json", {
        "version": 1, "vintage": "Enedis electricity consumption, 2024", "sources": ["fr_electricity"],
        "group": {"id": "energy_use", "name": "Energy use"},
        "lenses": [{
            "id": "electricity_use", "group": "energy_use", "name": "Electricity use", "icon": "electricity", "emoji": "⚡",
            "unit": "MWh per resident per year", "format": "float", "scale": "linear",
            "domain": [percentile(vals, 2), percentile(vals, 98)], "ramp": RAMP, "higher_is": "neutral",
            "source": "fr_electricity",
            "description": "Total 2024 electricity consumption on the Enedis distribution network per department resident. Department-level totals aggregate residential and economic activity; they are not household-only consumption. Enedis does not serve Corsica and some local-distribution areas, so low values in those departments reflect network coverage as well as use.",
            "values": vals,
        }],
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "electricity.json").read_text())
    vals = [v for v in doc["lenses"][0]["values"] if v is not None]
    assert len(vals) > 2500 and 2 < sum(vals) / len(vals) < 10
    return [("PASS", f"electricity.json: electricity-use lens over {len(vals)} cells")]
