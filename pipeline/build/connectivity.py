"""Connectivity lens: commune fiber eligibility aggregated to map hexes."""

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web

REQUIRES = ["_world", "fr_boundaries", "fr_broadband", "fr_ev_charging", "fr_mobile_network"]
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
    charging = load_interim("fr_ev_charging")
    mobile = load_interim("fr_mobile_network")
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
    ev_acc = defaultdict(int)
    pop_acc = defaultdict(int)
    for c in bounds["communes"]:
        cell = cell_by_commune.get(c["code"])
        if cell is not None:
            pop_acc[cell] += c.get("population") or 0
    unmatched_ev = 0
    for code, count in charging["rows"].items():
        cell = cell_by_commune.get(code)
        if cell is None:
            unmatched_ev += count
        else:
            ev_acc[cell] += count
    commune_pop = {c["code"]: c.get("population") or 0 for c in bounds["communes"]}
    mobile_ops_pop = defaultdict(float)
    mobile5g_pop = defaultdict(float)
    unmatched_mobile_sites = 0
    for code, row in mobile["rows"].items():
        cell = cell_by_commune.get(code)
        if cell is None:
            unmatched_mobile_sites += row["sites"]
            continue
        pop = commune_pop.get(code, 0)
        mobile_ops_pop[cell] += row["operators4g"] * pop
        if row["has5g"]:
            mobile5g_pop[cell] += pop
    ev_vals = []
    mobile_ops = []
    mobile5g = []
    for i in range(grid.size):
        fiber, premises = acc.get(i, [0, 0])
        vals.append(round(fiber / premises, 4) if premises else None)
        pop = pop_acc.get(i, 0)
        ev_vals.append(round(ev_acc.get(i, 0) * 10_000 / pop, 2) if pop else None)
        mobile_ops.append(round(mobile_ops_pop.get(i, 0) / pop, 2) if pop else None)
        mobile5g.append(round(mobile5g_pop.get(i, 0) / pop, 4) if pop else None)
    lens = {
        "id": "fiber", "group": "connectivity", "name": "Fiber eligibility", "icon": "fiber", "emoji": "🌐",
        "unit": "share of connectable premises", "format": "pct", "scale": "linear",
        "domain": [percentile(vals, 2), percentile(vals, 98)], "ramp": RAMP, "higher_is": "neutral",
        "source": "fr_broadband",
        "description": f"Fiber-to-the-home eligible premises as a share of all connectable premises, ARCEP reference date {broadband['date']}. Commune values are aggregated by map hex.",
        "values": vals,
    }
    ev_lens = {
        "id": "ev_charging", "group": "connectivity", "name": "EV charge points", "icon": "ev_charging", "emoji": "🔌",
        "unit": "charge points / 10k residents", "format": "float", "scale": "log",
        "domain": [max(0.1, percentile(ev_vals, 2)), percentile(ev_vals, 98)], "ramp": RAMP, "higher_is": "neutral",
        "source": "fr_ev_charging",
        "description": "Public electric-vehicle charge points per 10,000 residents from the nightly consolidated national IRVE registry. Commune counts are aggregated by map hex; zero means no published public charge point, not missing data.",
        "values": ev_vals,
    }
    mobile_ops_lens = {
        "id": "mobile_operators", "group": "connectivity", "name": "4G site operators", "icon": "mobile_operators", "emoji": "📶",
        "unit": "operators with 4G sites", "format": "float", "scale": "linear",
        "domain": [0, 5], "ramp": RAMP, "higher_is": "neutral", "source": "fr_mobile_network",
        "description": "Population-weighted number of mobile operators with at least one reported 4G-capable site physically located in each commune, ARCEP 2026 T2. This measures infrastructure presence and operator choice, not theoretical signal coverage.",
        "values": mobile_ops,
    }
    mobile5g_lens = {
        "id": "mobile_5g", "group": "connectivity", "name": "5G site presence", "icon": "mobile_5g", "emoji": "📡",
        "unit": "share of residents", "format": "pct", "scale": "linear",
        "domain": [percentile(mobile5g, 2), percentile(mobile5g, 98)], "ramp": RAMP, "higher_is": "neutral", "source": "fr_mobile_network",
        "description": "Share of residents living in communes with at least one reported 5G-capable operator site, ARCEP 2026 T2. A commune without a local site can still have signal from neighbouring communes, so this is deployment presence rather than coverage.",
        "values": mobile5g,
    }
    write_web("connectivity.json", {
        "version": 1, "vintage": f"ARCEP Ma connexion internet, {broadband['date']} / consolidated IRVE nightly export / ARCEP mobile sites 2026 T2", "sources": ["fr_broadband", "fr_ev_charging", "fr_mobile_network"],
        "group": {"id": "connectivity", "name": "Connectivity"}, "covered_cells": len(acc), "missing_communes": missing, "unmatched_ev_charge_points": unmatched_ev,
        "unmatched_mobile_sites": unmatched_mobile_sites,
        "lenses": [lens, ev_lens, mobile_ops_lens, mobile5g_lens],
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "connectivity.json").read_text())
    assert doc["covered_cells"] > 2500
    vals = [v for v in doc["lenses"][0]["values"] if v is not None]
    assert len(vals) > 2500 and all(0 <= v <= 1 for v in vals)
    ev = [v for v in doc["lenses"][1]["values"] if v is not None]
    assert len(doc["lenses"]) == 4 and len(ev) > 2500 and max(ev) > 5
    mob = [v for v in doc["lenses"][2]["values"] if v is not None]
    fiveg = [v for v in doc["lenses"][3]["values"] if v is not None]
    assert len(mob) > 2500 and max(mob) <= 4 and len(fiveg) > 2500 and all(0 <= v <= 1 for v in fiveg)
    return [("PASS", f"connectivity.json: fiber, EV-charging and mobile lenses over {doc['covered_cells']} cells")]
