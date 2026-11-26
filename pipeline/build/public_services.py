"""Crime and school-access lenses."""

from ..core.store import load_interim, write_web

REQUIRES = ["_world", "fr_crime", "fr_schools", "fr_boundaries"]
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

    write_web("public_services.json", {
        "version": 1, "vintage": f"Interior Ministry crime {year}; current school directory", "sources": ["fr_crime", "fr_schools"],
        "group": {"id": "public_services", "name": "Safety & schools"},
        "lenses": [
            lens("burglary", "Burglaries", "🏠", "per 100 residents / yr", dep_values(world, burglary), "fr_crime", f"Recorded home burglaries per 100 residents in {year}. Police/gendarmerie recording and reporting propensity vary by territory."),
            lens("violence", "Physical violence", "🛡️", "per 100 residents / yr", dep_values(world, violence), "fr_crime", f"Recorded non-domestic physical violence per 100 residents in {year}. This is recorded crime, not victimization prevalence."),
            lens("primary_schools", "Primary schools", "🏫", "schools per 10k residents", dep_values(world, primary), "fr_schools", "Open schools classified as Ecole in the current Ministry directory, per 10,000 department residents."),
            lens("secondary_schools", "Collèges & lycées", "🎓", "schools per 10k residents", dep_values(world, secondary), "fr_schools", "Open Collège and Lycée establishments in the current Ministry directory, per 10,000 department residents."),
        ],
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "public_services.json").read_text())
    assert len(doc["lenses"]) == 4
    vals = [v for v in doc["lenses"][0]["values"] if v is not None]
    assert len(vals) > 2500 and max(vals) > 0.1
    return [("PASS", f"public_services.json: 4 safety/school lenses over {len(vals)} cells")]
