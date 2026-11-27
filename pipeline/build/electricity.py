"""Electricity-consumption lenses."""

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .connectivity import shape_weights

REQUIRES = ["_world", "fr_electricity", "fr_boundaries"]
PRODUCES = ["electricity.json"]
RAMP = ["#252a3f", "#365070", "#457a76", "#a69b53", "#e1c55e"]
SECTORS = {
    "RESIDENTIEL": ("residential_electricity", "Residential electricity", "🏠", "Residential {year} electricity consumption on the Enedis distribution network per resident."),
    "TERTIAIRE": ("tertiary_electricity", "Tertiary electricity", "🏢", "Tertiary-sector {year} electricity consumption on the Enedis distribution network per resident. Values reflect where economic activity is located, not household use."),
    "INDUSTRIE": ("industrial_electricity", "Industrial electricity", "🏭", "Industrial {year} electricity consumption on the Enedis distribution network per resident. Values reflect where industrial load is located."),
    "AGRICULTURE": ("agricultural_electricity", "Agricultural electricity", "🚜", "Agricultural {year} electricity consumption on the Enedis distribution network per resident. Values reflect where metered agricultural load is located."),
}


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def lens(lens_id, name, emoji, unit, fmt, vals, desc, scale="linear", year="2025"):
    desc = desc.format(year=year)
    return {
        "id": lens_id, "group": "energy_use", "name": name, "icon": lens_id, "emoji": emoji,
        "unit": unit, "format": fmt, "scale": scale,
        "domain": [percentile(vals, 2), percentile(vals, 98)], "ramp": RAMP, "higher_is": "neutral",
        "source": "fr_electricity", "description": desc + " Commune values are distributed approximately over commune polygons at a 1 km lattice, assuming a uniform distribution inside each commune; this is a commune-level approximation, not meter locations. Enedis does not serve Corsica, overseas France and some local-distribution areas.",
        "values": vals,
    }


def parent_code(code):
    if code.startswith("751"):
        return "75056"
    if code.startswith("132") and len(code) == 5:
        return "13055"
    if code.startswith("6938"):
        return "69123"
    return code


def weighted_mean(rows):
    out = []
    size = max(rows, default=-1) + 1
    for i in range(size):
        vals = rows.get(i, [])
        total = sum(w for v, w in vals if v is not None)
        value = sum(v * w for v, w in vals if v is not None) / total if total else None
        out.append(round(value, 4) if value is not None else None)
    return out


def build():
    world = load_interim("_world")
    electricity = load_interim("fr_electricity")
    boundaries = load_interim("fr_boundaries")
    year = electricity.get("year", "2025")
    heating_year = electricity.get("heating_year", "2024")
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])

    population = {c["code"]: c.get("population") or 0 for c in boundaries["communes"]}
    commune_weights = shape_weights(world, grid, proj, boundaries["communes"])

    consumption = defaultdict(float)
    sector_acc = defaultdict(lambda: defaultdict(float))
    category_acc = defaultdict(lambda: defaultdict(float))
    covered_pop = defaultdict(float)
    heat_rows = defaultdict(list)
    sensitive_rows = defaultdict(list)
    matched = set()
    unmatched_mwh = total_mwh = 0.0
    for raw_code, row in electricity["communes"].items():
        code = parent_code(raw_code)
        total_mwh += row.get("consumption_mwh") or 0
        weights = commune_weights.get(code)
        if not weights:
            unmatched_mwh += row.get("consumption_mwh") or 0
            continue
        has_consumption = bool(row.get("sectors"))
        if has_consumption:
            matched.add(raw_code)
        pop = population.get(code) or row.get("source_population") or 0
        for cell, weight in weights.items():
            if has_consumption:
                consumption[cell] += (row.get("consumption_mwh") or 0) * weight
                covered_pop[cell] += pop * weight
                for sector, value in row.get("sectors", {}).items():
                    sector_acc[cell][sector] += (value or 0) * weight
                for category, value in row.get("categories", {}).items():
                    category_acc[cell][category] += (value or 0) * weight
            if pop:
                heat_rows[cell].append((row.get("electric_heating_share"), pop * weight))
                sensitive_rows[cell].append((row.get("heat_sensitive_share"), pop * weight))

    def per_resident(selector):
        vals = []
        for i in range(grid.size):
            pop = covered_pop.get(i, 0)
            vals.append(round(selector(i) / pop, 3) if pop and consumption.get(i) is not None else None)
        return vals

    total_vals = per_resident(lambda i: consumption[i])
    sector_vals = {sector: per_resident(lambda i, s=sector: sector_acc[i][s]) for sector in SECTORS}
    small_business_vals = per_resident(lambda i: category_acc[i]["PRO"])
    residential_share, heat, sensitive = [], [], []
    heat_vals = weighted_mean(heat_rows)
    sensitive_vals = weighted_mean(sensitive_rows)
    for i in range(grid.size):
        total = consumption.get(i, 0)
        residential_share.append(round(sector_acc[i]["RESIDENTIEL"] / total, 4) if total else None)
        heat.append(heat_vals[i] if i < len(heat_vals) else None)
        sensitive.append(sensitive_vals[i] if i < len(sensitive_vals) else None)

    lenses = [lens(
        "electricity_use", "Electricity use", "⚡", "MWh per resident per year", "float", total_vals,
        "Total {year} electricity consumption on the Enedis distribution network per resident. Commune-level totals aggregate residential and economic activity; they are not household-only consumption.", year=year
    )]
    for sector, (lens_id, name, emoji, desc) in SECTORS.items():
        lenses.append(lens(lens_id, name, emoji, "MWh per resident per year", "float", sector_vals[sector], desc, year=year))
    lenses.extend([
        lens("small_business_electricity", "Small-business electricity", "🏪", "MWh per resident per year", "float", small_business_vals,
             year=year, desc="Consumption by small professional customers (Enedis category PRO) per resident in {year}. This customer class cuts across the broad activity-sector lenses and should not be added to them as an additional sector total."),
        lens("residential_electricity_share", "Residential electricity share", "🏘️", "share of electricity consumption", "pct", residential_share,
             year=year, desc="Residential consumption as a share of all {year} electricity consumption in each commune aggregate. High values usually indicate housing-dominated territories; low values often indicate industrial, tertiary or agricultural load."),
        lens("electric_heating_share", "Electric heating", "♨️", "share of primary residences", "pct", heat,
             year=year, desc="Share of primary residences equipped with electric heating in Enedis " + heating_year + " commune residential statistics, population-weighted within map hexes. The {year} rows omit this housing attribute."),
        lens("heat_sensitive_electricity", "Heat-sensitive electricity", "🌡️", "share of residential electricity", "pct", sensitive,
             year=year, desc="Average winter temperature-sensitive share of residential electricity use in Enedis {year} commune statistics, population-weighted within map hexes. It approximates heating sensitivity rather than total energy efficiency."),
    ])
    write_web("electricity.json", {
        "version": 1, "vintage": f"Enedis electricity consumption, {year}; electric heating, {heating_year}", "sources": ["fr_electricity"],
        "group": {"id": "energy_use", "name": "Energy use"},
        "matched_communes": len(matched), "unmatched_consumption_mwh": round(unmatched_mwh, 2),
        "unmatched_consumption_share": round(unmatched_mwh / total_mwh, 5) if total_mwh else None,
        "lenses": lenses,
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "electricity.json").read_text())
    vals = [v for v in doc["lenses"][0]["values"] if v is not None]
    assert len(doc["lenses"]) == 9 and len(vals) > 2500 and 2 < sum(vals) / len(vals) < 12
    assert doc["unmatched_consumption_share"] < 0.05
    assert any((v or 0) > 0.5 for v in doc["lenses"][-2]["values"])
    return [("PASS", f"electricity.json: commune-level consumption, sector and heating lenses over {len(vals)} cells")]
