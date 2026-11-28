"""Commune-level demographic and business-dynamism lenses."""

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.insets import transform_real_point
from ..core.store import load_interim, write_web
from .connectivity import nearest_land, shape_weights

REQUIRES = ["_world", "fr_boundaries", "fr_insee_stats"]
PRODUCES = ["society.json"]
RAMP = ["#1b1035", "#4b2377", "#9a3b8a", "#e0645e", "#f9b24a", "#fff3a8"]


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def lens(lens_id, name, emoji, unit, fmt, vals, desc):
    return {"id": lens_id, "group": "society", "name": name, "icon": lens_id, "emoji": emoji, "unit": unit,
            "format": fmt, "scale": "linear", "domain": [percentile(vals, 2), percentile(vals, 98)], "ramp": RAMP,
            "higher_is": "neutral", "source": "fr_insee_stats", "description": desc, "values": vals}


def build():
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    stats = load_interim("fr_insee_stats")
    rows = stats["comparateur"]["COM"]
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    acc = defaultdict(lambda: defaultdict(float))
    migration_acc = defaultdict(lambda: defaultdict(float))
    unmatched = 0
    migration_years = range(2018, 2024)
    for c in bounds["communes"]:
        row = rows.get(c["code"])
        if not row or c.get("lon") is None:
            continue
        x, y = proj(*transform_real_point(c["lon"], c["lat"]))
        cell = nearest_land(world, grid, x, y)
        if cell < 0:
            unmatched += 1
            continue
        pop = row.get("POP_2023") or 0
        if pop:
            acc[cell]["pop"] += pop
            acc[cell]["births"] += row.get("NAIS_2023") or 0
            acc[cell]["deaths"] += row.get("DECES_2023") or 0
            acc[cell]["establishments"] += row.get("ETAB_2024") or 0
        migration_keys = [f"NAIS_{y}" for y in migration_years] + [f"DECES_{y}" for y in migration_years]
        if row.get("POP_2017") and row.get("POP_2023") and all(row.get(k) is not None for k in migration_keys):
            a = migration_acc[cell]
            a["pop17"] += row["POP_2017"]
            a["pop23"] += row["POP_2023"]
            a["natural"] += sum(row.get(f"NAIS_{y}", 0) - row.get(f"DECES_{y}", 0) for y in migration_years)

    natural, migration, establishments = [], [], []
    for i in range(grid.size):
        a = acc.get(i)
        natural.append(round((a["births"] - a["deaths"]) / a["pop"], 4) if a and a["pop"] else None)
        establishments.append(round(a["establishments"] * 1000 / a["pop"], 2) if a and a["pop"] else None)
        m = migration_acc.get(i)
        migration.append(round((m["pop23"] - m["pop17"] - m["natural"]) / m["pop17"], 4) if m and m["pop17"] else None)

    # The territory comparator contains commune-level income, poverty and housing counts that
    # the original headline lenses aggregate only to departments. Distribute them over commune
    # polygons, skipping suppressed/missing communes rather than treating them as zero.
    weights_by_commune = shape_weights(world, grid, proj, bounds["communes"])
    detail = defaultdict(lambda: defaultdict(float))
    for c in bounds["communes"]:
        row = rows.get(c["code"])
        weights = weights_by_commune.get(c["code"])
        if not row or not weights:
            continue
        pop = row.get("POP_2023") or 0
        for cell, weight in weights.items():
            a = detail[cell]
            if pop:
                a["pop_weight"] += pop * weight
                if row.get("MED_SL_2023") is not None:
                    a["income_weight"] += pop * weight
                    a["income_sum"] += pop * weight * row["MED_SL_2023"]
                if row.get("PR_MD60_2023") is not None:
                    a["poverty_weight"] += pop * weight
                    a["poverty_sum"] += pop * weight * row["PR_MD60_2023"]
            for numerator, denominator, out_key, den_key in [
                ("RP_PROP_2023", "RP_2023", "owner", "main"),
                ("RSEC_2023", "LOG_2023", "second", "homes"),
                ("LVAC_2023", "LOG_2023", "vacant", "homes"),
            ]:
                if row.get(numerator) is not None and row.get(denominator):
                    a[out_key] += row[numerator] * weight
                    a[den_key] += row[denominator] * weight

    commune_income, commune_poverty, commune_homeownership, commune_second, commune_vacancy = [], [], [], [], []
    for i in range(grid.size):
        a = detail.get(i)
        commune_income.append(round(a["income_sum"] / a["income_weight"]) if a and a["income_weight"] else None)
        commune_poverty.append(round(a["poverty_sum"] / a["poverty_weight"] / 100, 4) if a and a["poverty_weight"] else None)
        commune_homeownership.append(round(a["owner"] / a["main"], 4) if a and a["main"] else None)
        commune_second.append(round(a["second"] / a["homes"], 4) if a and a["homes"] else None)
        commune_vacancy.append(round(a["vacant"] / a["homes"], 4) if a and a["homes"] else None)

    write_web("society.json", {
        "version": 1, "vintage": f"INSEE comparateur de territoires, census {stats['year']} and 2024 establishments",
        "sources": ["fr_insee_stats"], "group": {"id": "society", "name": "Society"}, "unmatched_communes": unmatched,
        "lenses": [
            lens("natural_balance", "Natural population balance", "👶", "births minus deaths / resident / year", "signed", natural,
                 "Births minus deaths in 2023 as a share of residents, with commune vital events summed within each map hex. Negative values mean deaths exceed births before migration."),
            lens("net_migration", "Estimated net migration", "🧭", "population change 2017–2023", "signed", migration,
                 "Approximate net migration 2017–2023: total population change minus summed natural increase, divided by 2017 population. This residual omits statistical adjustments and is sensitive to municipal boundary changes."),
            lens("business_density", "Business establishments", "🏪", "establishments per 1k residents", "float", establishments,
                 "INSEE establishment count in 2024 per 1,000 residents, summed from communes within each map hex. Establishments are local business units, not enterprises or employment."),
            {**lens("commune_income", "Commune median income", "💶", "euros / year", "eur", commune_income,
                 "Commune-level median standard of living in 2023, distributed over commune polygons and population-weighted within each hex. This is a weighted average of commune medians, not a recomputed hex median; suppressed communes and most overseas territories are null."), "group": "prosperity"},
            {**lens("commune_poverty", "Commune poverty", "📉", "share of residents", "pct", commune_poverty,
                 "Commune-level share of residents below 60% of median standard of living in 2023, population-weighted within each hex. Suppressed communes and most overseas territories are null rather than zero."), "group": "prosperity"},
            {**lens("commune_homeownership", "Commune homeownership", "🏠", "share of main homes", "pct", commune_homeownership,
                 "Owner-occupied share of main residences in 2023, using commune-level counts distributed over commune polygons. Unlike the headline department lens, neighboring communes can differ within the same department."), "group": "land"},
            {**lens("commune_second_homes", "Commune second homes", "🏡", "share of dwellings", "pct", commune_second,
                 "Second homes and occasional dwellings as a share of all dwellings in 2023, using commune-level counts distributed over commune polygons."), "group": "land"},
            {**lens("commune_vacancy", "Commune vacant homes", "⬜", "share of dwellings", "pct", commune_vacancy,
                 "Vacant dwellings as a share of all dwellings in 2023, using commune-level counts distributed over commune polygons."), "group": "land"},
        ],
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "society.json").read_text())
    assert len(doc["lenses"]) == 8
    for item in doc["lenses"]:
        vals = [v for v in item["values"] if v is not None]
        assert len(vals) > 2500 and max(vals) > 0
    income = next(l for l in doc["lenses"] if l["id"] == "commune_income")["values"]
    assert len(set(v for v in income if v is not None)) > 500
    mig = [v for v in doc["lenses"][1]["values"] if v is not None]
    assert min(mig) < 0 < max(mig)
    return [("PASS", "society.json: demographic, business-dynamism and commune-detail lenses")]
