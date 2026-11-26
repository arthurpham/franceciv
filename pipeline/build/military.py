"""French military bases and garrison cities from the 2012 defense-base personnel file."""

from __future__ import annotations

import json
import re
import unicodedata

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web
from .infrastructure import nearest_land

REQUIRES = ["_world", "fr_boundaries", "fr_aav", "fr_military", "cities.json"]
PRODUCES = ["military.json"]

ALIASES = {
    "LA VALBONNE": "01032",       # Camp de La Valbonne headquarters: Béligneux
    "CAZAUX": "33529",            # Cazaux is part of La Teste-de-Buch
    "SOLENZARA": "2A269",         # now Sari-Solenzara
}
TIER_ORDER = {"major": 0, "base": 1, "site": 2}


def norm(value):
    s = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().upper()
    s = s.replace("ST ", "SAINT ").replace("STE ", "SAINTE ")
    return re.sub(r"[^A-Z0-9]+", "", s)


def slug(value):
    s = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s)).strip("-")


def titlecase(value):
    def cap(part):
        return "-".join(p[:1].upper() + p[1:].lower() for p in part.split("-"))
    return " ".join(cap(p) for p in (value or "").split())


def find_commune(row, exact, prefix, by_code):
    if row["seat"] in ALIASES:
        return by_code.get(ALIASES[row["seat"]]), "locality alias"
    dep = row["department"].zfill(2)
    key = norm(row["seat"])
    hit = exact.get((dep, key))
    if hit:
        return hit, "exact"
    if dep == "20":  # the 2012 file predates Corsica's 2A/2B department codes
        hits = [exact.get((d, key)) for d in ("2A", "2B")]
        hits = [h for h in hits if h]
        if len(hits) == 1:
            return hits[0], "Corsica department update"
    hits = [c for c in prefix.get(key, []) if dep in ("20", c["department"]) or c["department"] == dep]
    if len(hits) == 1:
        return hits[0], "current merged-commune prefix"
    return None, "unmatched"


def build():
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    aav = load_interim("fr_aav")
    mil = load_interim("fr_military")
    cities = json.loads((WEB_DATA / "cities.json").read_text())
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    state_abbr = {s["fips"]: s["abbr"] for s in bounds["states"]}
    city_by_id = {c["id"]: c for c in cities}
    commune_aav = {r["commune"]: r["aav"] for r in aav["composition"] if r["aav"] in city_by_id}

    exact, names, by_code = {}, {}, {}
    for c in bounds["communes"]:
        exact[(c["department"], norm(c["name"]))] = c
        names.setdefault(norm(c["name"]), []).append(c)
        by_code[c["code"]] = c
    prefix = {}
    for key, rows in names.items():
        for c in rows:
            for n in range(5, len(key) + 1):
                prefix.setdefault(key[:n], []).append(c)

    installations, unmatched = [], []
    for row in mil["rows"]:
        commune, match = find_commune(row, exact, prefix, by_code)
        if not commune:
            unmatched.append(row["name"])
            continue
        x, y = proj(commune["lon"], commune["lat"])
        personnel = row["personnel"]
        tier = "major" if personnel >= 5000 else "base" if personnel >= 2000 else "site"
        aav_id = commune_aav.get(commune["code"])
        installations.append({
            "id": f"base-{slug(row['name'])}", "name": titlecase(row["name"]), "component": "other", "joint": True,
            "status": "act", "tier": tier, "curated": False, "area_km2": None, "cells": None,
            "x": round(x, 1), "y": round(y, 1), "cell": nearest_land(world, grid, x, y),
            "county": commune["department"], "cbsa": aav_id, "state": state_abbr.get(commune["region"]),
            "state_filed": state_abbr.get(commune["region"]), "personnel": personnel, "formations": row.get("formations"),
            "seat_commune": commune["name"], "match": match, "year": mil["year"],
        })
    installations.sort(key=lambda f: (TIER_ORDER[f["tier"]], -f["personnel"], f["name"]))

    city_groups = {}
    for f in installations:
        if f["cbsa"]:
            city_groups.setdefault(f["cbsa"], []).append(f)
    city_rows = {}
    for city_id, rows in city_groups.items():
        personnel = sum(f["personnel"] for f in rows)
        population = city_by_id[city_id].get("population") or 0
        share = personnel / population if population else 0
        if personnel < 1000:
            continue
        rows.sort(key=lambda f: -f["personnel"])
        city_rows[city_id] = {
            "tier": "fortress" if personnel >= 5000 else "garrison",
            "armed_forces": personnel, "share": round(share, 4), "naval": False,
            "installations": [f["id"] for f in rows[:8]], "installation_count": len(rows),
        }
    # The historical file gives one aggregate for Île-de-France rather than detailed bases. Keep it out of the
    # installation inventory, but count it in Paris's city total because most of the region belongs to that AAV.
    idf = mil.get("ile_de_france")
    if idf and "001" in city_by_id:
        population = city_by_id["001"].get("population") or 0
        existing = city_rows.get("001", {"installations": [], "installation_count": 0, "armed_forces": 0})
        personnel = existing["armed_forces"] + idf["personnel"]
        share = personnel / population if population else 0
        city_rows["001"] = {**existing, "tier": "fortress", "armed_forces": personnel, "share": round(share, 4),
                            "naval": False, "aggregate_included": True}

    states = {}
    for f in installations:
        st = states.setdefault(f["state"], {"personnel": {"active": {"total": 0}, "guard_reserve": {"total": None}, "civilian": {"total": None}, "total": 0}, "spending": None, "installations": 0})
        st["personnel"]["active"]["total"] += f["personnel"]
        st["personnel"]["total"] += f["personnel"]
        st["installations"] += 1
    if idf and "IDF" in {s["abbr"] for s in bounds["states"]}:
        st = states.setdefault("IDF", {"personnel": {"active": {"total": 0}, "guard_reserve": {"total": None}, "civilian": {"total": None}, "total": 0}, "spending": None, "installations": 0})
        st["personnel"]["active"]["total"] += idf["personnel"]
        st["personnel"]["total"] += idf["personnel"]
        st["ile_de_france_aggregate"] = idf["personnel"]
    metro_stationed = sum(f["personnel"] for f in installations) + ((idf or {}).get("personnel") or 0)
    write_web("military.json", {
        "version": 1,
        "vintage": {"installations": "Ministry of the Armed Forces defense-base personnel, 2012", "personnel": "Same 2012 file"},
        "sources": ["fr_military"],
        "rule": "An AAV appears as a garrison when its geocoded base seats account for at least 1,000 stationed personnel in the 2012 file.",
        "rules": {
            "tier": "Installation display tiers are by stationed personnel in 2012: major 5,000+, base 2,000+, site below 2,000. They are not official importance tiers.",
            "ranges": "No current official open boundary inventory is used; no restricted-ground polygons are drawn.",
            "encampment": "Fortress: 5,000+ stationed personnel. Garrison: 1,000+. Personnel are counted at the base seat commune, not where personnel live. The displayed share divides 2012 personnel by the map's current AAV population only as contextual scale; it is not a historical rate and is not used for selection.",
            "installations": "Rows are 2012 bases de défense, geocoded at their support-group seat commune. They are not individual barracks, boundaries, or a current order of battle.",
        },
        "flagships": [],
        "caveats": "2012 is the newest detailed base-personnel file found in the Ministry's open-data catalogue. It excludes detailed Île-de-France rows and gives only one regional aggregate; that aggregate is included in Paris city statistics but not drawn as a base. Overseas and foreign rows are outside the map. Personnel counts are stationed personnel, not residents in uniform. The file's national organisation total of 251,063 is the sum of detailed rows outside Île-de-France; the map drops 10,960 overseas and foreign personnel, then adds the separate 20,131-person Île-de-France aggregate.",
        "components": [{"id": "other", "name": "Joint defense base", "codes": ["joint"]}],
        "installations": installations,
        "ranges": [],
        "states": states,
        "national": {
            "personnel": {"active": {"total": metro_stationed}, "guard_reserve": {"total": None}, "civilian": {"total": None}, "total": metro_stationed},
            "personnel_scope": "Sum of metropolitan detailed rows plus the separate aggregate Île-de-France row; stationed personnel in 2012, not current strength.",
            "published_total": mil.get("published_total"),
            "spending": None, "veterans": None, "armed_forces_resident": None,
            "matched_bases": len(installations), "unmatched_bases": unmatched,
        },
        "cities": city_rows,
    })
    print(f"    {len(installations)} installations; {len(city_rows)} garrison cities; unmatched {len(unmatched)}")


def check(web_dir):
    path = web_dir / "military.json"
    if not path.exists():
        return [("NOTE", "military.json missing (optional layer)")]
    data = json.loads(path.read_text())
    inst = data.get("installations") or []
    errors = []
    if len(inst) < 40:
        errors.append(f"only {len(inst)} installations")
    for f in inst:
        if not isinstance(f.get("cell"), int) or not isinstance(f.get("personnel"), int) or f["personnel"] <= 0:
            errors.append(f"malformed installation {f.get('id')}")
    if errors:
        return [("FAIL", "; ".join(errors[:4]))]
    return [("PASS", f"military.json: {len(inst)} installations, {len(data.get('cities') or {})} garrison cities")]
