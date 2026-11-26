"""Real French power-generation and storage resources for the strategy-map tiles."""

from __future__ import annotations

import json
from collections import Counter, defaultdict

from ..core.hexgrid import HexGrid
from ..core.geo import MapProjection
from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web

REQUIRES = ["_world", "fr_boundaries", "fr_aav", "fr_energy", "cities.json", "states.json"]
PRODUCES = ["resources.json"]

TYPES = [
    {"id": "nuclear", "name": "Nuclear plant", "category": "energy", "emoji": "☢️", "icon": "r-nuclear", "color": "#e8d44d", "unit": "MW", "source": "fr_energy", "description": "Nuclear installations in service, grouped by commune; value is installed capacity."},
    {"id": "hydro", "name": "Hydroelectric plant", "category": "energy", "emoji": "💧", "icon": "r-hydro", "color": "#3fa7d6", "unit": "MW", "source": "fr_energy", "description": "Hydroelectric installations in service, grouped by commune, at least 100 MW."},
    {"id": "pumped_storage", "name": "Pumped storage", "category": "energy", "emoji": "🔋", "icon": "r-pumped-storage", "color": "#2f7fb8", "unit": "MW", "source": "fr_energy", "description": "Pumped-storage installations in service, grouped by commune, at least 100 MW."},
    {"id": "tidal", "name": "Tidal power", "category": "energy", "emoji": "🌊", "icon": "r-hydro", "color": "#2876a8", "unit": "MW", "source": "fr_energy", "description": "Marine tidal generation in service, grouped by commune."},
    {"id": "gas_plant", "name": "Gas plant", "category": "energy", "emoji": "🔥", "icon": "r-gas-plant", "color": "#f08a24", "unit": "MW", "source": "fr_energy", "description": "Gas-fired thermal capacity in service, grouped by commune, at least 300 MW."},
    {"id": "coal_plant", "name": "Coal plant", "category": "energy", "emoji": "🏭", "icon": "r-coal-plant", "color": "#5a5a5a", "unit": "MW", "source": "fr_energy", "description": "Coal-fired thermal capacity in service, grouped by commune, at least 100 MW."},
    {"id": "wind", "name": "Wind power", "category": "energy", "emoji": "🌬️", "icon": "r-wind", "color": "#9fd8cb", "unit": "MW", "source": "fr_energy", "description": "Wind capacity in service grouped by map hex, at least 50 MW."},
    {"id": "solar", "name": "Solar power", "category": "energy", "emoji": "☀️", "icon": "r-solar", "color": "#ffc93c", "unit": "MW", "source": "fr_energy", "description": "Ground-mounted solar capacity in service grouped by map hex, at least 50 MW."},
    {"id": "battery", "name": "Batteries", "category": "energy", "emoji": "🔋", "icon": "r-battery", "color": "#7bc96f", "unit": "MW", "source": "fr_energy", "description": "Battery discharge capacity in service grouped by map hex, at least 30 MW."},
]
MIN_MW = {"nuclear": 100, "hydro": 100, "pumped_storage": 100, "tidal": 100, "gas_plant": 300, "coal_plant": 100, "wind": 50, "solar": 50, "battery": 30}
HEX_GROUPED = {"wind", "solar", "battery"}


def kind(row):
    filiere = (row.get("filiere") or "").lower()
    tech = (row.get("technologie") or "").lower()
    fuel = (row.get("combustible") or "").lower()
    stock = (row.get("typestockage") or "").lower()
    if "nucl" in filiere:
        return "nuclear"
    if "marémotrice" in tech or "maremotrice" in tech or "marines" in filiere:
        return "tidal"
    if "stockage" in filiere or "batterie" in tech or "batterie" in stock:
        return "battery"
    if "hydraulique" in filiere or "hydro" in filiere:
        return "pumped_storage" if "pompage" in tech or "step" in tech or "pompage" in stock else "hydro"
    if "éolien" in filiere or "eolien" in filiere:
        return "wind"
    if "solaire" in filiere or "photovolta" in tech:
        return "solar"
    if "thermique" in filiere:
        if "charbon" in fuel:
            return "coal_plant"
        if "gaz" in fuel or "gaz" in tech or "cycle combin" in tech:
            return "gas_plant"
    return None


def nearest_land(world, grid, x, y):
    exact = grid.cell_at(x, y)
    if exact >= 0 and world["owner"][exact] >= 0:
        return exact
    def d2(i):
        cx, cy = grid.center(*grid.col_row(i))
        return (cx - x) ** 2 + (cy - y) ** 2
    if exact >= 0:
        seen = {exact}
        frontier = [exact]
        for _ in range(20):
            nxt = []
            for cell in frontier:
                for n in grid.neighbours(cell):
                    if n in seen:
                        continue
                    if world["owner"][n] >= 0:
                        return n
                    seen.add(n)
                    nxt.append(n)
            frontier = nxt
            if not frontier:
                break
    return min((i for i, o in enumerate(world["owner"]) if o >= 0), key=d2)


def build():
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    energy = load_interim("fr_energy")
    aav = load_interim("fr_aav")
    cities = json.loads((WEB_DATA / "cities.json").read_text())
    grid = HexGrid(**world["grid"])
    communes = {c["code"]: c for c in bounds["communes"]}
    state_abbr = {s["fips"]: s["abbr"] for s in bounds["states"]}
    city_ids = {city["id"] for city in cities}
    commune_aav = {r["commune"]: r["aav"] for r in aav["composition"] if r["aav"] in city_ids}

    proj = MapProjection(**world["projection"])
    commune_xy = {}
    def locate(code):
        if code not in commune_xy:
            c = communes[code]
            if c.get("lon") is None or c.get("lat") is None:
                commune_xy[code] = None
            else:
                x, y = proj(c["lon"], c["lat"])
                commune_xy[code] = (x, y, nearest_land(world, grid, x, y))
        return commune_xy[code]

    groups = {}
    for r in energy["rows"]:
        if r.get("regime") != "En service":
            continue
        k = kind(r)
        if not k:
            continue
        code = r.get("codeinseecommuneimplantation") or r.get("codeinseecommune")
        if code not in communes:
            continue
        located = locate(code)
        if located is None:
            continue
        x, y, cell = located
        mw = ((r.get("puismaxinstallee") or 0) if k != "battery" else (r.get("puismaxinstalleedischarge") or r.get("puismaxinstallee") or 0)) / 1000
        key = (k, cell) if k in HEX_GROUPED else (k, code)
        g = groups.setdefault(key, {"mw": 0, "units": 0, "names": [], "communes": Counter(), "x": 0.0, "y": 0.0})
        g["mw"] += mw
        g["units"] += 1
        g["communes"][code] += mw
        g["x"] += x * mw
        g["y"] += y * mw
        name = r.get("nominstallation")
        if name and name.lower() != "confidentiel":
            g["names"].append(name)

    items = []
    for (k, _group_key), g in sorted(groups.items()):
        if g["mw"] < MIN_MW[k]:
            continue
        code = g["communes"].most_common(1)[0][0]
        c = communes[code]
        x, y = (g["x"] / g["mw"], g["y"] / g["mw"]) if g["mw"] else locate(code)[:2]
        cell = nearest_land(world, grid, x, y)
        state = state_abbr.get(c.get("region"))
        aav = commune_aav.get(code)
        raw_name = sorted(Counter(g["names"]).items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if g["names"] else c["name"]
        plant_name = raw_name
        upper = raw_name.upper()
        if "CENTRALE NUCLEAIRE DE " in upper:
            plant_name = raw_name[upper.index("CENTRALE NUCLEAIRE DE ") + len("CENTRALE NUCLEAIRE DE "):].title()
            plant_name = "Nuclear power plant of " + plant_name.replace("(Le)", "Le").replace("(La)", "La")
        if k in HEX_GROUPED and len(g["communes"]) > 1:
            detail = f"{g['units']} installations across {len(g['communes'])} communes grouped in this map hex; largest registration commune: {c['name']}; source name: {raw_name}"
        else:
            detail = f"{g['units']} installation{'s' if g['units'] != 1 else ''} registered in {c['name']}; source name: {raw_name}"
        items.append({"type": k, "name": plant_name, "x": round(x, 1), "y": round(y, 1), "cell": cell,
                      "value": round(g["mw"]), "detail": detail, "state": state, "aav": aav})

    order = {t["id"]: n for n, t in enumerate(TYPES)}
    items.sort(key=lambda i: (order[i["type"]], -(i["value"] or 0), i["name"]))
    national = {}
    states = defaultdict(dict)
    for t in TYPES:
        subset = [i for i in items if i["type"] == t["id"]]
        national[t["id"]] = {"count": len(subset), "value": round(sum(i["value"] or 0 for i in subset)), "unit": t["unit"]}
        by_state = defaultdict(list)
        for i in subset:
            by_state[i.get("state")].append(i)
        for st, arr in by_state.items():
            states[st][t["id"]] = {"count": len(arr), "value": round(sum(i["value"] or 0 for i in arr)), "unit": t["unit"]}

    states_doc = json.loads((WEB_DATA / "states.json").read_text())
    for st in states_doc:
        summary = states.get(st["abbr"], {})
        by_type = {k: v["value"] for k, v in summary.items()}
        sites = {k: v["count"] for k, v in summary.items()}
        st["energy"] = {"unit": "MW", "by_type": by_type, "sites": sites, "total": sum(by_type.values()), "note": "Mapped installations meeting capacity thresholds; zero means no mapped site, not missing data."}
    write_web("states.json", states_doc)
    # resources.json is the declared output and must be written last: states.json is an
    # input to this postprocessing builder, so writing it after resources.json would make
    # the builder look permanently stale to the mtime-based build cache.
    write_web("resources.json", {
        "types": TYPES,
        "items": items,
        "summary": {
            "note": "Totals cover only mapped installations meeting each type's capacity threshold; they are not complete national capacity totals.",
            "national": national,
            "states": dict(states),
        },
    })
