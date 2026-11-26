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
    assert len(w["owner"]) == len(w["county"]) == len(w["water"]) == len(w["france_share"]) == n
    assert all(0 <= x <= 1 for x in w["france_share"])
    assert any(0 < x < 1 for x in w["france_share"])
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
    assert all(c["homeownership"] is not None and c["second_homes"] is not None and c["vacancy"] is not None for c in cities)
    assert {x["key"] for x in nation["yields"]} == {"food", "production", "gold", "science", "culture"}
    assert {x["id"] for x in lenses["lenses"]} >= {"density", "gdp_capita", "forest", "farmland", "developed", "higher_education", "seniors", "immigration", "public_transit", "car_commuting"}
    assert len(lenses["lenses"][0]["values"]) == len(web("world.json")["owner"])
    counties = web("counties.json")
    ci = counties["columns"].index("cell")
    assert all(isinstance(r[ci], int) and 0 <= r[ci] < len(web("world.json")["owner"]) for r in counties["rows"])
    assert next(r for r in counties["rows"] if r[0] == "92")[ci] is not None
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
    carnavalet = next(w for w in museums if "Carnavalet" in w["name"])
    assert carnavalet["metrics"]["visits"] == 1_624_576
    assert carnavalet["metrics"]["sites"] == 3
    assert universities[0]["name"] == "Université de Lille"
    assert universities[0]["metrics"]["students"] > 80_000
    assert {w["name"] for w in universities} >= {"Université de Lorraine", "Université Grenoble Alpes"}
    assert all(w["cell"] is not None and w["state"] for w in museums + universities)
    assert [w["metrics"]["visits"] for w in museums] == sorted((w["metrics"]["visits"] for w in museums), reverse=True)
    assert [w["metrics"]["students"] for w in universities] == sorted((w["metrics"]["students"] for w in universities), reverse=True)
    assert any(s["id"] == "fr_culture" for s in web("sources.json"))


def test_museum_attendance_parser_deduplicates_sites(tmp_path, monkeypatch):
    from pipeline.sources.fr_culture import FrenchCulture

    (tmp_path / "museofile.csv").write_text(
        "Identifiant|Nom_officiel|AUTNOM|Ville|Coordonnees|Domaine_thematique|URL\n"
        "M1|Test museum||Paris|48.8,2.3|History|example.fr\n",
        encoding="utf-8",
    )
    (tmp_path / "museum-attendance.csv").write_text(
        "IDPatrimostat;IDMuseofile;ferme;annee;total\n"
        "S1;M1;NON;2024;100\n"
        "S1;M1;NON;2024;120\n"
        "S2;M1;NON;2024;30\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(FrenchCulture, "raw_dir", property(lambda self: tmp_path))
    rows, year = FrenchCulture().museums()
    assert year == 2024
    assert rows[0]["visits"] == 150
    assert rows[0]["sites"] == 2


def test_commune_search_index_contract():
    data = web("communes.json")
    cols = {k: i for i, k in enumerate(data["columns"])}
    rows = data["communes"]
    assert len(rows) > 34_000
    assert cols["code"] == cols["name"] - 1
    paris = next(r for r in rows if r[cols["code"]] == "75056")
    assert paris[cols["name"]] == "Paris"
    assert paris[cols["population"]] > 2_000_000
    assert all(len(r) == len(data["columns"]) for r in rows[:100])
    assert paris[cols["median_income"]] > 20_000
    assert 0 < paris[cols["macron_share"]] < 1
    assert paris[cols["density"]] > 10_000
    assert rows == sorted(rows, key=lambda r: (-r[cols["population"]], r[cols["name"]], r[cols["code"]]))
    assert data["sources"] == ["fr_boundaries", "fr_insee_stats", "fr_elections", "fr_hazards"]
    assert data["hazard_years"][0] == 2000 and data["hazard_years"][1] >= 2024
    assert 0 < paris[cols["owner_share"]] < 1
    assert paris[cols["hazard_events"]] >= 0
    terval = next(r for r in rows if r[cols["code"]] == "85289")
    assert terval[cols["hazard_events"]] == 15  # 9 under Terval + 6 under pre-merger Breuil-Barret


def test_hazard_commune_resolver_stops_at_current_communes():
    from pipeline.sources.fr_hazards import commune_resolver

    current = [
        {"TYPECOM": "COM", "COM": "76095", "COMPARENT": ""},
        {"TYPECOM": "COM", "COM": "76108", "COMPARENT": ""},
        {"TYPECOM": "COM", "COM": "12218", "COMPARENT": ""},
        {"TYPECOM": "COMD", "COM": "12076", "COMPARENT": "12218"},
    ]
    movements = [
        {"DATE_EFF": "2012-01-01", "MOD": "32", "TYPECOM_AP": "COM", "COM_AV": "76095", "COM_AP": "76108"},
        {"DATE_EFF": "2014-01-01", "MOD": "21", "TYPECOM_AP": "COM", "COM_AV": "76108", "COM_AP": "76095"},
        {"DATE_EFF": "2014-01-01", "MOD": "21", "TYPECOM_AP": "COM", "COM_AV": "76108", "COM_AP": "76108"},
        {"DATE_EFF": "2016-01-01", "MOD": "32", "TYPECOM_AP": "COM", "COM_AV": "12114", "COM_AP": "12076"},
        {"DATE_EFF": "2016-01-01", "MOD": "32", "TYPECOM_AP": "COM", "COM_AV": "12218", "COM_AP": "12076"},
        {"DATE_EFF": "2024-03-04", "MOD": "50", "TYPECOM_AP": "COM", "COM_AV": "12076", "COM_AP": "12218"},
    ]
    resolve = commune_resolver(current, movements)
    assert resolve("76095") == "76095"  # Bihorel is current again; do not follow its obsolete merger
    assert resolve("12114") == "12218"  # Grand-Vabre reaches current Conques-en-Rouergue without cycling


def test_citizens_contract():
    data = web("citizens.json")
    paris = data["cities"]["001"]
    assert data["sources"] == ["fr_insee_stats"]
    assert len(data["cities"]) >= 170
    assert set(data["groups"]) == {"workforce", "age", "commute", "education", "nativity"}
    for row_id, n in data["figures"].items():
        row = paris[row_id]
        assert row is not None
        keys = [g["key"] for g in data["groups"][row_id]]
        assert set(row["counts"]) == set(keys)
        assert sum(row["counts"].values()) == row["total"]
        assert sum(row["figures"].values()) == n
        assert all(0 <= row["shares"][k] <= 1 for k in keys)
    assert paris["commute"]["shares"]["transit"] > data["national"]["commute"]["shares"]["transit"]
    assert paris["education"]["bachelors_plus"] > data["national"]["education"]["bachelors_plus"]
    assert 0 < paris["nativity"]["foreign_born"] < 1
    assert paris["workforce"] is not None
    assert sum(paris["workforce"]["figures"].values()) == 20
    assert paris["specialists"]


def test_military_contract():
    data = web("military.json")
    rows = data["installations"]
    assert data["sources"] == ["fr_military"]
    assert len(rows) == 50
    assert data["ranges"] == []
    assert not data["national"]["unmatched_bases"]
    assert data["national"]["published_total"] == 251_063
    assert data["national"]["personnel"]["total"] > 250_000
    toulon = next(r for r in rows if r["id"] == "base-toulon")
    assert toulon["personnel"] == 23_120 and toulon["tier"] == "major"
    assert toulon["seat_commune"] == "Toulon" and toulon["aav"] == "018"
    assert all(r["area_km2"] is None and r["cells"] is None for r in rows)
    assert all(r["component"] == "other" and r["joint"] for r in rows)
    paris = data["cities"]["001"]
    assert paris["aggregate_included"] and paris["tier"] == "fortress"
    assert data["cities"]["018"]["armed_forces"] == 23_120
    assert data["states"]["IDF"]["ile_de_france_aggregate"] == 20_131
    assert any(s["id"] == "fr_military" for s in web("sources.json"))
