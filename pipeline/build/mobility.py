"""National-road traffic lenses."""

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .infrastructure import nearest_land, projected_samples

REQUIRES = ["_world", "fr_road_traffic"]
PRODUCES = ["mobility.json"]
RAMP = ["#26324a", "#465f78", "#718a69", "#b9a95c", "#e0bd55"]


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def lens(lens_id, name, emoji, unit, fmt, scale, vals, desc):
    positive = [v for v in vals if v]
    return {"id": lens_id, "group": "mobility", "name": name, "icon": lens_id, "emoji": emoji, "unit": unit, "format": fmt, "scale": scale,
            "domain": [percentile(positive, 5), percentile(positive, 95)], "ramp": RAMP, "higher_is": "neutral", "source": "fr_road_traffic", "description": desc, "values": vals}


def build():
    world = load_interim("_world")
    traffic = load_interim("fr_road_traffic")
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    acc = defaultdict(lambda: {"n": 0.0, "tmja": 0.0, "heavy": 0.0, "vehicles": 0.0})
    unmatched = 0
    for row in traffic["rows"]:
        cells = []
        for x, y in projected_samples(row["line"], proj, 0.8):
            cell = nearest_land(world, grid, x, y)
            if cell < 0:
                unmatched += 1
                continue
            if not cells or cells[-1] != cell:
                cells.append(cell)
        weight = max(1, len(cells))
        for cell in cells:
            a = acc[cell]
            a["n"] += 1
            a["tmja"] += row["tmja"]
            a["heavy"] += row["tmja"] * row["heavy_share"] if row.get("heavy_share") is not None else 0
            a["vehicles"] += row["tmja"] if row.get("heavy_share") is not None else 0
    volume, heavy = [], []
    for i in range(grid.size):
        a = acc.get(i)
        if a and a["n"]:
            volume.append(round(a["tmja"] / a["n"]))
            heavy.append(round(a["heavy"] / a["vehicles"], 4) if a["vehicles"] else None)
        else:
            volume.append(None); heavy.append(None)
    road_cells = [i for i, v in enumerate(volume) if v is not None]
    road_xy = [grid.center(*grid.col_row(i)) for i in road_cells]
    distance = []
    for i in range(grid.size):
        owner = world["owner"][i]
        ci = world["county"][i]
        dep = world["counties"][ci] if 0 <= ci < len(world["counties"]) else ""
        metropolitan = owner >= 0 and len(str(dep)) == 2 and str(dep) not in {"2A", "2B"}
        if owner < 0 or not metropolitan or not road_xy:
            distance.append(None)
            continue
        x, y = grid.center(*grid.col_row(i))
        distance.append(round(min((x - rx) ** 2 + (y - ry) ** 2 for rx, ry in road_xy) ** 0.5, 1))
    write_web("mobility.json", {
        "version": 1, "vintage": "TMJA national road network 2024 reference year; section measurement years vary", "sources": ["fr_road_traffic"], "traffic_sections": len(traffic["rows"]), "unmatched_samples": unmatched,
        "group": {"id": "mobility", "name": "Road mobility"},
        "lenses": [
            lens("road_traffic", "Road traffic", "🚗", "vehicles / day", "int", "log", volume, "Length-weighted average annual daily traffic on national-road sections, sampled into map hexes. Coverage is the national road network only; departmental and municipal roads are excluded. Section measurement years can precede the 2024 reference year."),
            lens("heavy_vehicle_share", "Heavy vehicle share", "🚛", "share of vehicles", "pct", "linear", heavy, "Heavy vehicles as a traffic-weighted share of annual average daily vehicles on national-road sections. Coverage excludes departmental and municipal roads; the share is not total freight volume."),
            lens("national_road_distance", "Distance to national roads", "🛣️", "km", "float", "linear", distance, "Straight-line distance from each metropolitan hex to the nearest national-road traffic-measurement section. This derived accessibility measure covers mainland France even where traffic itself is only measured on the national network; Corsica and overseas territories are null because the source does not measure their networks."),
        ],
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "mobility.json").read_text())
    vals = [v for v in doc["lenses"][0]["values"] if v]
    hv = [v for v in doc["lenses"][1]["values"] if v]
    assert len(vals) > 250 and max(vals) > 50_000 and len(hv) > 250 and max(hv) < 1
    dist = next(l for l in doc["lenses"] if l["id"] == "national_road_distance")["values"]
    measured = [v for v in dist if v is not None]
    assert len(measured) > 2500 and min(measured) == 0 and max(measured) < 300
    return [("PASS", f"mobility.json: national-road traffic lenses over {len(vals)} cells and access distances over {len(measured)} cells")]
