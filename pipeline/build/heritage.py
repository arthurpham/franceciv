"""Protected-built-heritage lenses."""

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .connectivity import nearest_land

REQUIRES = ["_world", "fr_boundaries", "fr_heritage"]
PRODUCES = ["heritage.json"]
RAMP = ["#2d2640", "#59466f", "#8a6280", "#bd8076", "#e0ad60"]


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def lens(lens_id, name, emoji, unit, fmt, scale, vals, desc):
    domain_vals = [v for v in vals if v] if scale == "log" else vals
    return {"id": lens_id, "group": "culture_recreation", "name": name, "icon": lens_id, "emoji": emoji,
            "unit": unit, "format": fmt, "scale": scale, "domain": [percentile(domain_vals, 2), percentile(domain_vals, 98)],
            "ramp": RAMP, "higher_is": "neutral", "source": "fr_heritage", "description": desc, "values": vals}


def build():
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    heritage = load_interim("fr_heritage")
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    cell_by_commune = {}
    pop_acc = defaultdict(int)
    for c in bounds["communes"]:
        if c.get("lon") is None:
            continue
        x, y = proj(c["lon"], c["lat"])
        cell = nearest_land(world, grid, x, y)
        if cell >= 0:
            cell_by_commune[c["code"]] = cell
            pop_acc[cell] += c.get("population") or 0
    acc = defaultdict(lambda: [0, 0])
    unmatched = 0
    for code, row in heritage["rows"].items():
        cell = cell_by_commune.get(code)
        if cell is None:
            unmatched += row["total"]
            continue
        acc[cell][0] += row["total"]
        acc[cell][1] += row["classified"]
    access, classified_share = [], []
    for i in range(grid.size):
        pop = pop_acc.get(i, 0)
        total, classified = acc.get(i, [0, 0])
        access.append(round(total * 10_000 / pop, 2) if pop else None)
        classified_share.append(round(classified / total, 4) if total else None)
    write_web("heritage.json", {
        "version": 1, "vintage": "Mérimée protected buildings, current ministry export", "sources": ["fr_heritage"],
        "group": {"id": "culture_recreation", "name": "Culture & recreation"}, "unmatched_buildings": unmatched,
        "lenses": [
            lens("heritage_sites", "Protected heritage", "🏛️", "buildings / 10k residents", "float", "log", access, "Buildings protected as Monuments historiques per 10,000 residents. Commune counts are aggregated by map hex; municipal mergers are resolved to current communes where unambiguous."),
            lens("classified_heritage", "Classified share", "🏰", "share of protected buildings", "pct", "linear", classified_share, "Share of protected heritage buildings whose protection text includes classement, the strongest Monument historique protection level. Null where no protected building is recorded in the hex."),
        ],
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "heritage.json").read_text())
    assert len(doc["lenses"]) == 2 and doc["unmatched_buildings"] < 5000
    vals = [v for v in doc["lenses"][0]["values"] if v is not None]
    share = [v for v in doc["lenses"][1]["values"] if v is not None]
    assert len(vals) > 2500 and max(vals) > 5 and len(share) > 1500
    return [("PASS", f"heritage.json: protected-heritage lenses over {len(vals)} cells")]
