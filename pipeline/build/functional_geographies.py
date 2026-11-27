"""First-class bassin-de-vie and zone-d'emploi search/statistical rows."""

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.insets import transform_real_point
from ..core.store import load_interim, write_web

REQUIRES = ["_world", "fr_boundaries", "fr_functional_geographies", "fr_housing_history", "fr_migration"]
PRODUCES = ["living_basins.json", "employment_zones.json"]
COLUMNS = ["code", "name", "population", "x", "y", "departments", "commune_count", "density", "home_price", "annual_sales", "mobility", "outside_migration"]


def parent_code(code):
    if code.startswith("751"):
        return "75056"
    if code.startswith("132") and len(code) == 5:
        return "13055"
    if code.startswith("6938"):
        return "69123"
    return code


def aggregate_group(communes, key, refs, dep_name, proj, housing, migration):
    groups = defaultdict(list)
    for c in communes:
        code = key(c)
        if code:
            groups[code].append(c)
    rows = []
    matched = 0
    for code, ms in sorted(groups.items()):
        ref = refs.get(code) or {"name": code}
        pop = sum(c.get("population") or 0 for c in ms)
        area = sum((c.get("surface_ha") or 0) / 100 for c in ms)
        if not pop:
            continue
        matched += len(ms)
        x0 = sum(c["lon"] * (c.get("population") or 0) for c in ms) / pop
        y0 = sum(c["lat"] * (c.get("population") or 0) for c in ms) / pop
        x, y = proj(*transform_real_point(x0, y0))
        price_num = sales = 0.0
        mob_num = out_num = mob_den = 0.0
        for c in ms:
            h = housing.get(parent_code(c["code"]), {}).get("2025", {})
            if h.get("price") and h.get("sales"):
                price_num += h["price"] * h["sales"]
                sales += h["sales"]
            m = migration.get(parent_code(c["code"]), {}).get("2023", {})
            if m.get("total"):
                mob_num += m.get("other_commune", 0)
                out_num += m.get("outside_department", 0)
                mob_den += m["total"]
        rows.append([
            code, ref.get("name") or code, round(pop), round(x, 1), round(y, 1),
            ", ".join(sorted({dep_name.get(c["department"], c["department"]) for c in ms})), len(ms),
            round(pop / area, 1) if area else None,
            round(price_num / sales) if sales else None, round(sales),
            round(mob_num / mob_den, 4) if mob_den else None,
            round(out_num / mob_den, 4) if mob_den else None,
        ])
    return rows, matched


def build():
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    geo = load_interim("fr_functional_geographies")
    housing = load_interim("fr_housing_history")["communes"]
    migration = load_interim("fr_migration")["communes"]
    proj = MapProjection(**world["projection"])
    dep_name = {d["geoid"]: d["name"] for d in bounds["counties"]}
    commune_geo = geo["communes"]

    bv_rows, bv_matched = aggregate_group(bounds["communes"], lambda c: commune_geo.get(c["code"], {}).get("bassin"), geo["bassins"], dep_name, proj, housing, migration)
    ze_rows, ze_matched = aggregate_group(bounds["communes"], lambda c: commune_geo.get(c["code"], {}).get("zone"), geo["zones"], dep_name, proj, housing, migration)
    common = {
        "version": 1,
        "columns": COLUMNS,
        "sources": ["fr_functional_geographies", "fr_boundaries", "fr_housing_history", "fr_migration"],
        "vintage": "INSEE functional geographies at 2025-01-01; populations from current commune boundaries; DVF/Terralyse 2025; census migration 2023",
    }
    write_web("living_basins.json", {**common, "kind": "bassin_de_vie", "geographies": bv_rows, "matched_communes": bv_matched})
    write_web("employment_zones.json", {**common, "kind": "zone_emploi", "geographies": ze_rows, "matched_communes": ze_matched})


def check(web_dir):
    import json
    bv = json.loads((web_dir / "living_basins.json").read_text())
    ze = json.loads((web_dir / "employment_zones.json").read_text())
    assert len(bv["geographies"]) > 1600 and len(ze["geographies"]) > 280
    assert bv["matched_communes"] > 34000 and ze["matched_communes"] > 34000
    assert all(len(r) == len(bv["columns"]) for r in bv["geographies"] + ze["geographies"])
    return [("PASS", f"functional geographies: {len(bv['geographies'])} bassins de vie and {len(ze['geographies'])} zones d'emploi")]
