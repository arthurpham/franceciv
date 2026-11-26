"""UNESCO World Heritage wonders for metropolitan France."""

from __future__ import annotations

import json

from ..core.geo import MapProjection, Shape, ShapeIndex
from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web
from .infrastructure import nearest_land

REQUIRES = ["_world", "fr_boundaries", "fr_aav", "fr_unesco", "fr_culture", "cities.json"]
PRODUCES = ["wonders.json"]


def build():
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    aav = load_interim("fr_aav")
    unesco = load_interim("fr_unesco")
    culture = load_interim("fr_culture")
    cities = json.loads((WEB_DATA / "cities.json").read_text())
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    state_abbr = {s["fips"]: s["abbr"] for s in bounds["states"]}
    city_ids = {c["id"] for c in cities}
    commune_aav = {r["commune"]: r["aav"] for r in aav["composition"] if r["aav"] in city_ids}
    shapes = [Shape([[proj(lon, lat) for lon, lat in ring] for ring in c["rings"]]) for c in bounds["communes"]]
    spatial = ShapeIndex(shapes, cell_km=40)
    communes = bounds["communes"]
    commune_by_code = {c["code"]: c for c in communes}

    def geo(lon, lat):
        x, y = proj(lon, lat)
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
            "state": state_abbr.get(c["region"]) if c else None,
        }

    wonders = []
    for row in unesco["rows"]:
        natural = row["category"] in {"Natural", "Mixed"}
        point = row["points"][0]
        wonders.append({
            "id": f"unesco-{row['id']}", "name": row["name"], "short": row["name"],
            "kind": "natural" if natural else "landmark",
            "rule": "unesco_natural" if natural else "unesco_cultural", "rank": 0,
            "metrics": {"designated": row["year"], "criteria": row["criteria"], "url": row["url"], "transnational": row["transnational"]},
            "cells": None, "curated": False, **geo(point["lon"], point["lat"]),
        })
    # Most-visited museums. These are landmarks ranked directly by attendance.
    for row in culture["museums"][:12]:
        wonders.append({
            "id": f"museum-{row['id']}", "name": row["name"], "short": row["name"],
            "kind": "landmark", "rule": "museum_attendance", "rank": 0,
            "metrics": {"visits": row["visits"], "year": row["year"], "sites": row.get("sites"), "domain": row.get("domain"), "url": row.get("url")},
            "cells": None, "curated": False, **geo(row["lon"], row["lat"]),
        })

    # Largest universities by enrolment. SISE locates institutions at their headquarters commune;
    # separate institutions sharing Paris/Lyon/Marseille parent communes are offset slightly so
    # their markers remain independently visible. The offsets are display geometry, not campus data.
    uni_rows = culture["universities"][:12]
    by_commune = {}
    for row in uni_rows:
        by_commune.setdefault(row["commune"], []).append(row)
    for row in uni_rows:
        c = commune_by_code.get(row["commune"])
        if not c:
            continue
        base = geo(c["lon"], c["lat"])
        group = by_commune[row["commune"]]
        if len(group) > 1:
            import math
            k = group.index(row)
            angle = 2 * math.pi * k / len(group) + 0.35
            radius = 7.0 if len(group) > 2 else 4.0
            base["x"] = round(base["x"] + math.cos(angle) * radius, 1)
            base["y"] = round(base["y"] + math.sin(angle) * radius, 1)
            base["cell"] = nearest_land(world, grid, base["x"], base["y"])
        wonders.append({
            "id": f"university-{row['id']}", "name": row["name"], "short": row["name"],
            "kind": "university", "rule": "university_enrolment", "rank": 0,
            "metrics": {"students": row["students"], "year": row["year"], "academic_year": "2024-25", "seat": row.get("seat"), "type": row.get("type")},
            "cells": None, "curated": False, **base,
        })

    for rule in ("unesco_natural", "unesco_cultural", "museum_attendance", "university_enrolment"):
        if rule == "museum_attendance":
            keyfn = lambda w: (-(w["metrics"].get("visits") or 0), w["name"])
        elif rule == "university_enrolment":
            keyfn = lambda w: (-(w["metrics"].get("students") or 0), w["name"])
        else:
            keyfn = lambda w: (w["metrics"]["designated"] or 9999, w["name"])
        subset = sorted((w for w in wonders if w["rule"] == rule), key=keyfn)
        for rank, w in enumerate(subset, 1):
            w["rank"] = rank
    wonders.sort(key=lambda w: (w["rule"], w["rank"]))

    write_web("wonders.json", {
        "version": 1,
        "vintage": {"unesco": "UNESCO World Heritage List, current XML export"},
        "sources": ["fr_unesco", "fr_culture"],
        "rules": [
            {"id": "unesco_natural", "kind": "natural", "kinds": ["natural"], "text": "Natural and mixed UNESCO World Heritage properties with at least one component point in metropolitan France or Corsica. Ranked by inscription year, not importance or visits."},
            {"id": "unesco_cultural", "kind": "landmark", "kinds": ["landmark"], "text": "Cultural UNESCO World Heritage properties with at least one component point in metropolitan France or Corsica. Serial properties are represented by their first French point; ranking is by inscription year, not importance."},
            {"id": "museum_attendance", "kind": "landmark", "kinds": ["landmark"], "text": "The 12 most-visited open Musées de France in each institution's latest annual attendance, using total visits summed across distinct physical sites sharing one Muséofile identifier."},
            {"id": "university_enrolment", "kind": "university", "kinds": ["university"], "text": "The 12 largest French universities by total enrolled students in SISE 2024-25, including principal and secondary enrolments and CPGE double enrolments. Locations are administrative headquarters communes, not full campus footprints."},
        ],
        "national": {
            "world_heritage_entries": sum(1 for w in wonders if w["id"].startswith("unesco-")),
            "museum_visits_top": max((w["metrics"].get("visits") or 0 for w in wonders if w["rule"] == "museum_attendance"), default=None),
            "museum_year": culture["years"].get("museums"), "university_year": culture["years"].get("universities"),
        },
        "wonders": wonders,
    })
    print(f"    {len(wonders)} wonders")
