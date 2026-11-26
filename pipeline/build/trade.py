"""French region-to-region freight routes from SDES goods-flow data."""

from __future__ import annotations

import heapq
import json
import math
from collections import Counter, defaultdict

from ..core.hexgrid import HexGrid
from ..core.geo import MapProjection
from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web

REQUIRES = ["_world", "fr_boundaries", "fr_freight", "infrastructure.json", "states.json", "cities.json"]
PRODUCES = ["trade.json"]

MODES = [
    {"id": "truck", "name": "Road"},
    {"id": "rail", "name": "Rail"},
    {"id": "water", "name": "Inland waterway"},
]
MODE_SOURCE = {"road": "truck", "rail": "rail", "water": "water"}


def dijkstra(grid, start, edge_cost, owner):
    dist = {start: 0.0}
    prev = {}
    heap = [(0.0, start)]
    while heap:
        d, a = heapq.heappop(heap)
        if d != dist.get(a):
            continue
        for b in grid.neighbours(a):
            if owner[b] == -2:
                continue
            key = (min(a, b), max(a, b))
            base = edge_cost.get(key)
            if base is None:
                base = 3.5 if owner[a] < 0 or owner[b] < 0 else 1.25
            nd = d + base
            if nd < dist.get(b, math.inf):
                dist[b] = nd
                prev[b] = a
                heapq.heappush(heap, (nd, b))
    return dist, prev


def path_to(prev, start, goal):
    if goal == start:
        return [start]
    if goal not in prev:
        return [start, goal]
    out = [goal]
    while out[-1] != start:
        out.append(prev[out[-1]])
    return list(reversed(out))


def build():
    world = load_interim("_world")
    freight = load_interim("fr_freight")
    bounds = load_interim("fr_boundaries")
    infra = json.loads((WEB_DATA / "infrastructure.json").read_text())
    states_doc = json.loads((WEB_DATA / "states.json").read_text())
    cities = json.loads((WEB_DATA / "cities.json").read_text())
    grid = HexGrid(**world["grid"])
    state_by_abbr = {s["abbr"]: s for s in states_doc}
    abbr_by_fips = {s["fips"]: s["abbr"] for s in bounds["states"]}
    region_abbr_by_fips = abbr_by_fips

    # Regional anchors: the owned hex nearest the population-weighted middle of the region.
    proj = MapProjection(**world["projection"])
    pop_by_cell = Counter()
    for c in bounds["communes"]:
        x, y = proj(c["lon"], c["lat"])
        cell = grid.cell_at(x, y)
        if cell < 0 or world["owner"][cell] < 0:
            continue
        if abbr_by_fips[world["states"][world["owner"][cell]]] != region_abbr_by_fips.get(c["region"]):
            continue
        pop_by_cell[cell] += c.get("population") or 0
    acc = {s["abbr"]: [0.0, 0.0, 0.0, 0] for s in states_doc}
    for i, owner in enumerate(world["owner"]):
        if owner < 0:
            continue
        abbr = abbr_by_fips[world["states"][owner]]
        x, y = grid.center(*grid.col_row(i))
        weight = pop_by_cell.get(i, 0)
        acc[abbr][0] += x * weight
        acc[abbr][1] += y * weight
        acc[abbr][2] += weight
        acc[abbr][3] += 1
    anchors = {}
    for abbr, (sx, sy, sw, n) in acc.items():
        if not n:
            continue
        if sw:
            tx, ty = sx / sw, sy / sw
        else:
            cells0 = [i for i, o in enumerate(world["owner"]) if o >= 0 and abbr_by_fips[world["states"][o]] == abbr]
            tx = sum(grid.center(*grid.col_row(i))[0] for i in cells0) / len(cells0)
            ty = sum(grid.center(*grid.col_row(i))[1] for i in cells0) / len(cells0)
        cells = [i for i, o in enumerate(world["owner"]) if o >= 0 and abbr_by_fips[world["states"][o]] == abbr]
        cell = min(cells, key=lambda i: (grid.center(*grid.col_row(i))[0] - tx) ** 2 + (grid.center(*grid.col_row(i))[1] - ty) ** 2)
        x, y = grid.center(*grid.col_row(cell))
        anchors[abbr] = {"cell": cell, "x": round(x, 1), "y": round(y, 1), "city": None}

    suppressed_pairs = {tuple(sorted((r["a"], r["b"]))) for r in freight.get("suppressed_rows", []) if r.get("mode") == "rail"}

    # Aggregate old-region rows into current-region pairs. Source rows are already non-directional.
    pairs = {}
    totals = Counter()
    for row in freight["rows"]:
        key = tuple(sorted((row["a"], row["b"])))
        rec = pairs.setdefault(key, {"modes": Counter(), "tons": 0.0, "rows": 0})
        mode = MODE_SOURCE[row["mode"]]
        rec["modes"][mode] += row["mtkm"]
        rec["tons"] += row["tons_est"]
        rec["rows"] += 1
        totals[key[0]] += row["mtkm"]
        totals[key[1]] += row["mtkm"]

    zones = []
    for abbr in sorted(anchors):
        st = state_by_abbr[abbr]
        city_ids = []
        for c in sorted(cities, key=lambda c: c.get("population") or 0, reverse=True):
            cell = c.get("cell")
            if cell is not None and 0 <= cell < len(world["owner"]) and world["owner"][cell] >= 0:
                if abbr_by_fips[world["states"][world["owner"][cell]]] == abbr:
                    city_ids.append(c["id"])
        zones.append({
            "id": abbr, "faf": [abbr], "name": st["name"], "short": st["name"], "kind": "region",
            "states": [abbr], "cities": city_ids, "counties": sum(1 for c in bounds["counties"] if c["state_fips"] == st["fips"]),
            "anchor": anchors.get(abbr), "partners": [],
            "totals_mtkm": {"within": None, "other_zones": round(totals[abbr], 3), "import": None, "export": None},
        })

    # Cheapest-path drawing aid over mapped road/rail links, exactly as a visual approximation.
    edge_cost = {}
    for a, b, cls, *_ in infra.get("roads", []):
        edge_cost[(min(a, b), max(a, b))] = 0.45 if cls == 0 else 0.65
    for a, b, tier, *_ in infra.get("rail", []):
        key = (min(a, b), max(a, b))
        edge_cost[key] = min(edge_cost.get(key, 999), 0.85 if tier == 0 else 1.0)
    trees = {abbr: dijkstra(grid, z["anchor"]["cell"], edge_cost, world["owner"]) for abbr, z in ((z["id"], z) for z in zones) if z.get("anchor")}

    routes = []
    for (a, b), rec in pairs.items():
        volume = sum(rec["modes"].values())
        if volume <= 0 or a not in anchors or b not in anchors:
            continue
        modes = {m: round(rec["modes"][m] / volume, 4) for m in ["truck", "rail", "water"] if rec["modes"][m] > 0}
        top = max(modes, key=modes.get)
        ca, cb = anchors[a]["cell"], anchors[b]["cell"]
        _, prev = trees.get(a, ({}, {}))
        path = path_to(prev, ca, cb)
        ax, ay = grid.center(*grid.col_row(ca))
        bx, by = grid.center(*grid.col_row(cb))
        routes.append({
            "a": a, "b": b, "rank": 0, "volume_mtkm": round(volume, 3), "tons_k": round(rec["tons"] / 1000, 1),
            "tmiles_m": round(volume, 3), "modes": modes, "top_mode": top, "top_commodity": "all",
            "rail_suppressed": (a, b) in suppressed_pairs or (b, a) in suppressed_pairs,
            "dist_km": round(math.hypot(bx - ax, by - ay)), "path": path,
        })
    all_routes = list(routes)
    routes.sort(key=lambda r: r["volume_mtkm"], reverse=True)
    national_total = sum(r["volume_mtkm"] for r in routes)
    routes = routes[:40]
    for rank, r in enumerate(routes, 1):
        r["rank"] = rank
    route_by_zone = defaultdict(list)
    for r in all_routes:
        route_by_zone[r["a"]].append((r["b"], r["volume_mtkm"], r["top_mode"]))
        route_by_zone[r["b"]].append((r["a"], r["volume_mtkm"], r["top_mode"]))
    for z in zones:
        z["partners"] = sorted(route_by_zone[z["id"]], key=lambda x: x[1], reverse=True)[:5]

    write_web("trade.json", {
        "version": 1, "vintage": "SDES national goods-flow data, 2019", "year": 2019, "sources": ["fr_freight"],
        "rule": "The 40 largest non-directional 2019 road, rail and inland-waterway freight flows between current metropolitan French regions, ranked by tonne-kilometres. Flows are aggregates of the 2016 NUTS-2 source regions; rail rows suppressed for statistical secrecy are absent rather than zero.",
        "path_note": "SDES publishes origin and destination regions, not the physical route. Drawn paths follow the cheapest mapped road/rail hexes as a visual aid only.",
        "units": {"volume_mtkm": "million tonne-kilometres", "tons_k": "thousand metric tonnes, derived by dividing tonne-kilometres by source-region centroid distance"},
        "modes": MODES,
        "commodities": {"all": "All commodities"},
        "national_mtkm": {"domestic": round(national_total, 3), "import": None, "export": None},
        "zones": zones,
        "routes": routes,
    })
    print(f"    {len(routes)} freight routes, {len(zones)} regions")
