"""Climate lenses from Météo-France's SIM2 grid."""

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web

REQUIRES = ["_world", "fr_climate"]
PRODUCES = ["climate.json"]

RAMP = ["#253858", "#3d6d93", "#62a1a5", "#f2d16b", "#d95f43"]


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    if not xs:
        return None
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))]


def aggregate(world, climate):
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    acc = defaultdict(lambda: {"n": 0, "temperature": 0.0, "warming": 0.0, "rainfall": 0.0, "rain_change": 0.0, "water_deficit": 0.0})
    for lon, lat, t, w, r, rc, wd in zip(
        climate["lon"], climate["lat"], climate["temperature"], climate["warming"], climate["rainfall"], climate["rain_change"], climate["water_deficit"]
    ):
        x, y = proj(lon, lat)
        cell = grid.cell_at(x, y)
        if cell < 0 or world["owner"][cell] < 0:
            continue
        a = acc[cell]
        a["n"] += 1
        a["temperature"] += t
        a["warming"] += w
        a["rainfall"] += r
        if rc is not None:
            a["rain_change"] += rc
        a["water_deficit"] += wd
    out = {}
    for key in ["temperature", "warming", "rainfall", "rain_change", "water_deficit"]:
        vals = []
        for i in range(grid.size):
            a = acc.get(i)
            vals.append(round(a[key] / a["n"], 4) if a and a["n"] else None)
        out[key] = vals
    return out, acc


def lens(lens_id, name, emoji, unit, fmt, vals, description):
    return {
        "id": lens_id,
        "group": "climate",
        "name": name,
        "icon": lens_id,
        "emoji": emoji,
        "unit": unit,
        "format": fmt,
        "scale": "linear",
        "domain": [percentile(vals, 2), percentile(vals, 98)],
        "ramp": RAMP,
        "higher_is": "neutral",
        "source": "fr_climate",
        "description": description,
        "values": vals,
    }


def build():
    world = load_interim("_world")
    climate = load_interim("fr_climate")
    vals, acc = aggregate(world, climate)
    periods = climate["periods"]
    lenses = [
        lens("temperature", "Temperature", "🌡️", "°C", "float", vals["temperature"],
             f"Mean annual temperature, {periods['normal'][0]}–{periods['normal'][1]} climate normal from the Météo-France SIM2 reanalysis."),
        lens("warming", "Warming", "🔥", "°C", "float", vals["warming"],
             f"Difference between mean annual temperature in {periods['recent'][0]}–{periods['recent'][1]} and {periods['baseline'][0]}–{periods['baseline'][1]}."),
        lens("rainfall", "Rainfall", "🌧️", "mm / year", "float", vals["rainfall"],
             f"Mean annual precipitation, {periods['normal'][0]}–{periods['normal'][1]} climate normal from the SIM2 reanalysis."),
        lens("rainfall_change", "Rainfall change", "💧", "change in annual precipitation", "signed", vals["rain_change"],
             f"Change in mean annual precipitation between {periods['recent'][0]}–{periods['recent'][1]} and {periods['baseline'][0]}–{periods['baseline'][1]}."),
        lens("water_deficit", "Climatic water deficit", "🏜️", "mm / year", "float", vals["water_deficit"],
             f"Mean annual potential evapotranspiration minus total precipitation, {periods['normal'][0]}–{periods['normal'][1]}. Positive values indicate a climatic moisture deficit before soil storage, irrigation, runoff and groundwater are considered."),
    ]
    write_web("climate.json", {
        "version": 1,
        "vintage": "Météo-France SIM2 monthly reanalysis, 1961–2025",
        "sources": ["fr_climate"],
        "group": {"id": "climate", "name": "Climate"},
        "grid_points": len(climate["lon"]),
        "covered_cells": len(acc),
        "lenses": lenses,
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "climate.json").read_text())
    assert len(doc["lenses"]) == 5
    assert all(len(l["values"]) for l in doc["lenses"])
    assert doc["covered_cells"] > 2500
    return [("PASS", f"climate.json: 5 lenses over {doc['covered_cells']} cells")]
