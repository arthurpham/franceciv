"""France MVP core: cities, regions, national yields, department table and lenses.

This first builder intentionally preserves the original usaciv web contracts while using
French concepts: région→state, département→county, aire d'attraction des villes→city.
Eurostat employment/GDP are department-level and are allocated across AAVs in proportion
to commune population; the outputs mark those values as estimates.
"""

from __future__ import annotations

import math
import unicodedata
from collections import Counter, defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web

REQUIRES = ["_world", "fr_boundaries", "fr_aav", "fr_eurostat", "fr_insee_stats", "fr_elections", "fr_hazards"]
PRODUCES = ["cities.json", "states.json", "nation.json", "counties.json", "lenses.json"]

INDUSTRIES = {
    "agriculture": "Agriculture, forestry & fishing", "mining": "Mining & quarrying",
    "construction": "Construction", "manufacturing": "Manufacturing", "wholesale": "Wholesale trade",
    "retail": "Retail trade", "transportation": "Transportation & storage", "utilities": "Utilities",
    "information": "Information & communication", "finance": "Finance & insurance", "real_estate": "Real estate",
    "professional": "Professional, scientific & technical services", "management": "Company management",
    "admin": "Administrative & support services", "education": "Education", "health": "Health & social work",
    "arts": "Arts, entertainment & recreation", "accommodation": "Accommodation & food services",
    "other": "Other services", "public_admin": "Public administration",
}
YIELDS = [
    {"key": "food", "icon": "y-food", "emoji": "🌾", "label": "Food", "color": "#7fbf3f", "unit": "workers", "industries": ["agriculture"], "description": "Employment in agriculture, forestry and fishing (Eurostat NACE A), allocated within departments in proportion to population."},
    {"key": "production", "icon": "y-production", "emoji": "⚙️", "label": "Production", "color": "#d9823b", "unit": "workers", "industries": ["manufacturing", "construction", "mining"], "description": "Employment in industry (NACE B–E) plus construction (NACE F)."},
    {"key": "gold", "icon": "y-gold", "emoji": "💰", "label": "Gold", "color": "#f2c94c", "unit": "eur", "industries": [], "description": "Gross domestic product per year in current euros (Eurostat regional accounts). AAV values are department values allocated by population."},
    {"key": "science", "icon": "y-science", "emoji": "🔬", "label": "Science", "color": "#4fa3e0", "unit": "workers", "industries": ["professional", "information"], "description": "Employment in information/communication (NACE J) plus professional, scientific and technical activities (NACE M–N)."},
    {"key": "culture", "icon": "y-culture", "emoji": "🎭", "label": "Culture", "color": "#b07ce0", "unit": "workers", "industries": ["arts"], "description": "Employment in arts, entertainment, recreation and other services (NACE R–U)."},
]

# NACE A38 activity codes used by the census workplace-employment table. Unlike the Eurostat
# department aggregates, these are observed directly for each aire d'attraction.
A38_INDUSTRY = {
    "AZ": ("agriculture", 1), "BZ": ("mining", 1),
    **{c: ("manufacturing", 1) for c in ["CA","CB","CC","CD","CE","CF","CG","CH","CI","CJ","CK","CL","CM"]},
    "DZ": ("utilities", 1), "EZ": ("utilities", 1), "FZ": ("construction", 1),
    "GZ": ("retail", .65), "HZ": ("transportation", 1), "IZ": ("accommodation", 1),
    "JA": ("information", 1), "JB": ("information", 1), "JC": ("information", 1),
    "KZ": ("finance", 1), "LZ": ("real_estate", 1), "MA": ("professional", 1), "MB": ("professional", 1), "MC": ("professional", 1),
    "NZ": ("admin", 1), "OZ": ("public_admin", 1), "PZ": ("education", 1),
    "QA": ("health", 1), "QB": ("health", 1), "QC": ("health", 1),
    "RZ": ("arts", 1), "SZ": ("other", 1), "TZ": ("other", 1), "UZ": ("other", 1),
}
# GZ combines wholesale and retail in A38; count the remainder as wholesale as well as retail.
A38_EXTRA = {"GZ": ("wholesale", .35)}


def census_jobs(row):
    """Translate one AAV/DEP/REG row of A38 workplace employment into the app's industry keys."""
    jobs = dict.fromkeys(INDUSTRIES, 0.0)
    for code, value in (row or {}).items():
        if code not in A38_INDUSTRY:
            continue
        key, share = A38_INDUSTRY[code]
        jobs[key] += value * share
        if code in A38_EXTRA:
            k2, s2 = A38_EXTRA[code]
            jobs[k2] += value * s2
    return {k: round(v) for k, v in jobs.items()}


def pct_change(new, old):
    return (new / old - 1) if new is not None and old not in (None, 0) else None


def comp_series(row, prefix):
    years = []
    for key, value in (row or {}).items():
        if key.startswith(prefix + "_"):
            try:
                years.append((int(key.rsplit("_", 1)[1]), value))
            except (TypeError, ValueError):
                pass
    return [[y, round(v, 2) if isinstance(v, float) else v] for y, v in sorted(years)]

def unemployment_rate(row):
    emp = (row or {}).get("EMPSTA_ENQ=1|AGE=Y15T64")
    unemp = (row or {}).get("EMPSTA_ENQ=2|AGE=Y15T64")
    return unemp / (emp + unemp) if emp is not None and unemp is not None and emp + unemp else None


# NACE aggregate -> original industry keys. Some high-level Eurostat slices are necessarily broader than ACS industries.
NACE_JOBS = {
    "A": {"agriculture": 1}, "B-E": {"manufacturing": 0.9, "utilities": 0.07, "mining": 0.03},
    "F": {"construction": 1},
    "G-I": {"retail": 0.45, "wholesale": 0.2, "transportation": 0.2, "accommodation": 0.15},
    "J": {"information": 1}, "K": {"finance": 1}, "L": {"real_estate": 1},
    "M_N": {"professional": 0.68, "admin": 0.32}, "O-Q": {"public_admin": 0.35, "education": 0.28, "health": 0.37},
    "R-U": {"arts": 0.4, "other": 0.6},
}


def norm(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "")).lower() if c.isalnum())


def dist_id(a, b):
    if b == 0 or b is None:
        return None
    return a / b


def percentile(vals, p):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    k = (len(vals) - 1) * p / 100
    lo, hi = math.floor(k), math.ceil(k)
    return vals[lo] if lo == hi else vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


def econ_rows(eurostat, kind, unit, wstatus=None):
    out = {}
    for r in eurostat[kind]:
        if r.get("unit") != unit or (wstatus and r.get("wstatus") != wstatus):
            continue
        key = (r["geo"], r.get("nace_r2", "TOTAL"))
        out[key] = r.get("value")
    return out


def build():
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    aav = load_interim("fr_aav")
    eu = load_interim("fr_eurostat")
    stats = load_interim("fr_insee_stats")
    elections = load_interim("fr_elections")
    hazards = load_interim("fr_hazards")
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    states_meta = load_interim_payload_states = None
    counties_meta = {c["geoid"]: c for c in bounds["counties"]}
    commune = {c["code"]: c for c in bounds["communes"]}
    county_ids = world["counties"]
    state_ids = world["states"]
    region_abbr = {s["fips"]: s["abbr"] for s in bounds["states"]}
    region_name = {s["fips"]: s["name"] for s in bounds["states"]}
    employment_stats = stats["datasets"].get("employment", {})
    comp_stats = stats.get("comparateur", {})
    activity_stats = stats["datasets"].get("activity", {})
    aav_employment = employment_stats.get("AAV2020", {})
    commune_employment = employment_stats.get("COM", {})
    dep_employment = employment_stats.get("DEP", {})
    reg_employment = employment_stats.get("REG", {})
    fr_employment = employment_stats.get("FRANCE", {})
    aav_activity = activity_stats.get("AAV2020", {})
    dep_activity = activity_stats.get("DEP", {})
    reg_activity = activity_stats.get("REG", {})
    fr_activity = activity_stats.get("FRANCE", {})
    aav_comp = comp_stats.get("AAV2020", {})
    dep_comp = comp_stats.get("DEP", {})
    reg_comp = comp_stats.get("REG", {})
    fr_comp = comp_stats.get("FRANCE", {})

    # Map Eurostat NUTS-3 labels to department codes by normalized names.
    by_name = {norm(c["name"]): c["geoid"] for c in bounds["counties"]}
    aliases = {"cotedor": "cotedor", "corse": "corse", "valdoise": "valdoise"}
    nut_to_dep = {}
    for nut, label in eu["gdp_labels"].items():
        if not nut.startswith("FR") or len(nut) < 4:
            continue
        key = norm(label)
        dep = by_name.get(key)
        if dep:
            nut_to_dep[nut] = dep
    missing = [c["name"] for c in bounds["counties"] if c["geoid"] not in set(nut_to_dep.values())]
    print(f"    mapped {len(nut_to_dep)} Eurostat NUTS-3 units to departments; unmatched departments: {len(missing)}")

    gdp_mio = econ_rows(eu, "gdp", "MIO_EUR")
    gva_mio = econ_rows(eu, "gva", "CP_MEUR")
    emp_ths = econ_rows(eu, "employment", "THS", "EMP")

    def dep_values(table, dep, nace="TOTAL"):
        vals = [v for (nut, n), v in table.items() if n == nace and nut_to_dep.get(nut) == dep]
        return vals[0] if vals else None

    # Department population/area from communes.
    dep_pop = Counter()
    dep_area = Counter()
    dep_comms = defaultdict(list)
    for c in bounds["communes"]:
        dep_pop[c["department"]] += c.get("population") or 0
        dep_area[c["department"]] += (c.get("surface_ha") or 0) / 100
        dep_comms[c["department"]].append(c)

    def dep_jobs(dep):
        jobs = dict.fromkeys(INDUSTRIES, 0.0)
        total = 0.0
        for nace, weights in NACE_JOBS.items():
            val = dep_values(emp_ths, dep, nace)
            if val is None:
                continue
            total += val * 1000 if nace != "TOTAL" else 0
            for k, share in weights.items():
                jobs[k] += val * 1000 * share
        # TOTAL is more reliable than summing the apportioned high-level slices.
        emp = dep_values(emp_ths, dep, "TOTAL")
        return {k: round(v) if v else 0 for k, v in jobs.items()}, round((emp or 0) * 1000) if emp is not None else None

    dep_hazard = {}
    hazard_acc = {}
    commune_counts = Counter(c["department"] for c in bounds["communes"])
    for commune_code, row in hazards["communes"].items():
        dep = commune_code[:2]
        if dep not in counties_meta:
            continue
        acc = hazard_acc.setdefault(dep, Counter())
        acc["communes"] = commune_counts[dep]
        for key in ["events", "flood", "drought", "storm", "ground"]:
            acc[key] += row.get(key, 0)
    for dep, acc in hazard_acc.items():
        denom = max(1, acc["communes"])
        events = max(1, acc["events"])
        dep_hazard[dep] = {
            "frequency": acc["events"] / denom,
            "flood": acc["flood"] / events,
            "drought": acc["drought"] / events,
            "storm": acc["storm"] / events,
        }

    dep_election = {}
    dep_election_acc = {}
    for commune_code, row in elections["communes"].items():
        dep = commune_code[:2]
        if dep not in counties_meta:
            continue
        acc = dep_election_acc.setdefault(dep, Counter())
        acc.update(row)
    for dep, acc in dep_election_acc.items():
        dep_election[dep] = {
            "macron": acc["macron"] / acc["valid"] if acc["valid"] else None,
            "le_pen": acc["le_pen"] / acc["valid"] if acc["valid"] else None,
            "abstention": acc["abstentions"] / acc["registered"] if acc["registered"] else None,
            "registered": acc["registered"],
        }

    dep_econ = {}
    for dep in counties_meta:
        jobs, employed = dep_jobs(dep)
        direct = dep_employment.get(dep)
        if direct:
            jobs = census_jobs(direct)
            employed = round(sum(direct.get(code, 0) for code in A38_INDUSTRY))
        comp = dep_comp.get(dep, {})
        gdp = dep_values(gdp_mio, dep)
        dep_econ[dep] = {
            "_dep": dep,
            "population": comp.get("POP_2023") or dep_pop[dep] or None,
            "area": comp.get("SUP_2023") or dep_area[dep] or None,
            "jobs": jobs, "employed": employed,
            "gdp": gdp * 1e6 if gdp is not None else None,
            "median_income": comp.get("MED_SL_2023"), "poverty": (comp.get("PR_MD60_2023") or 0) / 100 if comp.get("PR_MD60_2023") is not None else None,
            "unemployment": unemployment_rate(dep_activity.get(dep)),
            "growth": pct_change(comp.get("POP_2023"), comp.get("POP_2017")), "growth_years": [2017, 2023],
            "pop_series": {str(y): v for y, v in comp_series(comp, "POP")},
        }

    # Regions.
    states = []
    for s in sorted(bounds["states"], key=lambda x: state_ids.index(x["fips"])):
        deps = [d for d, c in counties_meta.items() if c["state_fips"] == s["fips"]]
        agg = {"population": 0, "employed": 0, "gdp": 0, "jobs": Counter()}
        have_gdp = False
        for d in deps:
            e = dep_econ[d]
            agg["population"] += e["population"] or 0
            agg["employed"] += e["employed"] or 0
            if e["gdp"] is not None:
                agg["gdp"] += e["gdp"]
                have_gdp = True
            agg["jobs"].update(e["jobs"])
        jobs = dict(agg["jobs"])
        rcomp = reg_comp.get(s["fips"], {})
        yields = {
            "food": jobs.get("agriculture"), "production": round(jobs.get("manufacturing", 0) + jobs.get("construction", 0) + jobs.get("mining", 0)),
            "gold": agg["gdp"] if have_gdp else None, "science": round(jobs.get("professional", 0) + jobs.get("information", 0)), "culture": jobs.get("arts"),
        }
        states.append({
            "fips": s["fips"], "abbr": s["abbr"], "name": s["name"], "population": agg["population"] or None,
            "employed": agg["employed"] or None, "yields": yields, "jobs": jobs, "median_income": None, "median_rent": None,
            "home_value": None, "unemployment": unemployment_rate(reg_activity.get(s["fips"])), "rent_burden": None, "gdp": agg["gdp"] if have_gdp else None,
            "gdp_year": 2023,
            "median_income": rcomp.get("MED_SL_2023"),
            "poverty": (rcomp.get("PR_MD60_2023") or 0) / 100 if rcomp.get("PR_MD60_2023") is not None else None,
            "growth": (lambda v: round(v, 4) if v is not None else None)(pct_change(rcomp.get("POP_2023"), rcomp.get("POP_2017"))),
            "growth_years": [2017, 2023] if rcomp.get("POP_2023") and rcomp.get("POP_2017") else None,
            "pop_series": {str(y): v for y, v in comp_series(rcomp, "POP")}, "ranks": {}, "label": None,
            "land": None, "energy": None,
        })

    # Yield ranks and direct land-cover shares for every region.
    for key in ["food", "production", "gold", "science", "culture"]:
        ranked = sorted((s for s in states if s["yields"].get(key) is not None), key=lambda s: s["yields"][key], reverse=True)
        for rank, s in enumerate(ranked, 1):
            s["ranks"][key] = rank
    for si, s in enumerate(states):
        cells = [i for i, o in enumerate(world["owner"]) if o == si]
        land = {}
        totals = {i: sum(world["pct"][key][i] for key in ["forest", "crop", "pasture", "grass", "shrub", "wetland", "developed"]) or 100 for i in cells}
        for key in ["forest", "crop", "pasture", "grass", "shrub", "wetland", "developed"]:
            vals = [world["pct"][key][i] / totals[i] for i in cells]
            land[key] = round(sum(vals) / len(vals), 4) if vals else 0
        s["land"] = land

    # AAV composition and aggregate population/economy. GDP/jobs are department-level allocations.
    comp = defaultdict(list)
    for r in aav["composition"]:
        if r["commune"] in commune:
            comp[r["aav"]].append(r)
    city_rows = []
    for area in aav["areas"]:
        code = area["code"]
        if code == "000":
            continue
        members = [commune[r["commune"]] for r in comp.get(code, []) if r["commune"] in commune]
        metro_members = [c for c in members if c["region"] in region_abbr]
        if not metro_members:
            continue
        comp_row = aav_comp.get(code, {})
        pop = comp_row.get("POP_2023") or sum(c.get("population") or 0 for c in metro_members)
        direct = aav_employment.get(code)
        if direct:
            jobs = Counter(census_jobs(direct))
            employed = round(sum(direct.get(code0, 0) for code0 in A38_INDUSTRY))
            # GDP is still departmental. Allocate it by the AAV's share of workplace employment;
            # for multi-department aires, population weights split the AAV total between departments.
            gdp = 0.0
            dep_city_jobs = Counter()
            for c in metro_members:
                row = commune_employment.get(c["code"], {})
                dep_city_jobs[c["department"]] += sum(row.get(code0, 0) for code0 in A38_INDUSTRY)
            if sum(dep_city_jobs.values()) <= 0:
                dep_city_pop = Counter()
                for c in metro_members:
                    dep_city_pop[c["department"]] += c.get("population") or 0
                commune_pop_total = sum(dep_city_pop.values()) or pop or 1
                dep_city_jobs = Counter({dep: employed * (dp / commune_pop_total) for dep, dp in dep_city_pop.items()})
            for dep, jobs_in_dep in dep_city_jobs.items():
                e = dep_econ.get(dep, {})
                share = jobs_in_dep / (e.get("employed") or 1)
                gdp += (e.get("gdp") or 0) * share
        else:
            jobs = Counter()
            employed = 0
            gdp = 0.0
            for c in metro_members:
                e = dep_econ.get(c["department"], {})
                share = (c.get("population") or 0) / (dep_pop[c["department"]] or 1)
                for k, v in (e.get("jobs") or {}).items():
                    jobs[k] += v * share
                employed += (e.get("employed") or 0) * share
                gdp += (e.get("gdp") or 0) * share
        city_rows.append((pop, code, area, metro_members, dict(jobs), round(employed), gdp, comp_row, bool(direct)))
    # Keep every functional area of at least 50k people, plus enough smaller places to reach 160 cities.
    city_rows.sort(reverse=True, key=lambda x: x[0])
    selected = [r for r in city_rows if r[0] >= 50000]
    selected += [r for r in city_rows if r not in selected][: max(0, 160 - len(selected))]
    selected.sort(reverse=True, key=lambda x: x[0])

    used_cells = set()
    cities = []
    for pop, code, area, members, jobs, employed, gdp, comp_row, direct_jobs in selected:
        poles = [c for c in members if any(r["category"] in {"11", "12", "13"} for r in comp[code] if r["commune"] == c["code"])]
        centre = max(poles or members, key=lambda c: c.get("population") or 0)
        x, y = proj(centre["lon"], centre["lat"])
        cell = grid.cell_at(x, y)
        if cell < 0 or world["owner"][cell] < 0 or cell in used_cells:
            # Commune centroids can fall in a harbour or a foreign border hex. Put the banner on the
            # nearest French land hex instead of the original fallback (the first land hex on the map).
            def dist2(i):
                ix, iy = grid.center(*grid.col_row(i))
                return (ix - x) ** 2 + (iy - y) ** 2
            cell = min((i for i, o in enumerate(world["owner"]) if o >= 0 and i not in used_cells), key=dist2)
        used_cells.add(cell)
        deps = sorted({c["department"] for c in members})
        regions = sorted({region_abbr[c["region"]] for c in members if c["region"] in region_abbr})
        county_indexes = [county_ids.index(d) for d in deps if d in county_ids]
        cx, cy = grid.center(*grid.col_row(cell))
        candidates = [i for i in range(grid.size) if world["owner"][i] >= 0 and world["county"][i] in county_indexes]
        footprint = sorted(sorted(candidates, key=lambda i: (grid.center(*grid.col_row(i))[0] - cx) ** 2 + (grid.center(*grid.col_row(i))[1] - cy) ** 2)[:24])
        if cell not in footprint:
            footprint = sorted((footprint + [cell])[-24:])
        yields = {
            "food": round(jobs.get("agriculture", 0)), "production": round(jobs.get("manufacturing", 0) + jobs.get("construction", 0) + jobs.get("mining", 0)),
            "gold": round(gdp), "science": round(jobs.get("professional", 0) + jobs.get("information", 0)), "culture": round(jobs.get("arts", 0)),
        }
        cities.append({
            "id": code, "name": area["name"].split(" (partie")[0], "full": f"{area['name']} (aire d'attraction)",
            "states": regions, "metro": pop >= 200000, "capital": code == "001", "x": round(x, 1), "y": round(y, 1), "cell": cell,
            "population": pop, "employed": employed, "yields": yields, "jobs": {k: round(jobs.get(k, 0)) for k in INDUSTRIES},
            "median_income": comp_row.get("MED_SL_2023"), "median_rent": None, "home_value": None,
            "unemployment": unemployment_rate(aav_activity.get(code)), "rent_burden": None,
            "gdp": round(gdp), "gdp_year": 2023, "gdp_by_industry": {}, "gdp_estimated": list(INDUSTRIES), "gdp_undisclosed": None,
            "growth": (lambda v: round(v, 4) if v is not None else None)(pct_change(comp_row.get("POP_2023"), comp_row.get("POP_2017"))),
            "growth_years": [2017, 2023] if comp_row.get("POP_2023") and comp_row.get("POP_2017") else None,
            "poverty": (comp_row.get("PR_MD60_2023") or 0) / 100 if comp_row.get("PR_MD60_2023") is not None else None,
            "counties": deps, "pop_series": {str(y): v for y, v in comp_series(comp_row, "POP")}, "footprint": footprint,
            "ranks": {}, "peers": [],
        })
    # ranks and peers
    for metric in ["population", "gdp", "food", "production", "gold", "science", "culture"]:
        vals = [(c["yields"].get(metric) if metric in {"food","production","gold","science","culture"} else c.get(metric), c) for c in cities]
        vals = [(v, c) for v, c in vals if v is not None]
        vals.sort(reverse=True, key=lambda z: z[0])
        for rank, (_, c) in enumerate(vals, 1):
            c["ranks"][metric] = rank
    ranked_pc = sorted((c for c in cities if c.get("gdp") and c.get("population")), key=lambda c: c["gdp"] / c["population"], reverse=True)
    for rank, c in enumerate(ranked_pc, 1):
        c["ranks"]["gdp_per_capita"] = rank
    for c in cities:
        c["peers"] = [o["id"] for o in sorted((o for o in cities if o is not c), key=lambda o: abs(math.log((o["population"] or 1) / c["population"]))) [:5]]
    ranked_growth = sorted((c for c in cities if c.get("growth") is not None), key=lambda c: c["growth"], reverse=True)
    for rank, c in enumerate(ranked_growth, 1):
        c["ranks"]["growth"] = rank

    # Nation.
    nat_jobs = Counter()
    nat_pop = nat_emp = nat_gdp = 0
    for e in dep_econ.values():
        nat_pop += e["population"] or 0
        nat_emp += e["employed"] or 0
        nat_gdp += e["gdp"] or 0
        nat_jobs.update(e["jobs"])
    nj = dict(nat_jobs)
    fr_row = fr_employment.get("FM") or fr_employment.get("F") or {}
    if fr_row:
        nj = census_jobs(fr_row)
        nat_emp = round(sum(fr_row.get(code, 0) for code in A38_INDUSTRY))
    fr_c = fr_comp.get("FM") or fr_comp.get("F") or {}
    nation_obj = {
        "population": nat_pop, "employed": nat_emp, "jobs": nj,
        "yields": {"food": nj.get("agriculture"), "production": round(nj.get("manufacturing", 0)+nj.get("construction",0)+nj.get("mining",0)), "gold": nat_gdp, "science": round(nj.get("professional",0)+nj.get("information",0)), "culture": nj.get("arts")},
        "median_income": fr_c.get("MED_SL_2023"), "median_rent": None, "home_value": None,
        "unemployment": unemployment_rate(fr_activity.get("FM") or fr_activity.get("F")), "rent_burden": None,
        "poverty": (fr_c.get("PR_MD60_2023") or 0) / 100 if fr_c.get("PR_MD60_2023") is not None else None,
        "gdp": nat_gdp, "gdp_year": 2023,
        "growth": (lambda v: round(v, 4) if v is not None else None)(pct_change(fr_c.get("POP_2023"), fr_c.get("POP_2017"))),
        "growth_years": [2017, 2023] if fr_c.get("POP_2023") and fr_c.get("POP_2017") else None,
    }
    nation = {"vintage": "INSEE populations / Eurostat regional accounts 2023", "year": 2023, "gdp_vintage": "Eurostat nama_10r_3gdp, 2023", "nation": nation_obj, "yields": YIELDS, "industries": INDUSTRIES, "gdp_industries": {}}

    # Departments (counties contract).
    fields_def = [
        ("geoid", "Department", "text", None), ("name", "Name", "text", None), ("state", "Region", "text", None),
        ("population", "Population", "int", "people"), ("land_km2", "Land area", "km2", "km²"), ("density", "Density", "int", "people / km²"),
        ("gdp", "GDP", "eur", "euros per year"), ("gdp_per_capita", "GDP per capita", "eur", "euros"), ("employment", "Employment", "int", "people"),
        ("industry", "Industry share", "pct", "share of employment"), ("forest", "Forest", "pct", "share of land"), ("crop", "Cropland", "pct", "share of land"),
        ("developed", "Built-up", "pct", "share of land"), ("income", "Median standard of living", "eur", "euros per year"),
        ("poverty", "Poverty", "pct", "share of residents"), ("growth", "Population growth", "signed", "2017–2023"),
        ("homeownership", "Owner-occupied", "pct", "share of main homes"), ("second_homes", "Second homes", "pct", "share of dwellings"),
        ("vacancy", "Vacant homes", "pct", "share of dwellings"), ("cbsa", "Main AAV", "text", None), ("cell", "Map cell", "int", None),
    ]
    insee_fields = {"population", "land_km2", "density", "income", "poverty", "growth", "homeownership", "second_homes", "vacancy"}
    fields = [{"key": k, "label": lab, "format": fmt, "unit": unit, "higher_is": "neutral", "source": "fr_insee_stats" if k in insee_fields else "fr_eurostat", "description": ""} for k, lab, fmt, unit in fields_def]
    rows = []
    for idx, dep in enumerate(county_ids):
        meta = counties_meta[dep]
        e = dep_econ[dep]
        pop, area = e["population"], e["area"]
        emp = e["employed"]
        ind = None
        if emp:
            ind = (e["jobs"].get("manufacturing", 0)+e["jobs"].get("construction",0)+e["jobs"].get("mining",0)) / emp
        cells = [i for i, c in enumerate(world["county"]) if c == idx]
        cell = cells[len(cells)//2] if cells else None
        meanpct = {}
        for key in ["forest", "crop", "developed"]:
            vals = [world["pct"][key][i] / 100 for i in cells if world["pct"][key][i]]
            meanpct[key] = sum(vals)/len(vals) if vals else None
        # most populous AAV touching the department
        aa = max((c for c in cities if dep in c["counties"]), key=lambda c: c["population"], default=None)
        rows.append([dep, meta["name"], region_abbr[meta["state_fips"]], pop, round(area or 0,1), round(pop/area,1) if pop and area else None,
                     round(e["gdp"]) if e["gdp"] else None, round(e["gdp"]/pop) if e["gdp"] and pop else None, emp, round(ind,4) if ind is not None else None,
                     round(meanpct["forest"],4) if meanpct["forest"] is not None else None, round(meanpct["crop"],4) if meanpct["crop"] is not None else None,
                     round(meanpct["developed"],4) if meanpct["developed"] is not None else None,
                     e.get("median_income"), round(e.get("poverty"),4) if e.get("poverty") is not None else None,
                     round(e.get("growth"),4) if e.get("growth") is not None else None,
                     round(dep_comp.get(dep,{}).get("RP_PROP_2023",0)/dep_comp.get(dep,{}).get("RP_2023",1),4) if dep_comp.get(dep,{}).get("RP_2023") else None,
                     round(dep_comp.get(dep,{}).get("RSEC_2023",0)/dep_comp.get(dep,{}).get("LOG_2023",1),4) if dep_comp.get(dep,{}).get("LOG_2023") else None,
                     round(dep_comp.get(dep,{}).get("LVAC_2023",0)/dep_comp.get(dep,{}).get("LOG_2023",1),4) if dep_comp.get(dep,{}).get("LOG_2023") else None,
                     aa["id"] if aa else None, cell])
    counties_out = {"vintage": "geo.api.gouv.fr populations; Eurostat 2023", "fields": fields, "columns": [x[0] for x in fields_def], "rows": rows}

    # Lenses: department economics spread over hexes plus direct land-cover shares.
    county_lookup = {i: world["county"][i] for i in range(grid.size)}
    def dep_lens(fn, digits=3):
        vals=[]
        for i in range(grid.size):
            if world["owner"][i] < 0 or county_lookup[i] < 0: vals.append(None); continue
            dep=county_ids[county_lookup[i]]
            v=fn(dep_econ[dep])
            vals.append(round(v,digits) if v is not None else None)
        return vals
    def dep_comp_lens(fn, digits=4):
        vals=[]
        for i in range(grid.size):
            if world["owner"][i] < 0 or county_lookup[i] < 0: vals.append(None); continue
            dep=county_ids[county_lookup[i]]
            v=fn(dep_comp.get(dep, {}))
            vals.append(round(v,digits) if v is not None else None)
        return vals
    landvals=lambda key: [round(world["pct"][key][i]/100,3) if world["owner"][i]>=0 and world["pct"][key][i] else (0 if world["owner"][i]>=0 else None) for i in range(grid.size)]
    defs=[
      ("density","people","Population","👥","people / km²","int","log",dep_lens(lambda e: e["population"]/e["area"] if e["population"] and e["area"] else None,1),"Residents per km² of department land."),
      ("gdp_capita","prosperity","GDP per capita","💰","euros / resident","eur","linear",dep_lens(lambda e: e["gdp"]/e["population"] if e["gdp"] and e["population"] else None,0),"Department GDP divided by residents. Unlike the original US map, this is not household income."),
      ("employment_rate","people","Employment density","💼","workers / km²","int","log",dep_lens(lambda e: e["employed"]/e["area"] if e["employed"] and e["area"] else None,1),"Employment by workplace per km² of department land."),
      ("industry","prosperity","Industry","⚙️","share of employment","pct","linear",dep_lens(lambda e: (e["jobs"].get("manufacturing",0)+e["jobs"].get("construction",0)+e["jobs"].get("mining",0))/e["employed"] if e["employed"] else None,4),"Industry and construction employment as a share of all employment."),
      ("forest","land","Forest","🌲","share of land","pct","linear",landvals("forest"),"Share of each hex classified as tree cover by CORINE Land Cover."),
      ("farmland","land","Farmland","🌾","share of land","pct","linear",landvals("crop"),"Share of each hex classified as cropland by CORINE Land Cover."),
      ("developed","land","Built-up","🏙️","share of land","pct","linear",landvals("developed"),"Share of each hex classified as built-up by CORINE Land Cover."),
      ("income","prosperity","Median standard of living","💶","euros / year","eur","linear",dep_lens(lambda e: e.get("median_income"),0),"Median standard of living by department (INSEE comparateur de territoires 2023)."),
      ("poverty","prosperity","Poverty","📉","share of residents","pct","linear",dep_lens(lambda e: e.get("poverty"),4),"Share of residents below 60% of median standard of living."),
      ("unemployment","prosperity","Unemployment","🧭","share of labour force","pct","linear",dep_lens(lambda e: e.get("unemployment"),4),"Unemployed census residents aged 15–64 ÷ the active population aged 15–64."),
      ("growth","people","Population growth","📈","population change","signed","linear",dep_lens(lambda e: e.get("growth"),4),"Population change 2017–2023."),
      ("homeownership","prosperity","Homeownership","🏠","share of main homes","pct","linear",dep_comp_lens(lambda c: c.get("RP_PROP_2023",0)/c.get("RP_2023",1) if c.get("RP_2023") else None,4),"Owner-occupied share of main residences."),
      ("second_homes","land","Second homes","🏡","share of dwellings","pct","linear",dep_comp_lens(lambda c: c.get("RSEC_2023",0)/c.get("LOG_2023",1) if c.get("LOG_2023") else None,4),"Second homes and occasional dwellings as a share of all dwellings."),
      ("vacancy","land","Vacant homes","⬜","share of dwellings","pct","linear",dep_comp_lens(lambda c: c.get("LVAC_2023",0)/c.get("LOG_2023",1) if c.get("LOG_2023") else None,4),"Vacant dwellings as a share of all dwellings."),
      ("lepen_2022","politics","Le Pen vote 2022","🗳️","share of valid votes","pct","linear",dep_lens(lambda e: dep_election.get(e["_dep"],{}).get("le_pen") if "_dep" in e else None,4),"Marine Le Pen's share of valid second-round votes in the 2022 presidential election, aggregated from commune results to departments."),
      ("macron_2022","politics","Macron vote 2022","🗳️","share of valid votes","pct","linear",dep_lens(lambda e: dep_election.get(e["_dep"],{}).get("macron") if "_dep" in e else None,4),"Emmanuel Macron's share of valid second-round votes in the 2022 presidential election, aggregated from commune results to departments."),
      ("abstention_2022","politics","Abstention 2022","🗳️","share of registered voters","pct","linear",dep_lens(lambda e: dep_election.get(e["_dep"],{}).get("abstention") if "_dep" in e else None,4),"Abstentions as a share of registered voters in the 2022 presidential second round."),
      ("disasters","hazards","Natural disasters","🌊","recognitions / current commune since 2000","float","linear",dep_lens(lambda e: dep_hazard.get(e["_dep"],{}).get("frequency") if "_dep" in e else None,4),f"Catastrophe-naturelle recognitions in 2000–{hazards['years'][1]}, normalized by today's commune count. Retired-commune recognitions remain attributed to their department; this is administrative recognition frequency, not measured damage."),
      ("flood_events","hazards","Flood events","💧","share of recognitions","pct","linear",dep_lens(lambda e: dep_hazard.get(e["_dep"],{}).get("flood") if "_dep" in e else None,4),"Flood, mudflow, wave and groundwater-rise recognitions as a share of local catastrophe-naturelle recognitions since 2000."),
      ("drought_events","hazards","Drought events","🏜️","share of recognitions","pct","linear",dep_lens(lambda e: dep_hazard.get(e["_dep"],{}).get("drought") if "_dep" in e else None,4),"Drought recognitions as a share of local catastrophe-naturelle recognitions since 2000."),
    ]
    lenses=[]
    ramps={"hazards":["#102a43","#2f6690","#7fb3d5","#f4d35e","#d95d39"],"politics":["#253858","#5f6f95","#b7c0d8","#e9c46a","#c36d3d"],"people":["#1b1035","#4b2377","#9a3b8a","#e0645e","#f9b24a","#fff3a8"],"prosperity":["#152238","#274b73","#3d8395","#72ba8c","#d6ec91"],"land":["#27351f","#476c35","#7f9d4b","#c5bd69","#eee4a1"]}
    for lid,group,name,emoji,unit,fmt,scale,vals,desc in defs:
      lo,hi=percentile(vals,2),percentile(vals,98)
      if lo is None or hi is None:
        continue
      lenses.append({"id":lid,"group":group,"name":name,"icon":"l-people" if lid=="density" else lid,"emoji":emoji,"unit":unit,"format":fmt,"scale":scale,"domain":[lo,hi],"ramp":ramps[group],"higher_is":"neutral","source":"fr_eurostat" if lid in {"density","gdp_capita","employment_rate","industry"} else ("fr_corine" if lid in {"forest","farmland","developed"} else ("fr_elections" if lid.endswith("_2022") else ("fr_hazards" if lid in {"disasters","flood_events","drought_events"} else "fr_insee_stats"))),"description":desc,"values":vals})
    lens_out={"vintage":"geo.api.gouv.fr / Eurostat 2023 / CORINE Land Cover 2018","groups":[{"id":"people","name":"People"},{"id":"prosperity","name":"Prosperity"},{"id":"land","name":"Land and housing"},{"id":"politics","name":"Elections"},{"id":"hazards","name":"Natural hazards"}],"lenses":lenses}

    write_web("cities.json", cities)
    write_web("states.json", states)
    write_web("nation.json", nation)
    write_web("counties.json", counties_out)
    write_web("lenses.json", lens_out)
