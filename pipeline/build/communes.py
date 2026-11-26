"""Commune search index for metropolitan France."""

from ..core.geo import MapProjection
from ..core.store import load_interim, write_web

REQUIRES = ["_world", "fr_boundaries", "fr_insee_stats", "fr_elections", "fr_hazards"]
PRODUCES = ["communes.json"]


def build():
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    proj = MapProjection(**world["projection"])
    counties = {c["geoid"]: c for c in bounds["counties"]}
    stats = load_interim("fr_insee_stats")["comparateur"]["COM"]
    elections = load_interim("fr_elections")["communes"]
    hazard_payload = load_interim("fr_hazards")
    hazards = hazard_payload["communes"]
    rows = []
    for c in bounds["communes"]:
        if c.get("lon") is None or c.get("lat") is None:
            continue
        x, y = proj(c["lon"], c["lat"])
        dept = counties.get(c["department"], {})
        st = stats.get(c["code"], {})
        el = elections.get(c["code"], {})
        hz = hazards.get(c["code"], {})
        area_km2 = (st.get("SUP_2023") or (c.get("surface_ha") or 0) / 100) or None
        density = round((st.get("POP_2023") or c.get("population") or 0) / area_km2, 1) if area_km2 else None
        growth = None
        if st.get("POP_2017") and st.get("POP_2023") is not None:
            growth = round((st["POP_2023"] / st["POP_2017"]) ** (1 / 6) - 1, 4)
        valid = el.get("valid") or 0
        registered = el.get("registered") or 0
        rows.append([
            c["code"], c["name"], dept.get("name") or c["department"], st.get("POP_2023") or c.get("population") or 0,
            round(x, 1), round(y, 1), dept.get("state_fips"),
            density, st.get("MED_SL_2023"), growth,
            round((st.get("RP_PROP_2023") or 0) / st["RP_2023"], 4) if st.get("RP_2023") else None,
            round((st.get("RSEC_2023") or 0) / st["LOG_2023"], 4) if st.get("LOG_2023") else None,
            round((st.get("LVAC_2023") or 0) / st["LOG_2023"], 4) if st.get("LOG_2023") else None,
            round(el.get("macron", 0) / valid, 4) if valid else None,
            round(el.get("le_pen", 0) / valid, 4) if valid else None,
            round((el.get("abstentions") or 0) / registered, 4) if registered else None,
            hz.get("events"), hz.get("dominant"),
            (bounds.get("epcis", {}).get(c.get("epci")) or {}).get("nom"),
            (bounds.get("epcis", {}).get(c.get("epci")) or {}).get("population"),
        ])
    rows.sort(key=lambda r: (-r[3], r[1], r[0]))
    write_web("communes.json", {
        "version": 1,
        "columns": ["code", "name", "department", "population", "x", "y", "state_fips", "density", "median_income", "growth", "owner_share", "second_home_share", "vacancy_share", "macron_share", "lepen_share", "abstention_share", "hazard_events", "hazard_dominant", "epci_name", "epci_population"],
        "sources": ["fr_boundaries", "fr_insee_stats", "fr_elections", "fr_hazards"],
        "hazard_years": hazard_payload["years"],
        "communes": rows,
        "vintage": {"population": "INSEE comparateur 2023", "election": "2022 presidential second round", "hazards": "GASPAR recognitions"},
    })
    print(f"    {len(rows)} communes")
