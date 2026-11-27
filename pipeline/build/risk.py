"""Natural-risk zoning lenses sampled from official Géorisques rasters."""

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .world import HEX_RADIUS_KM, WORLDCOVER_STEP_KM, hex_lattice

REQUIRES = ["_world", "fr_risk_zones"]
PRODUCES = ["risk.json"]
RAMP = ["#26324a", "#5a5872", "#8e6a63", "#c77948", "#e0a13f"]


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def sample_layer(world, grid, proj, raster):
    rows = raster["rows"]
    x0, dx, y0, dy, ncols = raster["x0"], raster["dx"], raster["y0"], raster["dy"], raster["cols"]
    lattice = hex_lattice(HEX_RADIUS_KM, WORLDCOVER_STEP_KM)
    vals = []
    for i in range(grid.size):
        if world["owner"][i] < 0:
            vals.append(None); continue
        cx, cy = grid.center(*grid.col_row(i))
        total = acc = 0.0
        for ox, oy in lattice:
            lon, lat = proj.inverse(cx + ox, cy + oy)
            c, r = round((lon - x0) / dx), round((lat - y0) / dy)
            if not (0 <= c < ncols and 0 <= r < len(rows)):
                continue
            total += 1
            ch = rows[r][c]
            if ch != ".":
                acc += int(ch) / 9
        vals.append(round(acc / total, 4) if total else None)
    return vals


def lens(lens_id, name, emoji, vals, desc):
    return {"id": lens_id, "group": "hazards", "name": name, "icon": lens_id, "emoji": emoji,
            "unit": "index (0-1)", "format": "float", "scale": "linear",
            "domain": [percentile(vals, 2), percentile(vals, 98)], "ramp": RAMP, "higher_is": "worse",
            "source": "fr_risk_zones", "description": desc, "values": vals}


def build():
    world = load_interim("_world")
    risk = load_interim("fr_risk_zones")
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    raster = {k: risk[k] for k in ["x0", "dx", "y0", "dy", "cols"]}
    vals = {}
    for key in ["clay", "seismic", "radon"]:
        vals[key] = sample_layer(world, grid, proj, raster | {"rows": risk["layers"][key]["rows"]})
    write_web("risk.json", {
        "version": 1, "vintage": risk.get("vintage", "Géorisques/BRGM risk zoning"), "sources": ["fr_risk_zones"],
        "group": {"id": "hazards", "name": "Hazards"},
        "lenses": [
            lens("clay_shrink_swell", "Clay shrink-swell", "🏚️", vals["clay"], "Area-weighted clay shrink-swell exposure index from the official Géorisques/BRGM zoning raster. Low, medium and high classes are weighted ⅓, ⅔ and 1; coverage is metropolitan France outside Paris and values are hex-scale estimates."),
            lens("seismic_zone", "Seismic zoning", "🫨", vals["seismic"], "Area-weighted seismic-zone index from the official French zoning raster. Zones 1–5 are weighted 0.2–1, so values represent average zoning intensity rather than earthquake probability or expected damage."),
            lens("radon_potential", "Radon potential", "☢️", vals["radon"], "Population-independent commune radon-potential index from Géorisques/BRGM. Low, moderate and high commune classes are weighted ⅓, ⅔ and 1; values are not indoor measurements."),
        ],
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "risk.json").read_text())
    assert len(doc["lenses"]) == 3
    clay = [v for v in doc["lenses"][0]["values"] if v is not None]
    seismic = [v for v in doc["lenses"][1]["values"] if v is not None]
    radon = [v for v in doc["lenses"][2]["values"] if v is not None]
    assert len(clay) > 2500 and len([v for v in clay if v]) > 500
    assert len(seismic) > 2500 and len(radon) > 2500 and max(seismic) > 0.3 and max(radon) > 0.3
    return [("PASS", f"risk.json: 3 natural-risk lenses over {len(clay)} cells")]
