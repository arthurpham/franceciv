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
    assert {x["id"] for x in lenses["lenses"]} >= {"density", "gdp_capita", "forest", "farmland", "developed", "higher_education", "seniors", "immigration", "public_transit", "car_commuting"}
    assert len(lenses["lenses"][0]["values"]) == len(web("world.json")["owner"])
    by_id = {x["id"]: x for x in lenses["lenses"]}
    assert "out-of-school" in by_id["higher_education"]["unit"]
    # Known Paris (department 75) census ratios, rounded to the four decimals written by the builder.
    expected = {"higher_education": 0.6593, "seniors": 0.1768, "immigration": 0.2122, "public_transit": 0.6108, "car_commuting": 0.0898}
    world = web("world.json")
    paris_county = next(i for i, c in enumerate(world["counties"]) if c["geoid"] == "75")
    paris_cells = [i for i, c in enumerate(world["county"]) if c == paris_county and world["owner"][i] >= 0]
    assert paris_cells
    for lid, want in expected.items():
        assert all(abs(by_id[lid]["values"][i] - want) < 0.00005 for i in paris_cells), lid


def test_hex_grid_index_round_trip():
    g = HexGrid(8, 98, 107)
    i = g.index(42, 17)
    assert g.col_row(i) == (42, 17)


def test_resource_postprocessor_cache_invariants():
    """The resources builder patches states.json, then writes resources.json last.

    This ordering is what lets the mtime-based build cache treat resources.json as newer
    than its states.json input while still rebuilding after france_core refreshes states.
    """
    from pipeline.build import resources

    src = (ROOT / "pipeline" / "build" / "resources.py").read_text()
    assert "states.json" in resources.REQUIRES
    assert src.index('write_web("states.json"') < src.index('write_web("resources.json"')
    states = web("states.json")
    assert states and all(s.get("energy") is not None for s in states)
    assert sum((s["energy"] or {}).get("total", 0) > 0 for s in states) == 12


def test_freight_trade_contract_uses_french_units():
    trade = web("trade.json")
    assert trade["sources"] == ["fr_freight"]
    assert trade["year"] == 2019
    assert len(trade["routes"]) == 40
    assert len(trade["zones"]) == 13
    assert all("value_musd" not in r for r in trade["routes"])
    assert all(r["volume_mtkm"] > 0 and len(r["path"]) >= 2 for r in trade["routes"])
    assert trade["routes"] == sorted(trade["routes"], key=lambda r: r["rank"])
    assert trade["national_mtkm"]["domestic"] >= sum(r["volume_mtkm"] for r in trade["routes"])
    assert {m["id"] for m in trade["modes"]} == {"truck", "rail", "water"}
    assert any(s["id"] == "fr_freight" for s in web("sources.json"))
    assert sum("001" in z["cities"] for z in trade["zones"]) == 1  # Paris belongs to the banner region only
    assert min(sum(r["modes"].values()) for r in trade["routes"]) > 0.999
    assert any(r.get("rail_suppressed") for r in trade["routes"])


def test_culture_wonders_contract():
    wonders = web("wonders.json")
    rows = wonders["wonders"]
    assert wonders["sources"] == ["fr_unesco", "fr_culture"]
    museums = [w for w in rows if w["rule"] == "museum_attendance"]
    universities = [w for w in rows if w["rule"] == "university_enrolment"]
    assert len(museums) == len(universities) == 12
    assert museums[0]["name"] == "musée du Louvre"
    assert museums[0]["metrics"]["visits"] > 8_000_000
    assert universities[0]["name"] == "Université de Lille"
    assert universities[0]["metrics"]["students"] > 80_000
    assert all(w["cell"] is not None and w["state"] for w in museums + universities)
    assert [w["metrics"]["visits"] for w in museums] == sorted((w["metrics"]["visits"] for w in museums), reverse=True)
    assert [w["metrics"]["students"] for w in universities] == sorted((w["metrics"]["students"] for w in universities), reverse=True)
    assert any(s["id"] == "fr_culture" for s in web("sources.json"))
