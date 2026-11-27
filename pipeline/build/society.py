"""Commune-level demographic and business-dynamism lenses."""

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.insets import transform_real_point
from ..core.store import load_interim, write_web
from .connectivity import nearest_land

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
        ],
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "society.json").read_text())
    assert len(doc["lenses"]) == 3
    for item in doc["lenses"]:
        vals = [v for v in item["values"] if v is not None]
        assert len(vals) > 2500 and max(vals) > 0
    mig = [v for v in doc["lenses"][1]["values"] if v is not None]
    assert min(mig) < 0 < max(mig)
    return [("PASS", "society.json: three demographic and business-dynamism lenses")]
