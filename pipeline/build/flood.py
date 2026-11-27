"""Physical flood-exposure lenses."""

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


def sample_layer(world, grid, proj, flood, rows):
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
    return vals


def lens(lens_id, name, vals, description):
    return {
        "id": lens_id, "group": "hazards", "name": name, "icon": lens_id,
        "emoji": "🌊", "unit": "share of hex area", "format": "pct", "scale": "linear",
        "domain": [0, percentile([v for v in vals if v], 98)], "ramp": RAMP,
        "higher_is": "worse", "source": "fr_flood", "description": description, "values": vals,
    }


def build():
    world = load_interim("_world")
    flood = load_interim("fr_flood")
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    river = sample_layer(world, grid, proj, flood, flood["layers"]["river_overflow"])
    coastal = sample_layer(world, grid, proj, flood, flood["layers"]["coastal_submersion"])
    write_web("flood.json", {
        "version": 1, "vintage": flood.get("vintage", "TRI flood-risk synthesis, 2020 reporting"), "sources": ["fr_flood"],
        "group": {"id": "hazards", "name": "Hazards"},
        "lenses": [
            lens("flood_exposure", "River flood exposure", river, "Approximate share of hex area inside rare or millennial river-overflow flood surfaces from the official 2020 TRI synthesis. Values are raster-sampled estimates limited to designated TRI territories, not parcel-level risk determinations."),
            lens("coastal_submersion", "Coastal submersion exposure", coastal, "Approximate share of hex area inside rare or millennial marine-submersion flood surfaces from the official 2020 TRI synthesis. Values are raster-sampled estimates limited to designated TRI territories; they do not include erosion, groundwater rise, drainage failure or parcel-level protection standards."),
        ],
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "flood.json").read_text())
    assert len(doc["lenses"]) == 2
    vals = [v for v in doc["lenses"][0]["values"] if v is not None]
    coastal = [v for v in doc["lenses"][1]["values"] if v is not None]
    nonzero = [v for v in vals if v]
    coast_nonzero = [v for v in coastal if v]
    assert len(vals) > 2500 and len(nonzero) > 400 and max(vals) > 0.2
    assert len(coastal) > 2500 and len(coast_nonzero) > 70 and max(coastal) > 0.1
    return [("PASS", f"flood.json: river and coastal flood lenses over {len(vals)} cells")]
