"""Crime and school-access lenses."""

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .connectivity import nearest_land

REQUIRES = ["_world", "fr_crime", "fr_schools", "fr_boundaries", "fr_public_equipment"]
PRODUCES = ["public_services.json"]
RAMP = ["#26324a", "#465f78", "#718a69", "#b9a95c", "#e0bd55"]


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def dep_values(world, metric):
    counties = world["counties"]
    return [round(metric[counties[ci]], 4) if ci >= 0 and counties[ci] in metric else None for ci in world["county"]]


def lens(lens_id, name, emoji, unit, vals, source, desc):
    return {"id": lens_id, "group": "public_services", "name": name, "icon": lens_id, "emoji": emoji,
            "unit": unit, "format": "float", "scale": "linear", "domain": [percentile(vals, 2), percentile(vals, 98)],
            "ramp": RAMP, "higher_is": "neutral", "source": source, "description": desc, "values": vals}


def build():
    world = load_interim("_world")
    crime = load_interim("fr_crime")
    schools = load_interim("fr_schools")
    boundaries = load_interim("fr_boundaries")
    equipment = load_interim("fr_public_equipment")
    year = crime["year"]
    rates = {}
    for r in crime["rows"]:
        if r["year"] != year:
            continue
        rates.setdefault(r["department"], {})[r["indicator"]] = r["rate"] / 10  # per mille -> per 100 residents
    burglary = {d: v.get("Cambriolages de logement") for d, v in rates.items() if "Cambriolages de logement" in v}
    violence = {d: v.get("Violences physiques hors cadre familial") for d, v in rates.items() if "Violences physiques hors cadre familial" in v}

    population = {}
    for c in boundaries["communes"]:
        population[c["department"]] = population.get(c["department"], 0) + (c.get("population") or 0)
    school_counts = {d["department"]: d for d in schools["departments"]}
    primary = {}
    secondary = {}
    for dep, row in school_counts.items():
        pop = population.get(dep)
        if not pop:
            continue
        primary[dep] = 10000 * row.get("Ecole", 0) / pop
        secondary[dep] = 10000 * (row.get("Collège", 0) + row.get("Lycée", 0)) / pop

    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    cell_by_commune = {}
    pop_acc = {}
    for c in boundaries["communes"]:
        if c.get("lon") is None:
            continue
        x, y = proj(c["lon"], c["lat"])
        cell = nearest_land(world, grid, x, y)
        if cell >= 0:
            cell_by_commune[c["code"]] = cell
            pop_acc[cell] = pop_acc.get(cell, 0) + (c.get("population") or 0)
    commune_pop = {c["code"]: c.get("population") or 0 for c in boundaries["communes"]}
    eq_acc = {}
    unmatched_eq = 0
    for code, row in equipment["rows"].items():
        cell = cell_by_commune.get(code)
        if cell is None:
            unmatched_eq += 1
            continue
        a = eq_acc.setdefault(cell, {"food": 0, "pharm": 0, "culture": 0, "hospital": 0.0, "childcare": 0.0, "eldercare": 0.0, "cinemas": 0.0, "pools": 0.0, "rail": 0.0, "service_pop": 0})
        a["food"] += row["food_shops"]
        a["pharm"] += row["pharmacies"]
        a["culture"] += row["culture_sports"]
        a["hospital"] += row.get("hospital_services", 0)
        a["childcare"] += row.get("childcare", 0)
        a["eldercare"] += row.get("eldercare", 0)
        a["cinemas"] += row.get("cinemas", 0)
        a["pools"] += row.get("swimming_pools", 0)
        a["rail"] += row.get("rail_stations", 0)
        # Population-weight the presence score so hexes represent residents' typical access,
        # not the arithmetic mean of tiny and large communes.
        a["service_pop"] += row["essential_score"] * commune_pop.get(code, 0)
    essential, food, pharm, culture, hospital, childcare, eldercare, cinemas, pools, rail = [], [], [], [], [], [], [], [], [], []
    for i in range(grid.size):
        pop = pop_acc.get(i, 0)
        a = eq_acc.get(i, {"food": 0, "pharm": 0, "culture": 0, "hospital": 0.0, "childcare": 0.0, "eldercare": 0.0, "cinemas": 0.0, "pools": 0.0, "rail": 0.0, "service_pop": 0})
        essential.append(round(a["service_pop"] / pop, 2) if pop else None)
        food.append(round(a["food"] * 10_000 / pop, 2) if pop else None)
        pharm.append(round(a["pharm"] * 10_000 / pop, 2) if pop else None)
        culture.append(round(a["culture"] * 10_000 / pop, 2) if pop else None)
        hospital.append(round(a["hospital"] * 100_000 / pop, 2) if pop else None)
        childcare.append(round(a["childcare"] * 10_000 / pop, 2) if pop else None)
        eldercare.append(round(a["eldercare"] * 10_000 / pop, 2) if pop else None)
        cinemas.append(round(a["cinemas"] * 100_000 / pop, 2) if pop else None)
        pools.append(round(a["pools"] * 100_000 / pop, 2) if pop else None)
        rail.append(round(a["rail"] * 100_000 / pop, 2) if pop else None)

    write_web("public_services.json", {
        "version": 1, "vintage": f"Interior Ministry crime {year}; current school directory; INSEE BPE 2024", "sources": ["fr_crime", "fr_schools", "fr_public_equipment"],
        "group": {"id": "public_services", "name": "Safety & services"},
        "unmatched_equipment_communes": unmatched_eq,
        "lenses": [
            lens("burglary", "Burglaries", "🏠", "per 100 residents / yr", dep_values(world, burglary), "fr_crime", f"Recorded home burglaries per 100 residents in {year}. Police/gendarmerie recording and reporting propensity vary by territory."),
            lens("violence", "Physical violence", "🛡️", "per 100 residents / yr", dep_values(world, violence), "fr_crime", f"Recorded non-domestic physical violence per 100 residents in {year}. This is recorded crime, not victimization prevalence."),
            lens("primary_schools", "Primary schools", "🏫", "schools per 10k residents", dep_values(world, primary), "fr_schools", "Open schools classified as Ecole in the current Ministry directory, per 10,000 department residents."),
            lens("secondary_schools", "Collèges & lycées", "🎓", "schools per 10k residents", dep_values(world, secondary), "fr_schools", "Open Collège and Lycée establishments in the current Ministry directory, per 10,000 department residents."),
            lens("essential_services", "Everyday services", "🏪", "of 6 service categories", essential, "fr_public_equipment", "Population-weighted number of six everyday service categories present in communes: food shops, pharmacy, general practitioner, primary school, post office/relais and library. INSEE BPE 2024."),
            lens("food_shops", "Food shops", "🥖", "per 10k residents", food, "fr_public_equipment", "Food retailers counted in the INSEE Base permanente des équipements 2024, per 10,000 residents. Commune counts are aggregated by map hex."),
            lens("pharmacies", "Pharmacies", "💊", "per 10k residents", pharm, "fr_public_equipment", "Pharmacies counted in the INSEE Base permanente des équipements 2024, per 10,000 residents."),
            lens("culture_sports", "Sports & culture", "🎭", "facilities per 10k residents", culture, "fr_public_equipment", "Sports, leisure and cultural facilities counted in the INSEE Base permanente des équipements 2024, per 10,000 residents. Counts reflect facility records, not floor area or quality."),
            lens("hospital_services", "Hospital services", "🏥", "service records per 100k residents", hospital, "fr_public_equipment", "Hospital and specialized health-service records in INSEE BPE 2024 per 100,000 residents. Multiple service types can belong to the same hospital, so this measures recorded service presence rather than hospital count or capacity."),
            lens("childcare", "Childcare facilities", "🧒", "facilities per 10k residents", childcare, "fr_public_equipment", "Young-childcare establishments and micro-crèches in INSEE BPE 2024 per 10,000 residents. The denominator is total population, not the target under-3 population."),
            lens("eldercare", "Eldercare services", "🧓", "services per 10k residents", eldercare, "fr_public_equipment", "Elderly housing, home-care and support-service records in INSEE BPE 2024 per 10,000 residents. Counts reflect service records, not beds or capacity."),
            lens("cinemas", "Cinemas", "🎬", "screens/sites per 100k residents", cinemas, "fr_public_equipment", "Cinema records in INSEE BPE 2024 per 100,000 residents. Counts reflect BPE equipment records, not admissions or screen quality."),
            lens("swimming_pools", "Swimming pools", "🏊", "facilities per 100k residents", pools, "fr_public_equipment", "Swimming-pool facility records in INSEE BPE 2024 per 100,000 residents. Counts reflect facility records, not water area, public opening hours or quality."),
            lens("rail_station_access", "Rail stations", "🚉", "stations per 100k residents", rail, "fr_public_equipment", "Passenger rail stations of national, regional or local interest in INSEE BPE 2024 per 100,000 residents. Station count does not measure train frequency or service quality."),
        ],
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "public_services.json").read_text())
    assert len(doc["lenses"]) == 14
    vals = [v for v in doc["lenses"][0]["values"] if v is not None]
    assert len(vals) > 2500 and max(vals) > 0.1
    return [("PASS", f"public_services.json: 14 safety/school/equipment lenses over {len(vals)} cells")]
