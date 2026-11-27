"""First-class EPCI and IRIS statistical geography."""

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .connectivity import nearest_land

REQUIRES = ["_world", "fr_boundaries", "fr_insee_stats", "fr_iris"]
PRODUCES = ["epci.json", "iris_index.json", "neighborhoods.json"]
RAMP = ["#1b1035", "#4b2377", "#9a3b8a", "#e0645e", "#f9b24a", "#fff3a8"]


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def positive_percentile(vals, p):
    return percentile([v for v in vals if v], p)


def lens(lens_id, name, emoji, unit, fmt, scale, vals, desc):
    domain_vals = [v for v in vals if v] if scale == "log" else vals
    return {"id": lens_id, "group": "neighborhoods", "name": name, "icon": lens_id, "emoji": emoji, "unit": unit,
            "format": fmt, "scale": scale, "domain": [positive_percentile(domain_vals, 2), positive_percentile(domain_vals, 98)],
            "ramp": RAMP, "higher_is": "neutral", "source": "fr_iris", "description": desc, "values": vals}


def annual_growth(row):
    if row.get("POP_2017") and row.get("POP_2023") is not None:
        return round((row["POP_2023"] / row["POP_2017"]) ** (1 / 6) - 1, 4)
    return None


def build():
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    stats_payload = load_interim("fr_insee_stats")
    iris = load_interim("fr_iris")
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])

    # EPCI search/index rows. EPCI statistics already exist in INSEE Comparateur;
    # map positions are population-weighted member-commune centroids.
    epci_stats = stats_payload["comparateur"]["EPCI"]
    members = defaultdict(list)
    for c in bounds["communes"]:
        if c.get("epci") and c.get("lon") is not None:
            members[c["epci"]].append(c)
    dep_name = {d["geoid"]: d["name"] for d in bounds["counties"]}
    epci_rows = []
    for code, ref in sorted(bounds["epcis"].items()):
        st = epci_stats.get(code, {})
        ms = members.get(code, [])
        weight = sum(c.get("population") or 0 for c in ms)
        if weight:
            x0 = sum(c["lon"] * (c.get("population") or 0) for c in ms) / weight
            y0 = sum(c["lat"] * (c.get("population") or 0) for c in ms) / weight
        elif ms:
            x0 = sum(c["lon"] for c in ms) / len(ms); y0 = sum(c["lat"] for c in ms) / len(ms)
        else:
            continue
        x, y = proj(x0, y0)
        population = st.get("POP_2023") or ref.get("population") or 0
        area = st.get("SUP_2023")
        deps = sorted({dep_name.get(c["department"], c["department"]) for c in ms})
        epci_rows.append([
            code, ref.get("nom") or code, population, round(x, 1), round(y, 1), ", ".join(deps), len(ms),
            round(population / area, 1) if population and area else None,
            st.get("MED_SL_2023"), (st.get("PR_MD60_2023") or 0) / 100 if st.get("PR_MD60_2023") is not None else None,
            annual_growth(st),
            round((st.get("RP_PROP_2023") or 0) / st["RP_2023"], 4) if st.get("RP_2023") else None,
            round((st.get("RSEC_2023") or 0) / st["LOG_2023"], 4) if st.get("LOG_2023") else None,
            round((st.get("LVAC_2023") or 0) / st["LOG_2023"], 4) if st.get("LOG_2023") else None,
            round((st.get("NAIS_2023", 0) - st.get("DECES_2023", 0)) / population, 4) if population and st.get("NAIS_2023") is not None and st.get("DECES_2023") is not None else None,
            round(st.get("ETAB_2024", 0) * 1000 / population, 2) if population and st.get("ETAB_2024") is not None else None,
        ])
    write_web("epci.json", {
        "version": 1,
        "columns": ["code", "name", "population", "x", "y", "departments", "commune_count", "density", "median_income", "poverty", "growth", "owner_share", "second_home_share", "vacancy_share", "natural_balance", "business_density"],
        "sources": ["fr_boundaries", "fr_insee_stats"],
        "epcis": epci_rows,
        "vintage": "INSEE comparateur 2023 / geo.api.gouv.fr EPCI reference",
    })

    # Compact IRIS search rows. Whole-commune pseudo-IRIS are omitted because they
    # duplicate commune search; they still contribute to the neighborhood lenses.
    supported_deps = {d["geoid"] for d in bounds["counties"]}
    supported_iris = [r for r in iris["rows"] if r.get("department") in supported_deps]
    excluded_iris = len(iris["rows"]) - len(supported_iris)
    iris_rows = []
    for r in sorted((r for r in supported_iris if r.get("true_iris")), key=lambda z: z["code"]):
        pop = r.get("population")
        area = r.get("area_km2")
        x, y = proj(r["lon"], r["lat"])
        iris_rows.append([
            r["code"], r["name"], r["commune"], r["department"], round(pop or 0), round(x, 1), round(y, 1),
            round(pop / area, 1) if pop and area else None,
            round(r["senior_share"], 4) if r.get("senior_share") is not None else None,
            round(r["immigration_share"], 4) if r.get("immigration_share") is not None else None,
            round(r["youth_share"], 4) if r.get("youth_share") is not None else None,
            round(r["working_age_share"], 4) if r.get("working_age_share") is not None else None,
            round(r["foreign_share"], 4) if r.get("foreign_share") is not None else None,
            1 if r.get("true_iris") else 0, r.get("type"), round(area or 0, 3),
        ])
    write_web("iris_index.json", {
        "version": 1,
        "columns": ["code", "name", "commune", "department", "population", "x", "y", "density", "senior_share", "immigration_share", "youth_share", "working_age_share", "foreign_share", "true_iris", "type", "area_km2"],
        "sources": ["fr_iris"],
        "iris": iris_rows,
        "vintage": "INSEE census population 2022; communes not divided into IRIS are pseudo-IRIS; Mayotte population statistics unavailable; collectivities outside the current map frame omitted",
        "excluded_outside_map": excluded_iris,
    })

    # Hex lenses from the fine statistical partition. Whole IRIS are assigned by centroid,
    # so both numerator and denominator use the same reproducible spatial approximation.
    acc = defaultdict(lambda: defaultdict(float))
    unmatched = 0
    for r in supported_iris:
        pop = r.get("population")
        if not pop:
            continue
        x, y = proj(r["lon"], r["lat"])
        cell = nearest_land(world, grid, x, y)
        if cell < 0:
            unmatched += pop
            continue
        a = acc[cell]
        a["pop"] += pop
        a["area"] += r.get("area_km2") or 0
        a["seniors"] += pop * (r.get("senior_share") or 0)
        a["immigrants"] += pop * (r.get("immigration_share") or 0)
        a["youth"] += pop * (r.get("youth_share") or 0)

    density, seniors, immigrants, youth = [], [], [], []
    for i in range(grid.size):
        a = acc.get(i)
        if a and a["pop"]:
            density.append(round(a["pop"] / a["area"], 1) if a["area"] else None)
            seniors.append(round(a["seniors"] / a["pop"], 4))
            immigrants.append(round(a["immigrants"] / a["pop"], 4))
            youth.append(round(a["youth"] / a["pop"], 4))
        else:
            density.append(None); seniors.append(None); immigrants.append(None); youth.append(None)

    write_web("neighborhoods.json", {
        "version": 1, "vintage": "INSEE census population 2022 / Contours IRIS", "sources": ["fr_iris"],
        "group": {"id": "neighborhoods", "name": "Neighborhoods"}, "unmatched_population": round(unmatched),
        "lenses": [
            lens("neighborhood_density", "Neighborhood density", "🏘️", "people / km²", "int", "log", density,
                 "Population per km² from the 2022 IRIS statistical partition, aggregated to map hexes. Communes not divided into IRIS are whole-commune pseudo-IRIS; whole units are assigned by centroid, so this is much finer than department density but still approximate at hex boundaries."),
            lens("neighborhood_seniors", "Neighborhood seniors", "👵", "share of residents", "pct", "linear", seniors,
                 "Residents aged 65 or older as a share of residents in the 2022 IRIS statistical partition, population-weighted within map hexes. Excludes Mayotte."),
            lens("neighborhood_immigration", "Neighborhood immigration", "🌍", "share of residents", "pct", "linear", immigrants,
                 "Immigrants as a share of residents in the 2022 IRIS statistical partition, population-weighted within map hexes. INSEE defines an immigrant as a person born abroad who was not born a French national. Excludes Mayotte."),
            lens("neighborhood_youth", "Neighborhood youth", "🧒", "share of residents", "pct", "linear", youth,
                 "Residents under 20 as a share of residents in the 2022 IRIS statistical partition, population-weighted within map hexes. Excludes Mayotte."),
        ],
    })
    print(f"    {len(epci_rows)} EPCI, {len(iris_rows)} true-IRIS browser rows; excluded {excluded_iris} outside current map frame")


def check(web_dir):
    import json
    epci = json.loads((web_dir / "epci.json").read_text())
    iris = json.loads((web_dir / "iris_index.json").read_text())
    neighborhoods = json.loads((web_dir / "neighborhoods.json").read_text())
    assert len(epci["epcis"]) > 1200 and len(iris["iris"]) > 15_000
    assert len(neighborhoods["lenses"]) == 4
    density = [v for v in neighborhoods["lenses"][0]["values"] if v is not None]
    seniors = [v for v in neighborhoods["lenses"][1]["values"] if v is not None]
    assert len(density) > 2500 and 20 < sum(density) / len(density) < 1000
    assert len(seniors) > 2500 and 0.05 < sum(seniors) / len(seniors) < 0.4
    return [("PASS", f"statistical geography: {len(epci['epcis'])} EPCI and {len(iris['iris'])} true-IRIS rows")]
