"""Connectivity lens: commune fiber eligibility aggregated to map hexes."""

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web

REQUIRES = ["_world", "fr_boundaries", "fr_broadband"]
PRODUCES = ["connectivity.json"]

RAMP = ["#30223d", "#564f86", "#4f87a8", "#62b58f", "#d8e982"]


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def nearest_land(world, grid, x, y):
    exact = grid.cell_at(x, y)
    if exact >= 0 and world["owner"][exact] >= 0:
        return exact
    if exact >= 0:
        seen = {exact}; frontier = [exact]
        for _ in range(10):
            nxt = []
            for cell in frontier:
                for n in grid.neighbours(cell):
                    if n in seen: continue
                    if world["owner"][n] >= 0: return n
                    seen.add(n); nxt.append(n)
            frontier = nxt
            if not frontier: break
    return exact


def build():
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    broadband = load_interim("fr_broadband")
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    cell_by_commune = {}
    for c in bounds["communes"]:
        if c.get("lon") is None: continue
        x, y = proj(c["lon"], c["lat"])
        cell = nearest_land(world, grid, x, y)
        if cell >= 0: cell_by_commune[c["code"]] = cell
    acc = defaultdict(lambda: [0, 0])
    missing = 0
    for r in broadband["rows"]:
        cell = cell_by_commune.get(r["code"])
        if cell is None:
            missing += 1; continue
        acc[cell][0] += r["fiber"]; acc[cell][1] += r["premises"]
    vals = []
    for i in range(grid.size):
        fiber, premises = acc.get(i, [0, 0])
        vals.append(round(fiber / premises, 4) if premises else None)
    lens = {
        "id": "fiber", "group": "connectivity", "name": "Fiber eligibility", "icon": "fiber", "emoji": "🌐",
        "unit": "share of connectable premises", "format": "pct", "scale": "linear",
        "domain": [percentile(vals, 2), percentile(vals, 98)], "ramp": RAMP, "higher_is": "neutral",
        "source": "fr_broadband",
        "description": f"Fiber-to-the-home eligible premises as a share of all connectable premises, ARCEP reference date {broadband['date']}. Commune values are aggregated by map hex.",
        "values": vals,
    }
    write_web("connectivity.json", {
        "version": 1, "vintage": f"ARCEP Ma connexion internet, {broadband['date']}", "sources": ["fr_broadband"],
        "group": {"id": "connectivity", "name": "Connectivity"}, "covered_cells": len(acc), "missing_communes": missing,
        "lenses": [lens],
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "connectivity.json").read_text())
    assert doc["covered_cells"] > 2500
    vals = [v for v in doc["lenses"][0]["values"] if v is not None]
    assert len(vals) > 2500 and all(0 <= v <= 1 for v in vals)
    return [("PASS", f"connectivity.json: fiber lens over {doc['covered_cells']} cells")]
