"""Smoke tests for the France MVP data spine."""

import json
from pathlib import Path

from pipeline.core.geo import Albers, MapProjection
from pipeline.core.hexgrid import HexGrid

ROOT = Path(__file__).resolve().parents[1]


def web(name):
    return json.load(open(ROOT / "web" / "data" / name, encoding="utf-8"))


def test_projection_round_trip():
    a = Albers()
    lon, lat = 2.3522, 48.8566
    assert a.inverse(*a(lon, lat)) == (lon, lat) or abs(a.inverse(*a(lon, lat))[0] - lon) < 1e-9


def test_committed_world_contract():
    w = web("world.json")
    n = w["grid"]["cols"] * w["grid"]["rows"]
    assert len(w["owner"]) == len(w["county"]) == len(w["water"]) == n
    assert len(w["states"]) == 13
    assert len(w["counties"]) == 96
    assert 9000 < n < 12000


def test_committed_france_core_contract():
    cities = web("cities.json")
    nation = web("nation.json")
    lenses = web("lenses.json")
    assert len(cities) >= 150
    paris = next(c for c in cities if c["id"] == "001")
    assert paris["name"] == "Paris"
    assert paris["population"] > 10_000_000
    assert paris["gdp"] > 500e9
    assert nation["nation"]["gdp"] > 2e12
    assert {x["key"] for x in nation["yields"]} == {"food", "production", "gold", "science", "culture"}
    assert {x["id"] for x in lenses["lenses"]} >= {"density", "gdp_capita", "forest", "farmland", "developed"}
    assert len(lenses["lenses"][0]["values"]) == len(web("world.json")["owner"])


def test_hex_grid_index_round_trip():
    g = HexGrid(8, 98, 107)
    i = g.index(42, 17)
    assert g.col_row(i) == (42, 17)
