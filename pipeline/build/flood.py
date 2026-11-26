"""Physical flood-exposure lens."""

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .world import HEX_RADIUS_KM, WORLDCOVER_STEP_KM, hex_lattice

REQUIRES = ["_world", "fr_flood"]
PRODUCES = ["flood.json"]
RAMP = ["#25313f", "#2f4f68", "#3f7388", "#5d9ca2", "#a5c6b8"]


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def build():
    world = load_interim("_world")
    flood = load_interim("fr_flood")
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    rows = flood["rows"]
    x0, dx, y0, dy, ncols = flood["x0"], flood["dx"], flood["y0"], flood["dy"], flood["cols"]
    lattice = hex_lattice(HEX_RADIUS_KM, WORLDCOVER_STEP_KM)
    vals = []
    for i in range(grid.size):
        if world["owner"][i] < 0:
            vals.append(None); continue
        cx, cy = grid.center(*grid.col_row(i))
        total = cover = 0
        for ox, oy in lattice:
            lon, lat = proj.inverse(cx + ox, cy + oy)
            c, r = round((lon - x0) / dx), round((lat - y0) / dy)
            if not (0 <= c < ncols and 0 <= r < len(rows)):
                continue
            total += 1
            ch = rows[r][c]
            if ch != ".":
                cover += int(ch) / 9
        vals.append(round(cover / total, 4) if total else None)
    write_web("flood.json", {
        "version": 1, "vintage": flood.get("vintage", "TRI flood-risk synthesis, 2020 reporting"), "sources": ["fr_flood"],
        "group": {"id": "hazards", "name": "Hazards"},
        "lenses": [{
            "id": "flood_exposure", "group": "hazards", "name": "River flood exposure", "icon": "flood_exposure", "emoji": "🌊",
            "unit": "share of hex area", "format": "pct", "scale": "linear",
            "domain": [percentile(vals, 2), percentile(vals, 98)], "ramp": RAMP, "higher_is": "worse", "source": "fr_flood",
            "description": "Approximate share of hex area inside rare or millennial river-overflow flood surfaces from the official 2020 TRI synthesis. Values are raster-sampled estimates limited to designated TRI territories, not parcel-level risk determinations.",
            "values": vals,
        }],
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "flood.json").read_text())
    vals = [v for v in doc["lenses"][0]["values"] if v is not None]
    nonzero = [v for v in vals if v]
    assert len(vals) > 2500 and len(nonzero) > 400 and max(vals) > 0.2
    return [("PASS", f"flood.json: physical flood lens over {len(vals)} cells")]
