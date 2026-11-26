"""Protected-nature lens."""

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .world import HEX_RADIUS_KM, hex_lattice

REQUIRES = ["_world", "fr_nature"]
PRODUCES = ["nature.json"]
RAMP = ["#243527", "#41643a", "#6d8d47", "#b6b765", "#e0cf78"]
STEP_KM = 2.0


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def build():
    world = load_interim("_world")
    nature = load_interim("fr_nature")
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    geometries = []
    kinds = []
    for site in nature["sites"]:
        try:
            geom = shape(site["geometry"])
        except Exception:
            continue
        if geom.is_empty:
            continue
        if geom.geom_type not in {"Polygon", "MultiPolygon"}:
            continue
        geometries.append(geom)
        kinds.append(site["kind"])
    tree = STRtree(geometries)
    lattice = hex_lattice(HEX_RADIUS_KM, STEP_KM)
    all_vals, habitat_vals, bird_vals = [], [], []
    for i in range(grid.size):
        if world["owner"][i] < 0:
            all_vals.append(None); habitat_vals.append(None); bird_vals.append(None); continue
        cx, cy = grid.center(*grid.col_row(i))
        total = hit = hab = bird = 0
        for ox, oy in lattice:
            lon, lat = proj.inverse(cx + ox, cy + oy)
            total += 1
            matches = tree.query(Point(lon, lat), predicate="intersects")
            if len(matches):
                hit += 1
                ks = {kinds[int(j)] for j in matches}
                hab += "habitat" in ks
                bird += "birds" in ks
        all_vals.append(round(hit / total, 4) if total else None)
        habitat_vals.append(round(hab / total, 4) if total else None)
        bird_vals.append(round(bird / total, 4) if total else None)

    def lens(lens_id, name, vals, desc):
        return {"id": lens_id, "group": "nature", "name": name, "icon": lens_id, "emoji": "🌿", "unit": "share of hex area",
                "format": "pct", "scale": "linear", "domain": [percentile(vals, 2), percentile(vals, 98)], "ramp": RAMP,
                "higher_is": "neutral", "source": "fr_nature", "description": desc, "values": vals}

    write_web("nature.json", {
        "version": 1, "vintage": "INPN Natura 2000 via API Carto Nature, current export", "sources": ["fr_nature"],
        "group": {"id": "nature", "name": "Protected nature"},
        "lenses": [
            lens("natura2000", "Natura 2000", all_vals, "Share of hex area covered by either Natura 2000 habitat-directive or birds-directive sites, approximated by sampling a 2 km lattice."),
            lens("natura_habitat", "Habitat directive", habitat_vals, "Share of hex area covered by Natura 2000 habitat-directive sites."),
            lens("natura_birds", "Birds directive", bird_vals, "Share of hex area covered by Natura 2000 birds-directive sites."),
        ],
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "nature.json").read_text())
    vals = [v for v in doc["lenses"][0]["values"] if v is not None]
    assert len(doc["lenses"]) == 3 and len(vals) > 2500 and max(vals) > 0.2
    return [("PASS", f"nature.json: 3 Natura 2000 lenses over {len(vals)} cells")]
