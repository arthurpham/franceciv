"""French transport tile improvements: schematic road/rail links plus real airports and ports."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import defaultdict

from ..core.geo import MapProjection, Shape, ShapeIndex
from ..core.insets import transform_real_point
from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web

REQUIRES = ["_world", "fr_boundaries", "fr_aav", "fr_transport", "fr_rail_network", "fr_rail_stations", "fr_road_traffic", "cities.json"]
PRODUCES = ["infrastructure.json"]

ROAD_CLASSES = [{"id": "motorway", "name": "Motorway / European route"}, {"id": "major", "name": "Major highway"}]
RAIL_TIERS = [{"id": "main", "name": "Main line"}, {"id": "secondary", "name": "Secondary line"}]
HUBS = {"L": "Large hub", "M": "Medium hub", "S": "Small hub", "N": "Nonhub primary"}
PORT_ALIASES = {
    "haropa le havre and rouen": "le havre",
    "nantes saint nazaire": "saint nazaire",
    "marseille": "marseille",
    "sete": "sete",
}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def road_class(p):
    if p.get("level") == "E":
        return 0
    if p.get("type") in {"Major Highway", "Beltway"} and (p.get("expressway") == 1 or (p.get("scalerank") or 99) <= 7):
        return 1
    return None


def rail_tier(p):
    if p.get("official"):
        return 0 if p.get("track_type") == "Ligne" else 1
    rank = p.get("scalerank") or 99
    if rank <= 5:
        return 0
    if rank <= 8:
        return 1
    return None


def corsican_line(row):
    # Corsica's railways are outside the national RFN export; retain the schematic Natural
    # Earth geometry there while official SNCF geometry replaces the mainland network.
    lons = [x for x, y in row["line"]]
    lats = [y for x, y in row["line"]]
    return min(lons) > 8.2 and max(lats) < 43.2


def route_name(p):
    raw = p.get("routeraw") or p.get("name") or p.get("label")
    if raw:
        return str(raw).strip() or None
    return None


def projected_samples(line, proj, step_km=1.0):
    pts = [proj(lon, lat) for lon, lat in line]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dist = math.hypot(x1 - x0, y1 - y0)
        n = max(1, math.ceil(dist / step_km))
        for k in range(n):
            t = k / n
            yield x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
    if pts:
        yield pts[-1]


def rasterize(rows, choose, proj, grid, world):
    """Turn polylines into unique neighbouring-hex links by dense sampling.

    A 1 km sample step is deliberately smaller than the 8 km hex radius, so consecutive
    samples normally occupy the same or adjacent hexes. Rare corner-cutting gaps are dropped
    rather than inventing non-neighbour links the renderer cannot draw.
    """
    best = {}
    names = {}
    for row in rows:
        cls = choose(row["properties"])
        if cls is None:
            continue
        cells = []
        for x, y in projected_samples(row["line"], proj):
            cell = grid.cell_at(x, y)
            if cell >= 0 and (not cells or cells[-1] != cell):
                cells.append(cell)
        for a, b in zip(cells, cells[1:]):
            if a == b or b not in grid.neighbours(a):
                continue
            if world["owner"][a] < 0 and world["owner"][b] < 0:
                continue
            if world["owner"][a] == -2 or world["owner"][b] == -2:
                continue
            key = (min(a, b), max(a, b))
            if key not in best or cls < best[key]:
                best[key] = cls
                names[key] = route_name(row["properties"])
    return [[a, b, cls] + ([names[(a, b)]] if choose.__name__ == "road_class" and names.get((a, b)) else []) for (a, b), cls in sorted(best.items())]


def nearest_land(world, grid, x, y):
    exact = grid.cell_at(x, y)
    if exact >= 0 and world["owner"][exact] >= 0:
        return exact
    cx0, cy0 = x, y

    def d2(i):
        cx, cy = grid.center(*grid.col_row(i))
        return (cx - cx0) ** 2 + (cy - cy0) ** 2

    return min((i for i, o in enumerate(world["owner"]) if o >= 0), key=d2)


def make_spatial_index(bounds, proj):
    shapes, communes = [], []
    for c in bounds["communes"]:
        shapes.append(Shape([[proj(lon, lat) for lon, lat in ring] for ring in c["rings"]]))
        communes.append(c)
    return ShapeIndex(shapes, cell_km=40), communes


def main_hub(passengers):
    if passengers is None:
        return None
    if passengers >= 10_000_000:
        return "L"
    if passengers >= 3_000_000:
        return "M"
    if passengers >= 500_000:
        return "S"
    return "N"


def build():
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    aav = load_interim("fr_aav")
    trans = load_interim("fr_transport")
    rail_network = load_interim("fr_rail_network")
    road_traffic = load_interim("fr_road_traffic")
    rail_stations_src = load_interim("fr_rail_stations")
    cities = json.loads((WEB_DATA / "cities.json").read_text())
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    state_abbr = {s["fips"]: s["abbr"] for s in bounds["states"]}
    city_ids = {c["id"] for c in cities}
    commune_aav = {r["commune"]: r["aav"] for r in aav["composition"] if r["aav"] in city_ids}
    spatial, communes = make_spatial_index(bounds, proj)

    def site_geo(lon, lat):
        x, y = proj(*transform_real_point(lon, lat))
        cell = nearest_land(world, grid, x, y)
        idx = spatial.locate(x, y)
        c = communes[idx] if idx >= 0 else None
        if c is None:
            def d2(cm):
                cx, cy = proj(cm["lon"], cm["lat"])
                return (cx - x) ** 2 + (cy - y) ** 2
            candidates = [cm for cm in communes if cm.get("lon") is not None]
            nearest = min(candidates, key=d2)
            if d2(nearest) <= 15 ** 2:
                c = nearest
        return {
            "x": round(x, 1), "y": round(y, 1), "cell": cell,
            "county": c["department"] if c else None,
            "aav": commune_aav.get(c["code"]) if c else None,
            "state": state_abbr.get(c["region"]) if c else state_abbr.get(world["states"][world["owner"][cell]]) if cell >= 0 and world["owner"][cell] >= 0 else None,
        }

    official_roads = [{"line": r["line"], "properties": {"level": "E" if (r.get("route") or "").startswith("A") else None, "type": "Major Highway", "expressway": 1, "scalerank": 5, "routeraw": r.get("route")}} for r in road_traffic["rows"]]
    def corsican_road(row):
        lons = [x for x, y in row["line"]]; lats = [y for x, y in row["line"]]
        return sum(lons) / len(lons) > 8.2 and sum(lats) / len(lats) < 43.3
    roads = rasterize(official_roads + [r for r in trans["roads"] if corsican_road(r)], road_class, proj, grid, world)
    rail_rows = [row for row in trans["rail"] if corsican_line(row)] + rail_network["rows"]
    rail = rasterize(rail_rows, rail_tier, proj, grid, world)

    airport_by_ident = {a["ident"]: a for a in trans["airports"] if a.get("ident", "").startswith("LF")}
    airports = []
    for ident, years in trans["air_passengers"].items():
        base = airport_by_ident.get(ident)
        if not base:
            continue
        pax, prev = years.get("2023"), years.get("2022")
        if not pax or pax < 20_000:
            continue
        geo = site_geo(base["lon"], base["lat"])
        label = trans["airport_labels"].get("FR_" + ident, base["name"])
        name = re.sub(r"\s+airport$", "", label or base["name"], flags=re.I).title()
        airports.append({
            "id": base.get("iata") or ident, "name": name, "city": base.get("municipality"),
            "hub": main_hub(pax), "enplanements": round(pax), "enplanements_prev": round(prev) if prev else None,
            "cargo_lbs": None, "year": 2023, **geo,
        })
    airports.sort(key=lambda a: -(a["enplanements"] or 0))

    # Match Eurostat ports first to Natural Earth's port points, then to a same-named commune centroid.
    ne_by_name = {norm(p["name"]): p for p in trans["ne_ports"] if p.get("name")}
    commune_by_name = {}
    for c in bounds["communes"]:
        key = norm(c["name"])
        if key not in commune_by_name or (c.get("population") or 0) > (commune_by_name[key].get("population") or 0):
            commune_by_name[key] = c
    ports = []
    for code, rec in trans["port_tons"].items():
        label = trans["port_labels"].get(code, code)
        n = norm(label)
        n = PORT_ALIASES.get(n, n)
        n = re.sub(r"\s*\([^)]*\)", "", n).strip()
        point = ne_by_name.get(n)
        lon = lat = None
        if point:
            lon, lat = point["lon"], point["lat"]
        else:
            commune = commune_by_name.get(n)
            if commune and commune.get("lon") is not None:
                lon, lat = commune["lon"], commune["lat"]
        if lon is None or not rec["tons"]:
            continue
        name = re.sub(r"\s*\([^)]*\)", "", label).strip()
        ports.append({"id": code.removeprefix("FR_"), "name": name, "type": "coastal", "rank": 0,
                      "tons": round(rec["tons"]), "domestic": None, "foreign": None, "imports": None, "exports": None,
                      "year": rec["year"], **site_geo(lon, lat)})
    ports.sort(key=lambda p: -p["tons"])
    for rank, p in enumerate(ports, 1):
        p["rank"] = rank


    stations = []
    for st in rail_stations_src["stations"]:
        if st["passengers"] < 250_000:
            continue
        stations.append({
            "id": st["uic"], "name": st["name"], "passengers": st["passengers"], "year": st["year"],
            "segment": st.get("segment"), **site_geo(st["lon"], st["lat"]),
        })
    stations.sort(key=lambda st: -st["passengers"])

    write_web("infrastructure.json", {
        "version": 1,
        "vintage": {"roads": "Natural Earth v5.1.2 (1:10m)", "rail": "SNCF Réseau official active-line shapes; Natural Earth v5.1.2 retained only for Corsica", "ports": "Eurostat mar_go_aa, 2023", "airports": "Eurostat avia_paoa, 2023; OurAirports positions", "stations": "SNCF station traffic 2025"},
        "sources": ["fr_transport", "fr_rail_network", "fr_rail_stations", "fr_road_traffic"],
        "rules": {
            "roads": "Natural Earth European-route/motorway lines form class 0; major highways and expressways at scale rank 7 or better form class 1. Geometry is schematic map art, not a complete road inventory.",
            "rail": "Official active SNCF Réseau line sections: ordinary lines form main lines and connections/main/port tracks form secondary lines. Natural Earth is retained only for Corsica because it is outside the RFN export.",
            "ports": "Eurostat ports reporting metric tonnes handled in 2023, positioned by Natural Earth or their namesake commune.",
            "airports": "Metropolitan airports with at least 20,000 passengers on board in 2023. Hub letters are local display-size buckets.",
            "stations": "Passenger stations with at least 250,000 passengers in 2025. SNCF changed the traffic methodology in 2025, so values are not directly comparable with 2015–2024.",
        },
        "road_classes": ROAD_CLASSES,
        "rail_tiers": RAIL_TIERS,
        "hubs": HUBS,
        "roads": roads,
        "rail": rail,
        "ports": ports,
        "airports": airports,
        "stations": stations,
    })
    print(f"    roads {len(roads)}, rail {len(rail)}, ports {len(ports)}, airports {len(airports)}, stations {len(stations)}")
