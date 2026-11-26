"""Agricultural land lenses from detailed CORINE crop classes."""

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .world import HEX_RADIUS_KM, WORLDCOVER_STEP_KM, hex_lattice

REQUIRES = ["_world", "fr_corine"]
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


def lens(lens_id, name, emoji, vals, desc):
    return {"id": lens_id, "group": "agriculture", "name": name, "icon": lens_id, "emoji": emoji,
            "unit": "share of land", "format": "pct", "scale": "linear", "domain": [percentile(vals, 2), percentile(vals, 98)],
            "ramp": RAMP, "higher_is": "neutral", "source": "fr_corine", "description": desc, "values": vals}


def build():
    world = load_interim("_world")
    corine = load_interim("fr_corine")
    vineyards, orchards = shares(world, corine)
    write_web("agriculture.json", {
        "version": 1, "vintage": corine.get("vintage", "CORINE Land Cover 2018"), "sources": ["fr_corine"],
        "group": {"id": "agriculture", "name": "Agriculture"},
        "lenses": [
            lens("vineyards", "Vineyards", "🍇", vineyards, "Share of land classified as vineyards by CORINE Land Cover 2018, sampled on a 1 km lattice inside each hex."),
            lens("orchards", "Orchards & olives", "🫒", orchards, "Share of land classified as fruit-tree or olive plantations by CORINE Land Cover 2018."),
        ],
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "agriculture.json").read_text())
    vals = [v for v in doc["lenses"][0]["values"] if v]
    assert len(doc["lenses"]) == 2 and len(vals) > 100
    return [("PASS", f"agriculture.json: vineyard/orchard lenses, {len(vals)} nonzero vineyard cells")]
