"""Brownfield-inventory density lenses."""

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.insets import transform_real_point
from ..core.store import load_interim, load_interim_payload, write_web
from .connectivity import nearest_land
from .time_dimension import land_area_by_cell

REQUIRES = ["_world", "fr_brownfields"]
PRODUCES = ["brownfields.json"]
RAMP = ["#2b2a22", "#55513d", "#756f4a", "#a1844f", "#c9793d"]


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def positive_domain(vals):
    positive = [v for v in vals if v]
    return [0, percentile(positive, 98) or max(positive or [0])]


def lens(lens_id, name, emoji, unit, fmt, vals, desc):
    return {"id": lens_id, "group": "land", "name": name, "icon": lens_id, "emoji": emoji,
            "unit": unit, "format": fmt, "scale": "linear", "domain": positive_domain(vals),
            "ramp": RAMP, "higher_is": "neutral", "source": "fr_brownfields", "description": desc, "values": vals}


def build():
    world = load_interim("_world")
    brownfields = load_interim("fr_brownfields")
    brownfield_vintage = load_interim_payload("fr_brownfields")["vintage"]
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    real_land_area = land_area_by_cell(world, grid)
    sites = defaultdict(float)
    surface = defaultdict(float)
    vacant_surface = defaultdict(float)
    unmatched = 0
    for row in brownfields["rows"]:
        map_x, map_y = proj(*transform_real_point(row["lon"], row["lat"]))
        cell = nearest_land(world, grid, map_x, map_y)
        if cell < 0 or world["owner"][cell] < 0:
            unmatched += 1
            continue
        sites[cell] += 1
        area = row.get("surface_m2") or 0
        surface[cell] += area
        if "sans projet" in row.get("status", ""):
            vacant_surface[cell] += area

    density, land_share, no_project_share = [], [], []
    for i in range(grid.size):
        land = real_land_area[i]
        if world["owner"][i] < 0 or not land:
            density.append(None); land_share.append(None); no_project_share.append(None)
            continue
        density.append(round(sites[i] * 100 / land, 3))
        land_share.append(round(surface[i] / 1e6 / land, 6))
        no_project_share.append(round(vacant_surface[i] / 1e6 / land, 6))

    write_web("brownfields.json", {
        "version": 1,
        "vintage": brownfield_vintage,
        "sources": ["fr_brownfields"],
        "group": {"id": "land", "name": "Land"},
        "inventory_rows": len(brownfields["rows"]),
        "unmatched_rows": unmatched,
        "lenses": [
            lens("brownfield_sites", "Brownfield sites", "🏚️", "sites / 100 km²", "float", density, "Cartofriches brownfield inventory sites per 100 km². Coverage comes from heterogeneous local inventories, so low values may reflect missing inventories rather than a true absence of brownfields."),
            lens("brownfield_land", "Brownfield land", "🧱", "share of land", "pct", land_share, "Cartofriches brownfield-site cadastral surface as a share of land. Inventory surfaces can overlap or include very large industrial estates, so local shares can exceed parcel-scale intuition and are not a complete national brownfield-cadastre measurement."),
            lens("brownfield_without_project", "Brownfields without projects", "♻️", "share of land", "pct", no_project_share, "Cartofriches brownfield-site surface whose inventory status is 'friche sans projet', as a share of land. This reuse-potential indicator depends on locally reported project status."),
        ],
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "brownfields.json").read_text())
    vals = [v for l in doc["lenses"] for v in l["values"] if v]
    assert len(doc["lenses"]) == 3 and len(vals) > 500 and doc["inventory_rows"] > 25_000
    return [("PASS", f"brownfields.json: {doc['inventory_rows']} inventory rows across {len(vals)} nonzero lens cells")]
