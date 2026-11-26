"""Electricity-consumption lenses."""

from ..core.store import load_interim, write_web

REQUIRES = ["_world", "fr_electricity", "fr_boundaries"]
PRODUCES = ["electricity.json"]
RAMP = ["#252a3f", "#365070", "#457a76", "#a69b53", "#e1c55e"]
SECTORS = {
    "RESIDENTIEL": ("residential_electricity", "Residential electricity", "🏠", "Residential 2024 electricity consumption on the Enedis distribution network per department resident."),
    "TERTIAIRE": ("tertiary_electricity", "Tertiary electricity", "🏢", "Tertiary-sector 2024 electricity consumption on the Enedis distribution network per department resident. Values reflect where economic activity is located, not household use."),
    "INDUSTRIE": ("industrial_electricity", "Industrial electricity", "🏭", "Industrial 2024 electricity consumption on the Enedis distribution network per department resident. Values reflect where industrial load is located."),
    "AGRICULTURE": ("agricultural_electricity", "Agricultural electricity", "🚜", "Agricultural 2024 electricity consumption on the Enedis distribution network per department resident. Values reflect where metered agricultural load is located."),
}


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def lens(lens_id, name, emoji, vals, desc):
    return {
        "id": lens_id, "group": "energy_use", "name": name, "icon": lens_id, "emoji": emoji,
        "unit": "MWh per resident per year", "format": "float", "scale": "linear",
        "domain": [percentile(vals, 2), percentile(vals, 98)], "ramp": RAMP, "higher_is": "neutral",
        "source": "fr_electricity", "description": desc + " Enedis does not serve Corsica and some local-distribution areas, so low values there reflect network coverage as well as use.",
        "values": vals,
    }


def build():
    world = load_interim("_world")
    electricity = load_interim("fr_electricity")
    boundaries = load_interim("fr_boundaries")
    rows = {d["code"]: d for d in electricity["departments"] if d.get("consumption_mwh") and d.get("rows")}
    population = {}
    for c in boundaries["communes"]:
        population[c["department"]] = population.get(c["department"], 0) + (c.get("population") or 0)
    counties = world["counties"]

    def values(selector):
        per_resident = {
            dep: selector(row) / population[dep]
            for dep, row in rows.items() if dep in population and population[dep]
        }
        vals = []
        for ci in world["county"]:
            dep = counties[ci] if ci >= 0 else None
            vals.append(round(per_resident.get(dep, 0), 3) if dep in per_resident else None)
        return vals

    total_vals = values(lambda row: row["consumption_mwh"])
    lenses = [lens(
        "electricity_use", "Electricity use", "⚡", total_vals,
        "Total 2024 electricity consumption on the Enedis distribution network per department resident. Department-level totals aggregate residential and economic activity; they are not household-only consumption."
    )]
    for sector, (lens_id, name, emoji, desc) in SECTORS.items():
        lenses.append(lens(lens_id, name, emoji, values(lambda row, s=sector: row.get("sectors", {}).get(s, 0)), desc))
    write_web("electricity.json", {
        "version": 1, "vintage": "Enedis electricity consumption, 2024", "sources": ["fr_electricity"],
        "group": {"id": "energy_use", "name": "Energy use"}, "lenses": lenses,
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "electricity.json").read_text())
    vals = [v for v in doc["lenses"][0]["values"] if v is not None]
    assert len(doc["lenses"]) == 5 and len(vals) > 2500 and 2 < sum(vals) / len(vals) < 10
    return [("PASS", f"electricity.json: total and sectoral electricity lenses over {len(vals)} cells")]
