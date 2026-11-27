"""Historical population and housing time-series lenses.

The INSEE comparateur already publishes several census/vintage years on a current
commune geography. This builder turns those commune rows into hex time series. Values
are distributed across each commune polygon on a 1 km lattice, which is much less
distorting than putting the whole commune at its centroid, while still assuming a
uniform distribution inside the commune.
"""

from __future__ import annotations

import math
from collections import defaultdict

from ..core.geo import R_EARTH_KM, MapProjection, Shape
from ..core.hexgrid import HexGrid
from ..core.insets import PARAMS, REGION_TO_DEP, real_inverse_bounds
from ..core.store import load_interim, load_interim_payload, write_web
from .connectivity import nearest_land

REQUIRES = ["_world", "fr_boundaries", "fr_insee_stats", "fr_elections", "fr_housing_history", "fr_climate", "fr_migration"]
PRODUCES = ["time.json"]

RAMP_PEOPLE = ["#1b1035", "#4b2377", "#9a3b8a", "#e0645e", "#f9b24a", "#fff3a8"]
RAMP_LAND = ["#27351f", "#476c35", "#7f9d4b", "#c5bd69", "#eee4a1"]
RAMP_POLITICS = ["#253858", "#5f6f95", "#b7c0d8", "#e9c46a", "#c36d3d"]
RAMP_CLIMATE = ["#253858", "#3d6d93", "#62a1a5", "#f2d16b", "#d95f43"]
RAMP_QUALITY = ["#2d213f", "#58508d", "#4f86a8", "#62b58f", "#f0d264"]
POP_YEARS = [1968, 1975, 1982, 1990, 1999, 2007, 2012, 2017, 2023]
HOUSING_YEARS = [2012, 2017, 2023]
ELECTION_YEARS = [2017, 2022]
MIGRATION_YEARS = [2012, 2017, 2023]
SAMPLE_STEP_KM = 1.0


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * p / 100
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] if lo == hi else xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def shape_weights(world, grid, proj, communes):
    """Normalized hex weights for every commune, approximating land-area overlap at 1 km."""
    out = {}
    fallback = 0
    for c in communes:
        counts = defaultdict(int)
        shape = Shape([[proj(lon, lat) for lon, lat in ring] for ring in c.get("rings", [])])
        if shape.rings:
            x0, y0, x1, y1 = shape.bbox
            x = math.floor(x0 / SAMPLE_STEP_KM) * SAMPLE_STEP_KM + SAMPLE_STEP_KM / 2
            while x <= x1:
                y = math.floor(y0 / SAMPLE_STEP_KM) * SAMPLE_STEP_KM + SAMPLE_STEP_KM / 2
                while y <= y1:
                    if shape.contains(x, y):
                        cell = grid.cell_at(x, y)
                        if cell >= 0 and world["owner"][cell] >= 0:
                            counts[cell] += 1
                    y += SAMPLE_STEP_KM
                x += SAMPLE_STEP_KM
        if not counts and c.get("lon") is not None:
            fallback += 1
            cell = nearest_land(world, grid, *proj(c["lon"], c["lat"]))
            if cell >= 0 and world["owner"][cell] >= 0:
                counts[cell] = 1
        total = sum(counts.values())
        if total:
            out[c["code"]] = {cell: n / total for cell, n in counts.items()}
    print(f"    commune spatial weights: {len(out)} communes, {fallback} centroid fallbacks")
    return out


def aggregate_measure(rows, weights, measure, years):
    sums = {y: defaultdict(float) for y in years}
    incomplete = {y: set() for y in years}
    for code, weights_by_cell in weights.items():
        row = rows.get(code) or {}
        for y in years:
            value = row.get(f"{measure}_{y}")
            if value is None:
                incomplete[y].update(weights_by_cell)
                continue
            for cell, weight in weights_by_cell.items():
                sums[y][cell] += value * weight
    return sums, incomplete


def lonlat_area(bounds):
    """Spherical ground area of a lon/lat rectangle, matching the spherical Albers projection."""
    x0, y0, x1, y1 = bounds
    return R_EARTH_KM ** 2 * math.radians(abs(x1 - x0)) * abs(math.sin(math.radians(y1)) - math.sin(math.radians(y0)))


def inset_area_scales():
    """Displayed inset ground area divided by the territory's real ground area."""
    scales = {}
    for region, dep in REGION_TO_DEP.items():
        spec = PARAMS[dep]
        real_area = lonlat_area(real_inverse_bounds(spec))
        scales[region] = lonlat_area(spec["target"]) / real_area if real_area else 1.0
    return scales


def land_area_by_cell(world, grid):
    hex_area = 1.5 * math.sqrt(3) * grid.radius ** 2
    scales = inset_area_scales()
    out = []
    for i in range(grid.size):
        samples = world["county_samples"][i]
        land_share = sum(1 for k in samples if k >= 0) / len(samples) if samples else 1.0
        owner = world["owner"][i]
        region = world["states"][owner] if owner >= 0 else None
        out.append(hex_area * land_share / scales.get(region, 1.0))
    return out


def density_series(world, grid, totals, incomplete, years, digits=1):
    areas = land_area_by_cell(world, grid)
    series = {}
    for y in years:
        vals = []
        for i in range(grid.size):
            if world["owner"][i] < 0 or i in incomplete[y] or not areas[i]:
                vals.append(None)
            else:
                vals.append(round(totals[y].get(i, 0) / areas[i], digits))
        series[str(y)] = vals
    return series


def ratio_series(world, grid, numer, numer_missing, denom, denom_missing, years):
    series = {}
    for y in years:
        bad = numer_missing[y] | denom_missing[y]
        vals = []
        for i in range(grid.size):
            d = denom[y].get(i, 0)
            if world["owner"][i] < 0 or i in bad or not d:
                vals.append(None)
            else:
                vals.append(round(numer[y].get(i, 0) / d, 4))
        series[str(y)] = vals
    return series


def aggregate_nested_measure(rows, weights, measure, years):
    """Aggregate commune rows shaped as rows[code][year][measure]."""
    sums = {y: defaultdict(float) for y in years}
    incomplete = {y: set() for y in years}
    for code, weights_by_cell in weights.items():
        by_year = rows.get(code) or {}
        for y in years:
            value = (by_year.get(str(y)) or {}).get(measure)
            if value is None:
                incomplete[y].update(weights_by_cell)
                continue
            for cell, weight in weights_by_cell.items():
                sums[y][cell] += value * weight
    return sums, incomplete


def department_from_commune(code):
    if code.startswith(("971", "972", "973", "974", "976")):
        return code[:3]
    return code[:2]


def election_series(world, grid, elections, years, numerator, denominator):
    """Department-level vote ratios from commune result counts."""
    departments = {}
    for y in years:
        acc = defaultdict(lambda: defaultdict(float))
        for code, row in elections["history"].get(str(y), {}).items():
            dep = department_from_commune(code)
            for key in (numerator, denominator):
                acc[dep][key] += row.get(key) or 0
        departments[y] = acc

    series = {}
    for y in years:
        vals = []
        for i in range(grid.size):
            county = world["county"][i]
            dep = world["counties"][county] if county >= 0 else None
            row = departments[y].get(dep) if dep else None
            denom = row.get(denominator, 0) if row else 0
            vals.append(round(row[numerator] / denom, 4) if row and denom else None)
        series[str(y)] = vals
    return series


def weighted_price_series(world, grid, rows, weights, years, min_weighted_sales=5):
    """Transaction-count-weighted mean of commune median prices, distributed over commune polygons."""
    totals = {y: defaultdict(float) for y in years}
    weights_out = {y: defaultdict(float) for y in years}
    for code, cells in weights.items():
        by_year = rows.get(code) or {}
        for y in years:
            row = by_year.get(str(y)) or {}
            price, sales = row.get("price"), row.get("sales")
            if price is None or not sales:
                continue
            for cell, spatial_weight in cells.items():
                w = sales * spatial_weight
                totals[y][cell] += price * w
                weights_out[y][cell] += w
    series = {}
    for y in years:
        vals = []
        for i in range(grid.size):
            w = weights_out[y].get(i, 0)
            vals.append(int(round(totals[y][i] / w)) if world["owner"][i] >= 0 and w >= min_weighted_sales else None)
        series[str(y)] = vals
    return series


def climate_series(world, grid, proj, climate, measure, years, digits):
    """Average SIM2 grid-point annual values inside each hex."""
    acc = {y: defaultdict(lambda: [0.0, 0]) for y in years}
    arrays = {y: climate[measure][str(y)] for y in years}
    for idx, (lon, lat) in enumerate(zip(climate["lon"], climate["lat"])):
        cell = grid.cell_at(*proj(lon, lat))
        if cell < 0 or world["owner"][cell] < 0:
            continue
        for y in years:
            value = arrays[y][idx] if idx < len(arrays[y]) else None
            if value is None:
                continue
            acc[y][cell][0] += value
            acc[y][cell][1] += 1
    series = {}
    for y in years:
        vals = []
        for i in range(grid.size):
            total, count = acc[y].get(i, [0.0, 0])
            vals.append(round(total / count, digits) if count else None)
        series[str(y)] = vals
    return series


def temporal_lens(lens_id, group, name, emoji, unit, fmt, scale, series, years, ramp, description, positive_log=False, source="fr_insee_stats", time_label="Census year"):
    flat = [v for vals in series.values() for v in vals if v is not None and (not positive_log or v > 0)]
    lo, hi = percentile(flat, 2), percentile(flat, 98)
    default = years[-1]
    return {
        "id": lens_id, "group": group, "name": name, "icon": lens_id, "emoji": emoji, "unit": unit,
        "format": fmt, "scale": scale, "domain": [lo, hi], "ramp": ramp, "higher_is": "neutral",
        "source": source, "description": description,
        "values": series[str(default)],
        "time": {"label": time_label, "years": years, "default": default, "series": series},
    }


def build():
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    stats = load_interim("fr_insee_stats")
    elections = load_interim("fr_elections")
    housing_history = load_interim("fr_housing_history")
    climate = load_interim("fr_climate")
    migration = load_interim("fr_migration")
    rows = stats["comparateur"]["COM"]
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    weights = shape_weights(world, grid, proj, bounds["communes"])

    pop, pop_missing = aggregate_measure(rows, weights, "POP", POP_YEARS)
    dwellings, dwellings_missing = aggregate_measure(rows, weights, "LOG", HOUSING_YEARS)
    main_homes, main_missing = aggregate_measure(rows, weights, "RP", HOUSING_YEARS)
    owner_homes, owner_missing = aggregate_measure(rows, weights, "RP_PROP", HOUSING_YEARS)
    second_homes, second_missing = aggregate_measure(rows, weights, "RSEC", HOUSING_YEARS)
    vacant, vacant_missing = aggregate_measure(rows, weights, "LVAC", HOUSING_YEARS)

    population_series = density_series(world, grid, pop, pop_missing, POP_YEARS)
    dwelling_series = density_series(world, grid, dwellings, dwellings_missing, HOUSING_YEARS)
    ownership_series = ratio_series(world, grid, owner_homes, owner_missing, main_homes, main_missing, HOUSING_YEARS)
    second_series = ratio_series(world, grid, second_homes, second_missing, dwellings, dwellings_missing, HOUSING_YEARS)
    vacancy_series = ratio_series(world, grid, vacant, vacant_missing, dwellings, dwellings_missing, HOUSING_YEARS)

    migration_rows = migration["communes"]
    mig_total, mig_total_missing = aggregate_nested_measure(migration_rows, weights, "total", MIGRATION_YEARS)
    mig_other, mig_other_missing = aggregate_nested_measure(migration_rows, weights, "other_commune", MIGRATION_YEARS)
    mig_outside, mig_outside_missing = aggregate_nested_measure(migration_rows, weights, "outside_department", MIGRATION_YEARS)
    mobility_series = ratio_series(world, grid, mig_other, mig_other_missing, mig_total, mig_total_missing, MIGRATION_YEARS)
    outside_migration_series = ratio_series(world, grid, mig_outside, mig_outside_missing, mig_total, mig_total_missing, MIGRATION_YEARS)

    price_years = housing_history["years"]
    price_series = weighted_price_series(world, grid, housing_history["communes"], weights, price_years)
    climate_years = climate["annual_years"]
    temperature_series = climate_series(world, grid, proj, climate, "annual_temperature", climate_years, 2)
    rainfall_series = climate_series(world, grid, proj, climate, "annual_rainfall", climate_years, 1)
    deficit_series = climate_series(world, grid, proj, climate, "annual_water_deficit", climate_years, 1)
    lepen_series = election_series(world, grid, elections, ELECTION_YEARS, "le_pen", "valid")
    macron_series = election_series(world, grid, elections, ELECTION_YEARS, "macron", "valid")
    abstention_series = election_series(world, grid, elections, ELECTION_YEARS, "abstentions", "registered")

    method = ("INSEE comparateur commune values are distributed across current commune polygons on a 1 km lattice, "
              "assuming a uniform distribution inside each commune, with a centroid fallback for very small or sparsely sampled polygons; colour scales stay fixed across years. "
              "Overseas inset display areas are converted back to ground area using each territory's affine scale. "
              "Missing or suppressed commune values make the affected hexes null rather than zero.")
    migration_method = ("INSEE census-weighted commune counts are distributed across current commune polygons on a 1 km lattice, "
                        "assuming uniform residence within each commune. These are gross one-year residential moves, not net migration balances. "
                        "Missing or suppressed commune values make the affected hexes null rather than zero; colour scales stay fixed across years.")
    election_method = ("Definitive commune vote counts are summed to departments, then shown at every hex in the department. "
                       "Both runoffs opposed Emmanuel Macron and Marine Le Pen, so vote shares are directly comparable; colour scales stay fixed across years.")
    price_method = ("Terralyse commune medians are distributed over current commune polygons on a 1 km lattice and combined as a transaction-count-weighted mean, "
                    "not as a true hex-level median. Hex estimates based on fewer than five spatially allocated sales are suppressed, matching the source's minimum-sale publication threshold. Sparse commune coverage reflects too few usable sales and is null rather than zero. "
                    "DVF excludes Alsace-Moselle and Mayotte. Municipal-arrondissement detail for Paris, Lyon and Marseille begins in 2021, so those parent communes are null in earlier years; colour scales stay fixed across years.")
    climate_method = ("SIM2 reanalysis grid points are averaged inside each hex over metropolitan France. These are individual weather-year snapshots, "
                      "not climate normals, so year-to-year variability is part of the measurement; overseas departments are outside SIM2 coverage. Colour scales stay fixed across years.")

    lenses = [
        temporal_lens("population_history", "people", "Population history", "👥", "people / km²", "int", "log",
                      population_series, POP_YEARS, RAMP_PEOPLE,
                      "Residents per km² in nine census snapshots from 1968 to 2023. Zero values clamp to the bottom of the log colour scale. " + method, positive_log=True),
        temporal_lens("housing_stock_history", "land", "Housing stock history", "🏘️", "dwellings / km²", "float", "log",
                      dwelling_series, HOUSING_YEARS, RAMP_LAND,
                      "Total dwellings per km² in the 2012, 2017 and 2023 census snapshots. Zero values clamp to the bottom of the log colour scale. " + method, positive_log=True),
        temporal_lens("homeownership_history", "land", "Homeownership history", "🏠", "share of main homes", "pct", "linear",
                      ownership_series, HOUSING_YEARS, RAMP_LAND,
                      "Owner-occupied main residences as a share of all main residences in 2012, 2017 and 2023. " + method),
        temporal_lens("second_homes_history", "land", "Second-home history", "🏡", "share of dwellings", "pct", "linear",
                      second_series, HOUSING_YEARS, RAMP_LAND,
                      "Second homes and occasional dwellings as a share of all dwellings in 2012, 2017 and 2023. " + method),
        temporal_lens("vacancy_history", "land", "Vacancy history", "⬜", "share of dwellings", "pct", "linear",
                      vacancy_series, HOUSING_YEARS, RAMP_LAND,
                      "Vacant dwellings as a share of all dwellings in 2012, 2017 and 2023. " + method),
        temporal_lens("lepen_history", "politics", "Le Pen vote history", "🗳️", "share of valid votes", "pct", "linear",
                      lepen_series, ELECTION_YEARS, RAMP_POLITICS,
                      "Marine Le Pen's share of valid second-round votes in the 2017 and 2022 presidential elections. " + election_method,
                      source="fr_elections", time_label="Election year"),
        temporal_lens("macron_history", "politics", "Macron vote history", "🗳️", "share of valid votes", "pct", "linear",
                      macron_series, ELECTION_YEARS, RAMP_POLITICS,
                      "Emmanuel Macron's share of valid second-round votes in the 2017 and 2022 presidential elections. " + election_method,
                      source="fr_elections", time_label="Election year"),
        temporal_lens("abstention_history", "politics", "Abstention history", "🗳️", "share of registered voters", "pct", "linear",
                      abstention_series, ELECTION_YEARS, RAMP_POLITICS,
                      "Abstentions as a share of registered voters in the 2017 and 2022 presidential second rounds. " + election_method,
                      source="fr_elections", time_label="Election year"),
        temporal_lens("housing_price_history", "quality", "Housing-price history", "💶", "euros / m²", "eur", "linear",
                      price_series, price_years, RAMP_QUALITY,
                      "Median sale price per m² of dwellings sold in each year from 2014 to 2025. " + price_method,
                      source="fr_housing_history", time_label="Sale year"),
        temporal_lens("residential_mobility_history", "society", "Residential mobility history", "🧭", "share of residents aged 1+", "pct", "linear",
                      mobility_series, MIGRATION_YEARS, RAMP_PEOPLE,
                      "Residents aged one year or more who lived in another commune one year earlier, as a share of all residents aged one year or more, in the 2012, 2017 and 2023 censuses. " + migration_method,
                      source="fr_migration"),
        temporal_lens("interdepartmental_migration_history", "society", "Interdepartmental in-migration history", "🧳", "share of residents aged 1+", "pct", "linear",
                      outside_migration_series, MIGRATION_YEARS, RAMP_PEOPLE,
                      "Residents aged one year or more whose previous residence was outside their current department, as a share of all residents aged one year or more, in the 2012, 2017 and 2023 censuses. " + migration_method,
                      source="fr_migration"),
        temporal_lens("temperature_history", "climate", "Temperature history", "🌡️", "°C", "float", "linear",
                      temperature_series, climate_years, RAMP_CLIMATE,
                      "Mean annual temperature in the 1985, 1995, 2005, 2015 and 2025 SIM2 reanalysis years. " + climate_method,
                      source="fr_climate", time_label="Reanalysis year"),
        temporal_lens("rainfall_history", "climate", "Rainfall history", "🌧️", "mm / year", "float", "linear",
                      rainfall_series, climate_years, RAMP_CLIMATE,
                      "Total annual precipitation in the 1985, 1995, 2005, 2015 and 2025 SIM2 reanalysis years. " + climate_method,
                      source="fr_climate", time_label="Reanalysis year"),
        temporal_lens("water_deficit_history", "climate", "Water-deficit history", "🏜️", "mm / year", "float", "linear",
                      deficit_series, climate_years, RAMP_CLIMATE,
                      "Annual potential evapotranspiration minus precipitation in the 1985, 1995, 2005, 2015 and 2025 SIM2 reanalysis years. Positive values indicate climatic moisture deficit before soil storage, irrigation, runoff and groundwater are considered. " + climate_method,
                      source="fr_climate", time_label="Reanalysis year"),
    ]

    write_web("time.json", {
        "version": 1,
        "vintage": "; ".join([
            f"{load_interim_payload('fr_insee_stats').get('vintage')}; historical population and housing series",
            str(load_interim_payload('fr_elections').get('vintage')),
            str(load_interim_payload('fr_housing_history').get('vintage')),
            str(load_interim_payload('fr_climate').get('vintage')),
            str(load_interim_payload('fr_migration').get('vintage')),
        ]),
        "sources": ["fr_insee_stats", "fr_elections", "fr_housing_history", "fr_climate", "fr_migration"],
        "methodology": {
            "spatial_distribution": "1 km lattice over current commune polygons; uniform within each commune",
            "sample_step_km": SAMPLE_STEP_KM,
            "inset_display_area_over_real_area": {dep: round(lonlat_area(PARAMS[dep]["target"]) / lonlat_area(real_inverse_bounds(PARAMS[dep])), 6) for dep in PARAMS},
            "population_years": POP_YEARS,
            "housing_years": HOUSING_YEARS,
            "election_years": ELECTION_YEARS,
            "housing_price_years": price_years,
            "migration_years": MIGRATION_YEARS,
            "climate_years": climate_years,
        },
        "lenses": lenses,
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "time.json").read_text())
    world = json.loads((web_dir / "world.json").read_text())
    n = len(world["owner"])
    expected = {
        "population_history", "housing_stock_history", "homeownership_history", "second_homes_history", "vacancy_history",
        "lepen_history", "macron_history", "abstention_history", "housing_price_history",
        "residential_mobility_history", "interdepartmental_migration_history",
        "temperature_history", "rainfall_history", "water_deficit_history",
    }
    assert {l["id"] for l in doc["lenses"]} == expected
    for lens in doc["lenses"]:
        time_meta = lens["time"]
        assert time_meta["default"] == time_meta["years"][-1]
        assert len(lens["values"]) == n
        assert set(time_meta["series"]) == {str(y) for y in time_meta["years"]}
        assert all(len(vals) == n for vals in time_meta["series"].values())
        assert all(v is None or isinstance(v, (int, float)) for vals in time_meta["series"].values() for v in vals)
    pop = next(l for l in doc["lenses"] if l["id"] == "population_history")
    vals68 = [v for v in pop["time"]["series"]["1968"] if v is not None]
    vals23 = [v for v in pop["time"]["series"]["2023"] if v is not None]
    assert len(vals68) > 2500 and len(vals23) > 2500
    assert sum(vals23) / len(vals23) > sum(vals68) / len(vals68)
    price = next(l for l in doc["lenses"] if l["id"] == "housing_price_history")
    assert price["time"]["years"] == list(range(2014, 2026))
    assert min(sum(v is not None for v in vals) for vals in price["time"]["series"].values()) > 2000
    election = next(l for l in doc["lenses"] if l["id"] == "lepen_history")
    assert election["time"]["years"] == [2017, 2022]
    assert all(sum(v is not None for v in vals) > 3900 for vals in election["time"]["series"].values())
    deficit = next(l for l in doc["lenses"] if l["id"] == "water_deficit_history")
    flat = [v for vals in deficit["time"]["series"].values() for v in vals if v is not None]
    assert min(flat) < 0 < max(flat)
    return [("PASS", "time.json: 14 temporal population, housing, election, price, migration and climate lenses")]
