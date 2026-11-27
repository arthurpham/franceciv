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

REQUIRES = ["_world", "fr_boundaries", "fr_insee_stats"]
PRODUCES = ["time.json"]

RAMP_PEOPLE = ["#1b1035", "#4b2377", "#9a3b8a", "#e0645e", "#f9b24a", "#fff3a8"]
RAMP_LAND = ["#27351f", "#476c35", "#7f9d4b", "#c5bd69", "#eee4a1"]
POP_YEARS = [1968, 1975, 1982, 1990, 1999, 2007, 2012, 2017, 2023]
HOUSING_YEARS = [2012, 2017, 2023]
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


def temporal_lens(lens_id, group, name, emoji, unit, fmt, scale, series, years, ramp, description, positive_log=False):
    flat = [v for vals in series.values() for v in vals if v is not None and (not positive_log or v > 0)]
    lo, hi = percentile(flat, 2), percentile(flat, 98)
    default = years[-1]
    return {
        "id": lens_id, "group": group, "name": name, "icon": lens_id, "emoji": emoji, "unit": unit,
        "format": fmt, "scale": scale, "domain": [lo, hi], "ramp": ramp, "higher_is": "neutral",
        "source": "fr_insee_stats", "description": description,
        "values": series[str(default)],
        "time": {"label": "Census year", "years": years, "default": default, "series": series},
    }


def build():
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    stats = load_interim("fr_insee_stats")
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

    method = ("INSEE comparateur commune values are distributed across current commune polygons on a 1 km lattice, "
              "assuming a uniform distribution inside each commune, with a centroid fallback for very small or sparsely sampled polygons; colour scales stay fixed across years. "
              "Overseas inset display areas are converted back to ground area using each territory's affine scale. "
              "Missing or suppressed commune values make the affected hexes null rather than zero.")
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
    ]

    write_web("time.json", {
        "version": 1,
        "vintage": f"{load_interim_payload('fr_insee_stats').get('vintage')}; historical population and housing series",
        "sources": ["fr_insee_stats"],
        "methodology": {
            "spatial_distribution": "1 km lattice over current commune polygons; uniform within each commune",
            "sample_step_km": SAMPLE_STEP_KM,
            "inset_display_area_over_real_area": {dep: round(lonlat_area(PARAMS[dep]["target"]) / lonlat_area(real_inverse_bounds(PARAMS[dep])), 6) for dep in PARAMS},
            "population_years": POP_YEARS,
            "housing_years": HOUSING_YEARS,
        },
        "lenses": lenses,
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "time.json").read_text())
    world = json.loads((web_dir / "world.json").read_text())
    n = len(world["owner"])
    assert len(doc["lenses"]) == 5
    for lens in doc["lenses"]:
        time_meta = lens["time"]
        assert time_meta["default"] == time_meta["years"][-1]
        assert len(lens["values"]) == n
        assert set(time_meta["series"]) == {str(y) for y in time_meta["years"]}
        assert all(len(vals) == n for vals in time_meta["series"].values())
        assert all(v is None or v >= 0 for vals in time_meta["series"].values() for v in vals)
    pop = next(l for l in doc["lenses"] if l["id"] == "population_history")
    vals68 = [v for v in pop["time"]["series"]["1968"] if v is not None]
    vals23 = [v for v in pop["time"]["series"]["2023"] if v is not None]
    assert len(vals68) > 2500 and len(vals23) > 2500
    assert sum(vals23) / len(vals23) > sum(vals68) / len(vals68)
    return [("PASS", "time.json: five temporal population/housing lenses with complete year series")]
