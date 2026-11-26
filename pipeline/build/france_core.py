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

REQUIRES = ["_world", "fr_boundaries", "fr_aav", "fr_eurostat"]
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
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    states_meta = load_interim_payload_states = None
    counties_meta = {c["geoid"]: c for c in bounds["counties"]}
    commune = {c["code"]: c for c in bounds["communes"]}
    county_ids = world["counties"]
    state_ids = world["states"]
    region_abbr = {s["fips"]: s["abbr"] for s in bounds["states"]}
    region_name = {s["fips"]: s["name"] for s in bounds["states"]}

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

    dep_econ = {}
    for dep in counties_meta:
        jobs, employed = dep_jobs(dep)
        gdp = dep_values(gdp_mio, dep)
        dep_econ[dep] = {
            "population": dep_pop[dep] or None, "area": dep_area[dep] or None, "jobs": jobs, "employed": employed,
            "gdp": gdp * 1e6 if gdp is not None else None,
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
        yields = {
            "food": jobs.get("agriculture"), "production": round(jobs.get("manufacturing", 0) + jobs.get("construction", 0) + jobs.get("mining", 0)),
            "gold": agg["gdp"] if have_gdp else None, "science": round(jobs.get("professional", 0) + jobs.get("information", 0)), "culture": jobs.get("arts"),
        }
        states.append({
            "fips": s["fips"], "abbr": s["abbr"], "name": s["name"], "population": agg["population"] or None,
            "employed": agg["employed"] or None, "yields": yields, "jobs": jobs, "median_income": None, "median_rent": None,
            "home_value": None, "unemployment": None, "rent_burden": None, "gdp": agg["gdp"] if have_gdp else None,
            "gdp_year": 2023, "growth": None, "growth_years": None, "ranks": {}, "label": None,
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
        pop = sum(c.get("population") or 0 for c in metro_members)
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
        city_rows.append((pop, code, area, metro_members, dict(jobs), round(employed), gdp))
    # Keep every functional area of at least 50k people, plus enough smaller places to reach 160 cities.
    city_rows.sort(reverse=True, key=lambda x: x[0])
    selected = [r for r in city_rows if r[0] >= 50000]
    selected += [r for r in city_rows if r not in selected][: max(0, 160 - len(selected))]
    selected.sort(reverse=True, key=lambda x: x[0])

    used_cells = set()
    cities = []
    for pop, code, area, members, jobs, employed, gdp in selected:
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
            "median_income": None, "median_rent": None, "home_value": None, "unemployment": None, "rent_burden": None,
            "gdp": round(gdp), "gdp_year": 2023, "gdp_by_industry": {}, "gdp_estimated": list(INDUSTRIES), "gdp_undisclosed": None,
            "growth": None, "growth_years": None, "counties": deps, "pop_series": None, "footprint": footprint,
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
        c["ranks"]["growth"] = None
        c["peers"] = [o["id"] for o in sorted((o for o in cities if o is not c), key=lambda o: abs(math.log((o["population"] or 1) / c["population"]))) [:5]]

    # Nation.
    nat_jobs = Counter()
    nat_pop = nat_emp = nat_gdp = 0
    for e in dep_econ.values():
        nat_pop += e["population"] or 0
        nat_emp += e["employed"] or 0
        nat_gdp += e["gdp"] or 0
        nat_jobs.update(e["jobs"])
    nj = dict(nat_jobs)
    nation_obj = {
        "population": nat_pop, "employed": nat_emp, "jobs": nj,
        "yields": {"food": nj.get("agriculture"), "production": round(nj.get("manufacturing", 0)+nj.get("construction",0)+nj.get("mining",0)), "gold": nat_gdp, "science": round(nj.get("professional",0)+nj.get("information",0)), "culture": nj.get("arts")},
        "median_income": None, "median_rent": None, "home_value": None, "unemployment": None, "rent_burden": None,
        "gdp": nat_gdp, "gdp_year": 2023, "growth": None, "growth_years": None,
    }
    nation = {"vintage": "INSEE populations / Eurostat regional accounts 2023", "year": 2023, "gdp_vintage": "Eurostat nama_10r_3gdp, 2023", "nation": nation_obj, "yields": YIELDS, "industries": INDUSTRIES, "gdp_industries": {}}

    # Departments (counties contract).
    fields_def = [
        ("geoid", "Department", "text", None), ("name", "Name", "text", None), ("state", "Region", "text", None),
        ("population", "Population", "int", "people"), ("land_km2", "Land area", "km2", "km²"), ("density", "Density", "int", "people / km²"),
        ("gdp", "GDP", "eur", "euros per year"), ("gdp_per_capita", "GDP per capita", "eur", "euros"), ("employment", "Employment", "int", "people"),
        ("industry", "Industry share", "pct", "share of employment"), ("forest", "Forest", "pct", "share of land"), ("crop", "Cropland", "pct", "share of land"),
        ("developed", "Built-up", "pct", "share of land"), ("cbsa", "Main AAV", "text", None), ("cell", "Map cell", "int", None),
    ]
    fields = [{"key": k, "label": lab, "format": fmt, "unit": unit, "higher_is": "neutral", "source": "fr_eurostat", "description": ""} for k, lab, fmt, unit in fields_def]
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
                     round(meanpct["developed"],4) if meanpct["developed"] is not None else None, aa["id"] if aa else None, cell])
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
    landvals=lambda key: [round(world["pct"][key][i]/100,3) if world["owner"][i]>=0 and world["pct"][key][i] else (0 if world["owner"][i]>=0 else None) for i in range(grid.size)]
    defs=[
      ("density","people","Population","👥","people / km²","int","log",dep_lens(lambda e: e["population"]/e["area"] if e["population"] and e["area"] else None,1),"Residents per km² of department land."),
      ("gdp_capita","prosperity","GDP per capita","💰","euros / resident","eur","linear",dep_lens(lambda e: e["gdp"]/e["population"] if e["gdp"] and e["population"] else None,0),"Department GDP divided by residents. Unlike the original US map, this is not household income."),
      ("employment_rate","people","Employment density","💼","workers / km²","int","log",dep_lens(lambda e: e["employed"]/e["area"] if e["employed"] and e["area"] else None,1),"Employment by workplace per km² of department land."),
      ("industry","prosperity","Industry","⚙️","share of employment","pct","linear",dep_lens(lambda e: (e["jobs"].get("manufacturing",0)+e["jobs"].get("construction",0)+e["jobs"].get("mining",0))/e["employed"] if e["employed"] else None,4),"Industry and construction employment as a share of all employment."),
      ("forest","land","Forest","🌲","share of land","pct","linear",landvals("forest"),"Share of each hex classified as tree cover by ESA WorldCover."),
      ("farmland","land","Farmland","🌾","share of land","pct","linear",landvals("crop"),"Share of each hex classified as cropland by ESA WorldCover."),
      ("developed","land","Built-up","🏙️","share of land","pct","linear",landvals("developed"),"Share of each hex classified as built-up by ESA WorldCover."),
    ]
    lenses=[]
    ramps={"people":["#1b1035","#4b2377","#9a3b8a","#e0645e","#f9b24a","#fff3a8"],"prosperity":["#152238","#274b73","#3d8395","#72ba8c","#d6ec91"],"land":["#27351f","#476c35","#7f9d4b","#c5bd69","#eee4a1"]}
    for lid,group,name,emoji,unit,fmt,scale,vals,desc in defs:
      lo,hi=percentile(vals,2),percentile(vals,98)
      lenses.append({"id":lid,"group":group,"name":name,"icon":"l-people" if lid=="density" else lid,"emoji":emoji,"unit":unit,"format":fmt,"scale":scale,"domain":[lo,hi],"ramp":ramps[group],"higher_is":"neutral","source":"fr_eurostat" if lid in {"density","gdp_capita","employment_rate","industry"} else "fr_worldcover","description":desc,"values":vals})
    lens_out={"vintage":"geo.api.gouv.fr / Eurostat 2023 / ESA WorldCover 2021","groups":[{"id":"people","name":"People"},{"id":"prosperity","name":"Prosperity"},{"id":"land","name":"Land"}],"lenses":lenses}

    write_web("cities.json", cities)
    write_web("states.json", states)
    write_web("nation.json", nation)
    write_web("counties.json", counties_out)
    write_web("lenses.json", lens_out)
