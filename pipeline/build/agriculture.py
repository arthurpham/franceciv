"""Agricultural land and commune farm-structure lenses."""

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .connectivity import nearest_land
from .world import HEX_RADIUS_KM, WORLDCOVER_STEP_KM, hex_lattice

REQUIRES = ["_world", "fr_corine", "fr_boundaries", "fr_agreste"]
PRODUCES = ["agriculture.json"]

RAMP = ["#27351f", "#526f34", "#8fa24b", "#d2bd65", "#f3df8e"]


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def shares(world, corine):
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    rows = corine["crop_detail_rows"]
    x0, dx, y0, dy, ncols = corine["x0"], corine["dx"], corine["y0"], corine["dy"], corine["cols"]
    lattice = hex_lattice(HEX_RADIUS_KM, WORLDCOVER_STEP_KM)
    vineyards, orchards = [], []
    for i in range(grid.size):
        if world["owner"][i] < 0:
            vineyards.append(None); orchards.append(None); continue
        cx, cy = grid.center(*grid.col_row(i))
        land = vine = orch = 0
        for ox, oy in lattice:
            lon, lat = proj.inverse(cx + ox, cy + oy)
            c, r = round((lon - x0) / dx), round((lat - y0) / dy)
            if not (0 <= c < ncols and 0 <= r < len(rows)):
                continue
            base = corine["rows"][r][c]
            if base in {".", "w"}:
                continue
            land += 1
            ch = rows[r][c]
            vine += ch == "v"
            orch += ch == "o"
        vineyards.append(round(vine / land, 4) if land else None)
        orchards.append(round(orch / land, 4) if land else None)
    return vineyards, orchards


def agreste_shares(world, bounds, agreste):
    """Aggregate published commune farm counts/areas to hexes by commune centroid.

    Blank census cells conflate zero and statistical suppression. They are therefore omitted
    from both numerator and denominator rather than zero-filled.
    """
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    cell_by_commune = {}
    for c in bounds["communes"]:
        if c.get("lon") is None or c.get("lat") is None:
            continue
        x, y = proj(c["lon"], c["lat"])
        cell = nearest_land(world, grid, x, y)
        if cell >= 0:
            cell_by_commune[c["code"]] = cell
    commune = {c["code"]: c for c in bounds["communes"]}
    farm_acc = defaultdict(lambda: [0.0, 0.0])  # published farms, surface of published communes (ha)
    size_acc = defaultdict(lambda: [0.0, 0.0])  # utilised agricultural area, farms
    missing = 0
    for code, row in agreste["rows"].items():
        cell = cell_by_commune.get(code)
        c = commune.get(code)
        if cell is None or c is None:
            missing += 1
            continue
        surface = c.get("surface_ha") or 0
        farms = row.get("farms")
        sau = row.get("agricultural_area_ha")
        if farms is not None and surface:
            farm_acc[cell][0] += farms
            farm_acc[cell][1] += surface
        if farms and sau is not None:
            size_acc[cell][0] += sau
            size_acc[cell][1] += farms
    density, average_size = [], []
    for i in range(grid.size):
        if world["owner"][i] < 0:
            density.append(None); average_size.append(None); continue
        farms, surface = farm_acc.get(i, [0, 0])
        sau, size_farms = size_acc.get(i, [0, 0])
        density.append(round(farms * 10_000 / surface, 2) if surface else None)
        average_size.append(round(sau / size_farms, 2) if size_farms else None)
    return density, average_size, len(farm_acc), missing


def lens(lens_id, name, emoji, unit, fmt, scale, vals, source, desc):
    return {"id": lens_id, "group": "agriculture", "name": name, "icon": lens_id, "emoji": emoji,
            "unit": unit, "format": fmt, "scale": scale, "domain": [percentile(vals, 2), percentile(vals, 98)],
            "ramp": RAMP, "higher_is": "neutral", "source": source, "description": desc, "values": vals}


def build():
    world = load_interim("_world")
    corine = load_interim("fr_corine")
    bounds = load_interim("fr_boundaries")
    agreste = load_interim("fr_agreste")
    vineyards, orchards = shares(world, corine)
    farm_density, average_size, covered_cells, missing = agreste_shares(world, bounds, agreste)
    write_web("agriculture.json", {
        "version": 1,
        "vintage": f"{corine.get('vintage', 'CORINE Land Cover 2018')} / Agreste agricultural census 2020, ANCT communal geography 2026",
        "sources": ["fr_corine", "fr_agreste"],
        "group": {"id": "agriculture", "name": "Agriculture"},
        "agreste_covered_cells": covered_cells,
        "agreste_unmatched_communes": missing,
        "agreste_blank_communes": agreste["suppressed_communes"],
        "lenses": [
            lens("vineyards", "Vineyards", "🍇", "share of land", "pct", "linear", vineyards, "fr_corine", "Share of land classified as vineyards by CORINE Land Cover 2018, sampled on a 1 km lattice inside each hex."),
            lens("orchards", "Orchards & olives", "🫒", "share of land", "pct", "linear", orchards, "fr_corine", "Share of land classified as fruit-tree or olive plantations by CORINE Land Cover 2018."),
            lens("farm_density", "Farm density", "🚜", "farms / 100 km²", "float", "log", farm_density, "fr_agreste", "Agreste 2020 farm count per 100 km², aggregated from communes to hexes. Blank commune cells mean no farm or statistical suppression; those communes are omitted from both numerator and denominator rather than zero-filled."),
            lens("average_farm_size", "Average farm size", "🌾", "hectares / farm", "float", "log", average_size, "fr_agreste", "Utilised agricultural area per farm in the 2020 agricultural census. Areas are assigned to the headquarters commune and may include land worked in other communes, so this is farm structure rather than a physical parcel map."),
        ],
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "agriculture.json").read_text())
    vals = [v for v in doc["lenses"][0]["values"] if v]
    farms = [v for v in next(l["values"] for l in doc["lenses"] if l["id"] == "farm_density") if v]
    assert len(doc["lenses"]) == 4 and len(vals) > 100 and len(farms) > 2500
    return [("PASS", f"agriculture.json: vineyard/orchard and Agreste lenses, {len(vals)} nonzero vineyard cells, {len(farms)} farm-density cells")]
