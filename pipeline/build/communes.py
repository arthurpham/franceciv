"""Commune search index for metropolitan France."""

from ..core.geo import MapProjection
from ..core.store import load_interim, write_web

REQUIRES = ["_world", "fr_boundaries"]
PRODUCES = ["communes.json"]


def build():
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    proj = MapProjection(**world["projection"])
    counties = {c["geoid"]: c for c in bounds["counties"]}
    rows = []
    for c in bounds["communes"]:
        if c.get("lon") is None or c.get("lat") is None:
            continue
        x, y = proj(c["lon"], c["lat"])
        dept = counties.get(c["department"], {})
        rows.append([
            c["code"], c["name"], dept.get("name") or c["department"], c["population"] or 0,
            round(x, 1), round(y, 1), dept.get("state_fips"),
        ])
    rows.sort(key=lambda r: (-r[3], r[1], r[0]))
    write_web("communes.json", {
        "version": 1,
        "columns": ["code", "name", "department", "population", "x", "y", "state_fips"],
        "communes": rows,
    })
    print(f"    {len(rows)} communes")
