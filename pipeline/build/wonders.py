"""UNESCO World Heritage wonders for metropolitan France."""

from __future__ import annotations

import json

from ..core.geo import MapProjection, Shape, ShapeIndex
from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web
from .infrastructure import nearest_land

REQUIRES = ["_world", "fr_boundaries", "fr_aav", "fr_unesco", "cities.json"]
PRODUCES = ["wonders.json"]


def build():
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    aav = load_interim("fr_aav")
    unesco = load_interim("fr_unesco")
    cities = json.loads((WEB_DATA / "cities.json").read_text())
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    state_abbr = {s["fips"]: s["abbr"] for s in bounds["states"]}
    city_ids = {c["id"] for c in cities}
    commune_aav = {r["commune"]: r["aav"] for r in aav["composition"] if r["aav"] in city_ids}
    shapes = [Shape([[proj(lon, lat) for lon, lat in ring] for ring in c["rings"]]) for c in bounds["communes"]]
    spatial = ShapeIndex(shapes, cell_km=40)
    communes = bounds["communes"]

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
            "cbsa": commune_aav.get(c["code"]) if c else None,
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
    for rule in ("unesco_natural", "unesco_cultural"):
        subset = sorted((w for w in wonders if w["rule"] == rule), key=lambda w: (w["metrics"]["designated"] or 9999, w["name"]))
        for rank, w in enumerate(subset, 1):
            w["rank"] = rank
    wonders.sort(key=lambda w: (w["rule"], w["rank"]))

    write_web("wonders.json", {
        "version": 1,
        "vintage": {"unesco": "UNESCO World Heritage List, current XML export"},
        "sources": ["fr_unesco"],
        "rules": [
            {"id": "unesco_natural", "kind": "natural", "kinds": ["natural"], "text": "Natural and mixed UNESCO World Heritage properties with at least one component point in metropolitan France or Corsica. Ranked by inscription year, not importance or visits."},
            {"id": "unesco_cultural", "kind": "landmark", "kinds": ["landmark"], "text": "Cultural UNESCO World Heritage properties with at least one component point in metropolitan France or Corsica. Serial properties are represented by their first French point; ranking is by inscription year, not importance."},
        ],
        "national": {"world_heritage_entries": len(wonders)},
        "wonders": wonders,
    })
    print(f"    {len(wonders)} UNESCO wonders")
