"""Water-service quality, wastewater and circular-economy lenses."""

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .connectivity import shape_weights

REQUIRES = ["_world", "fr_boundaries", "fr_water_services", "fr_water_quality", "fr_circular_economy"]
PRODUCES = ["water_circular.json"]
RAMP = ["#1d2d45", "#27526f", "#2f7d82", "#65aa83", "#c9cf73"]


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


def lens(lens_id, name, emoji, unit, fmt, vals, desc, higher="neutral", scale="linear"):
    return {
        "id": lens_id, "group": "water_circular", "name": name, "icon": lens_id, "emoji": emoji,
        "unit": unit, "format": fmt, "scale": scale,
        "domain": [percentile(vals, 2), percentile(vals, 98)], "ramp": RAMP, "higher_is": higher,
        "source": "fr_water_services" if lens_id.startswith(("drinking_service", "wastewater")) else "fr_water_quality" if lens_id.startswith("drinking_water") else "fr_circular_economy",
        "description": desc,
        "values": vals,
    }


def build():
    world = load_interim("_world")
    boundaries = load_interim("fr_boundaries")
    services = load_interim("fr_water_services")
    quality = load_interim("fr_water_quality")
    circular = load_interim("fr_circular_economy")
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    weights_by_commune = shape_weights(world, grid, proj, boundaries["communes"])
    population = {c["code"]: c.get("population") or 0 for c in boundaries["communes"]}

    # SISPEA departmental service-performance values. They are weighted service averages
    # assigned to the managing body's headquarters department, not exact service territories.
    dep_metrics = defaultdict(dict)
    for dep, row in services["drinking"].items():
        dep_metrics[dep].update({"D102.0": row.get("D102.0"), "P101.1": row.get("P101.1"), "P102.1": row.get("P102.1"), "P104.3": row.get("P104.3")})
    for dep, row in services["wastewater"].items():
        dep_metrics[dep].update({"D204.0": row.get("D204.0"), "P201.1": row.get("P201.1"), "P254.3": row.get("P254.3")})

    def dep_values(code, percent=False):
        vals = []
        for ci in world["county"]:
            dep = world["counties"][ci] if ci >= 0 else None
            value = (dep_metrics.get(dep) or {}).get(code)
            vals.append(round(value / 100, 4) if value is not None and percent else value)
        return vals

    total_pop = defaultdict(float)
    limit_acc = defaultdict(lambda: defaultdict(float))
    full_acc = defaultdict(lambda: defaultdict(float))
    monitoring_acc = defaultdict(float)
    circular_acc = defaultdict(lambda: defaultdict(float))
    matched_quality = matched_circular = 0
    for raw_code, row in quality["communes"].items():
        code = parent_code(raw_code)
        weights = weights_by_commune.get(code)
        if not weights:
            continue
        matched_quality += 1
        for cell, weight in weights.items():
            monitoring_acc[cell] += row["samples"] * weight
            # Apply small-sample suppression at the measured commune level before
            # spatial distribution; fractional polygon weights are not fewer observations.
            if row["limit_valid"] >= 3:
                limit_acc[cell]["ok"] += row["limit_ok"] * weight
                limit_acc[cell]["valid"] += row["limit_valid"] * weight
            if row["samples"] >= 3:
                full_acc[cell]["ok"] += row["full_ok"] * weight
                full_acc[cell]["samples"] += row["samples"] * weight
    for raw_code, count in circular["recycling_centres"].items():
        code = parent_code(raw_code)
        weights = weights_by_commune.get(code)
        if weights:
            matched_circular += 1
            for cell, weight in weights.items():
                circular_acc[cell]["recycling"] += count * weight
    for raw_code, row in circular["services"].items():
        code = parent_code(raw_code)
        weights = weights_by_commune.get(code)
        if not weights:
            continue
        for cell, weight in weights.items():
            circular_acc[cell]["repair"] += (row.get("service_de_reparation") or 0) * weight
            circular_acc[cell]["recyclerie"] += (row.get("recyclerie") or 0) * weight
    for c in boundaries["communes"]:
        pop = c.get("population") or 0
        for cell, weight in weights_by_commune.get(c["code"], {}).items():
            total_pop[cell] += pop * weight

    limit_compliance, full_compliance, monitoring = [], [], []
    recycling_density, repair_density, reuse_density = [], [], []
    for i in range(grid.size):
        valid = limit_acc[i].get("valid", 0)
        samples = full_acc[i].get("samples", 0)
        limit_compliance.append(round(limit_acc[i]["ok"] / valid, 4) if valid else None)
        full_compliance.append(round(full_acc[i]["ok"] / samples, 4) if samples else None)
        pop = total_pop.get(i, 0)
        monitoring.append(round(monitoring_acc[i] * 1000 / pop, 3) if monitoring_acc[i] and pop else None)
        recycling_density.append(round(circular_acc[i].get("recycling", 0) * 100000 / pop, 3) if pop else None)
        repair_density.append(round(circular_acc[i].get("repair", 0) * 100000 / pop, 3) if pop else None)
        reuse_density.append(round(circular_acc[i].get("recyclerie", 0) * 100000 / pop, 3) if pop else None)

    service_note = " Multi-commune service territories are population-weighted and assigned to the managing body's headquarters department, so values are departmental service approximations rather than exact territorial averages."
    commune_note = " Commune values are distributed approximately over commune polygons at a 1 km lattice; this is a spatial approximation, not exact service locations."
    lenses = [
        lens("drinking_service_price", "Drinking-water price", "💧", "€ per m³", "float", dep_values("D102.0"), "Population-weighted SISPEA 2024 drinking-water service price for a reference consumption of 120 m³ per year, including taxes and water-agency fees." + service_note),
        lens("microbial_water_compliance", "Microbial water compliance", "🦠", "share of compliant controls", "pct", dep_values("P101.1", True), "Population-weighted SISPEA 2024 share of drinking-water controls compliant with mandatory microbiological limits." + service_note, higher="better"),
        lens("physicochemical_water_compliance", "Physicochemical water compliance", "🧪", "share of compliant controls", "pct", dep_values("P102.1", True), "Population-weighted SISPEA 2024 share of drinking-water controls compliant with mandatory physicochemical limits such as pesticides, nitrates, chromium and bromate." + service_note, higher="better"),
        lens("water_network_efficiency", "Water-network efficiency", "🕸️", "share of input water billed or used", "pct", dep_values("P104.3", True), "Population-weighted SISPEA 2024 drinking-water distribution efficiency. Higher values mean less leakage relative to water entering the network." + service_note, higher="better"),
        lens("wastewater_service_price", "Wastewater price", "🚰", "€ per m³", "float", dep_values("D204.0"), "Population-weighted SISPEA 2024 collective-wastewater service price per cubic metre." + service_note),
        lens("sewer_connection_rate", "Sewer connection rate", "🔗", "share of connectable residents", "pct", dep_values("P201.1", True), "Population-weighted SISPEA 2024 share of residents in collective-wastewater zones who are connectable and connected to the sewer network." + service_note, higher="better"),
        lens("wastewater_treatment_compliance", "Wastewater treatment compliance", "🏭", "share of compliant load", "pct", dep_values("P254.3", True), "Population-weighted SISPEA 2024 compliant share of 24-hour treatment-performance balances for plants above 2,000 population-equivalent, weighted by incoming organic load." + service_note, higher="better"),
        lens("drinking_water_limit_compliance", "Drinking-water limit compliance", "✅", "share of valid samples", "pct", limit_compliance, "Share of 2025 Hub'eau drinking-water samples compliant with mandatory bacteriological and physicochemical limits. Communes with fewer than three routine Escherichia coli control rows are treated as missing rather than assigning a noisy zero or perfect score." + commune_note, higher="better"),
        lens("drinking_water_full_compliance", "Fully compliant water samples", "🥛", "share of samples", "pct", full_compliance, "Share of 2025 Hub'eau drinking-water samples whose whole multi-parameter regulatory conclusion was compliant with every measured requirement, including quality references as well as mandatory limits. Communes with fewer than three control rows are treated as missing." + commune_note, higher="better"),
        lens("drinking_water_monitoring", "Water-quality monitoring", "🔬", "samples per 1,000 residents per year", "float", monitoring, "Routine 2025 drinking-water control samples per 1,000 residents. This measures monitoring intensity, not water quality itself." + commune_note),
        lens("recycling_center_density", "Recycling-centre access", "♻️", "centres per 100k residents", "float", recycling_density, "Current ADEME SINOE recycling centres accepting household and similar waste per 100,000 residents. Counts are distributed approximately from commune polygons at a 1 km lattice." + commune_note),
        lens("repair_service_density", "Repair-service access", "🛠️", "actors per 100k residents", "float", repair_density, "Distinct ADEME circular-economy actors offering repair services per 100,000 residents. The composite database includes contributed entries, so density is observed service availability rather than a complete business registry." + commune_note),
        lens("reuse_infrastructure_density", "Reuse-infrastructure access", "🔄", "recycleries per 100k residents", "float", reuse_density, "Distinct ADEME circular-economy actors classified as recycleries per 100,000 residents. Recycleries collect, repair, reuse and resell objects; the composite database is an observed-availability indicator rather than a statutory registry." + commune_note),
    ]
    write_web("water_circular.json", {
        "version": 1,
        "vintage": f"SISPEA 2024; Hub'eau {quality.get('year')}; ADEME circular infrastructure {circular.get('year')}",
        "sources": ["fr_water_services", "fr_water_quality", "fr_circular_economy"],
        "group": {"id": "water_circular", "name": "Water & circular economy"},
        "matched_quality_communes": matched_quality,
        "matched_recycling_communes": matched_circular,
        "quality_samples": quality.get("samples"),
        "lenses": lenses,
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "water_circular.json").read_text())
    assert len(doc["lenses"]) == 13 and doc["quality_samples"] > 200000
    vals = [v for v in doc["lenses"][7]["values"] if v is not None]
    assert len(vals) > 2500 and 0.8 < sum(vals) / len(vals) <= 1
    return [("PASS", f"water_circular.json: water and circular-economy lenses over {len(vals)} cells")]
