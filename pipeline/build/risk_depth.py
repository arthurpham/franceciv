"""Technological-risk, transport-noise and background air-quality lenses."""

import math
from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.insets import transform_real_point
from ..core.store import load_interim, write_web
from .connectivity import nearest_land, shape_weights
from .risk import sample_layer
from .time_dimension import land_area_by_cell

REQUIRES = ["_world", "fr_boundaries", "fr_noise", "fr_air_quality", "fr_risk_perimeters"]
PRODUCES = ["risk_depth.json"]
RAMP = ["#23243d", "#4e4f78", "#756a76", "#a77a56", "#d69a3d"]
AIR_RAMP = ["#20364b", "#326b78", "#5b9a70", "#b5b75e", "#e0a33f"]


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def positive_domain(vals):
    positive = [v for v in vals if v]
    return [0, percentile(positive, 98) or max(positive or [0])]


def parent_code(code):
    if code.startswith("751"):
        return "75056"
    if code.startswith("132") and len(code) == 5:
        return "13055"
    if code.startswith("6938"):
        return "69123"
    return code


def lens(lens_id, name, emoji, unit, vals, desc, source, ramp=RAMP, share=False):
    return {
        "id": lens_id, "group": "hazards", "name": name, "icon": lens_id, "emoji": emoji,
        "unit": unit, "format": "pct" if share else "float", "scale": "linear",
        "domain": positive_domain(vals) if share else [percentile(vals, 2), percentile(vals, 98)],
        "ramp": ramp, "higher_is": "worse", "source": source, "description": desc, "values": vals,
    }


def combine_air_communes(rows):
    grouped = defaultdict(list)
    for raw_code, row in rows.items():
        grouped[parent_code(raw_code)].append(row)
    combined = {}
    for code, members in grouped.items():
        out = {}
        for pollutant in ("no2", "pm10", "pm25"):
            vals = [row[pollutant] for row in members if row.get(pollutant) is not None]
            if vals:
                out[pollutant] = sum(vals) / len(vals)
        combined[code] = out
    return combined


def build():
    world = load_interim("_world")
    boundaries = load_interim("fr_boundaries")
    noise = load_interim("fr_noise")
    air = load_interim("fr_air_quality")
    perimeters = load_interim("fr_risk_perimeters")
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    real_land_area = land_area_by_cell(world, grid)

    noise_acc = defaultdict(lambda: defaultdict(float))
    noise_unmatched = 0.0
    for dep in noise["departments"]:
        for kind, area, high_area, lon, lat in noise["cells"].get(dep, []):
            map_x, map_y = proj(*transform_real_point(lon, lat))
            cell = nearest_land(world, grid, map_x, map_y)
            if cell < 0 or world["owner"][cell] < 0:
                noise_unmatched += area
                continue
            noise_acc[(cell, kind)]["all"] += area
            noise_acc[(cell, kind)]["high"] += high_area

    missing_noise_deps = set(noise.get("missing_departments", []))
    road_share, road_high_share, rail_share, rail_high_share = [], [], [], []
    for i in range(grid.size):
        owner = world["owner"][i]
        dep = world["counties"][world["county"][i]] if owner >= 0 and world["county"][i] >= 0 else None
        land = real_land_area[i]
        if owner < 0 or dep in missing_noise_deps or not land:
            road_share.append(None); road_high_share.append(None); rail_share.append(None); rail_high_share.append(None)
            continue
        road = noise_acc[(i, 0)]
        rail = noise_acc[(i, 1)]
        road_share.append(round(road["all"] / 1e6 / land, 6))
        road_high_share.append(round(road["high"] / 1e6 / land, 6))
        rail_share.append(round(rail["all"] / 1e6 / land, 6))
        rail_high_share.append(round(rail["high"] / 1e6 / land, 6))

    weights_by_commune = shape_weights(world, grid, proj, boundaries["communes"])
    air_acc = defaultdict(lambda: defaultdict(float))
    air_den = defaultdict(lambda: defaultdict(float))
    air_communes = combine_air_communes(air["communes"])
    for code, row in air_communes.items():
        weights = weights_by_commune.get(code)
        if not weights:
            continue
        for cell, weight in weights.items():
            for pollutant, value in row.items():
                air_acc[pollutant][cell] += value * weight
                air_den[pollutant][cell] += weight
    air_vals = {}
    for pollutant in ("no2", "pm10", "pm25"):
        vals = []
        for i in range(grid.size):
            den = air_den[pollutant].get(i, 0)
            vals.append(round(air_acc[pollutant][i] / den, 3) if den else None)
        air_vals[pollutant] = vals

    raster = {k: perimeters[k] for k in ["x0", "dx", "y0", "dy", "cols"]}
    industrial = sample_layer(world, grid, proj, raster | {"rows": perimeters["layers"]["industrial"]})
    noise_note = " Type-A Lden polygons are aggregated approximately in 250 m bins and then assigned to map hexes; values are modelled exposure within the regulatory infrastructure scope, not measurements at a façade or total environmental noise."
    air_note = " Values are commune-level annual mean background concentrations from measurements combined with CHIMERE modelling, distributed approximately over commune polygons. They do not characterize local peaks near traffic or industry; overseas territories are outside coverage. Arrondissement rows are averaged to their parent commune before distribution."

    lenses = [
        lens("industrial_risk_perimeter", "Industrial-risk perimeter", "🏭", "share of hex area", industrial, "Approximate share of hex area inside official industrial-risk prevention servitude perimeters (SUP industrial risk). These administrative prevention perimeters indicate regulated technological-risk areas, not accident probability or expected damage. Coverage follows the metropolitan Géorisques raster grid.", "fr_risk_perimeters", share=True),
        lens("road_noise_exposure", "Major-road noise", "🚗", "share of land area", road_share, "Share of real land area modelled at Lden 55 dB(A) or higher around qualifying non-conceded roads in the 2022 strategic noise maps. Concessionaire motorways, urban-agglomeration noise, airports and industry are outside this layer; Paris and the three inner-ring departments are absent from the source." + noise_note, "fr_noise", share=True),
        lens("intense_road_noise", "Intense road noise", "🔊", "share of land area", road_high_share, "Share of real land area modelled at Lden 65 dB(A) or higher around qualifying non-conceded roads in the 2022 strategic noise maps. This stricter threshold highlights the most exposed corridors but remains limited to the source's infrastructure scope." + noise_note, "fr_noise", share=True),
        lens("rail_noise_exposure", "Major-rail noise", "🚆", "share of land area", rail_share, "Share of real land area modelled at Lden 55 dB(A) or higher around qualifying railways in the 2022 strategic noise maps. Urban-agglomeration noise, airports and industry are outside this layer; Paris and the three inner-ring departments are absent from the source." + noise_note, "fr_noise", share=True),
        lens("intense_rail_noise", "Intense rail noise", "🚄", "share of land area", rail_high_share, "Share of real land area modelled at Lden 65 dB(A) or higher around qualifying railways in the 2022 strategic noise maps. This stricter threshold highlights the most exposed rail corridors but remains limited to the source's infrastructure scope." + noise_note, "fr_noise", share=True),
        lens("nitrogen_dioxide", "Nitrogen dioxide", "🌫️", "µg/m³ annual mean", air_vals["no2"], f"Annual mean background nitrogen-dioxide concentration in {air.get('year')}. Higher values generally indicate more combustion-related urban and traffic-influenced background pollution." + air_note, "fr_air_quality", ramp=AIR_RAMP),
        lens("fine_particles", "Fine particles PM2.5", "🌁", "µg/m³ annual mean", air_vals["pm25"], f"Annual mean background PM2.5 concentration in {air.get('year')}. Fine particles are a major long-term health-relevant air pollutant." + air_note, "fr_air_quality", ramp=AIR_RAMP),
        lens("coarse_particles", "Particles PM10", "💨", "µg/m³ annual mean", air_vals["pm10"], f"Annual mean background PM10 concentration in {air.get('year')}. Values represent regional/urban background particulate pollution rather than short regulatory exceedance episodes." + air_note, "fr_air_quality", ramp=AIR_RAMP),
    ]
    write_web("risk_depth.json", {
        "version": 1,
        "vintage": f"CEREMA noise {noise.get('year')}; INERIS air {air.get('year')}; Géorisques industrial-risk perimeters, current publication",
        "sources": ["fr_noise", "fr_air_quality", "fr_risk_perimeters"],
        "group": {"id": "hazards", "name": "Hazards"},
        "noise_polygon_count": noise.get("polygon_count"),
        "noise_area_km2": noise.get("area_km2"),
        "unmatched_noise_area_km2": round(noise_unmatched / 1e6, 3),
        "noise_missing_departments": sorted(missing_noise_deps),
        "lenses": lenses,
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "risk_depth.json").read_text())
    assert len(doc["lenses"]) == 8
    by_id = {lens["id"]: lens for lens in doc["lenses"]}
    for lens_id in ("road_noise_exposure", "rail_noise_exposure"):
        vals = [v for v in by_id[lens_id]["values"] if v is not None]
        positive = [v for v in vals if v]
        assert len(vals) > 2500 and len(positive) > 200 and max(vals) < 0.5
    for lens_id in ("nitrogen_dioxide", "fine_particles", "coarse_particles"):
        vals = [v for v in by_id[lens_id]["values"] if v is not None]
        assert len(vals) > 2500 and max(vals) > 8
    industrial = [v for v in by_id["industrial_risk_perimeter"]["values"] if v is not None]
    assert len(industrial) > 2500 and len([v for v in industrial if v]) > 50
    assert doc["noise_polygon_count"] > 200000
    return [("PASS", f"risk_depth.json: technological, noise and air-quality lenses over {len(industrial)} cells")]
