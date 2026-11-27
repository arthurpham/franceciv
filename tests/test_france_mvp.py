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
    assert len(w["states"]) == 18
    assert {s["abbr"] for s in w["states"] if s.get("inset")} == {"GUA", "MTQ", "GUY", "REU", "MAY"}
    assert len(w["insets"]) == 5
    assert len(w["counties"]) == 101
    assert 9000 < n < 18000


def test_committed_france_core_contract():
    cities = web("cities.json")
    nation = web("nation.json")
    lenses = web("lenses.json")
    assert len(cities) >= 650
    paris = next(c for c in cities if c["id"] == "001")
    assert paris["name"] == "Paris"
    assert paris["population"] > 10_000_000
    assert paris["gdp"] > 500e9
    assert nation["nation"]["gdp"] > 2e12
    assert nation["nation"]["gdp_year"] == 2024
    assert "workplace employment" in next(y for y in nation["yields"] if y["key"] == "gold")["description"]
    assert all(c["homeownership"] is not None and c["second_homes"] is not None and c["vacancy"] is not None for c in cities if "976" not in c["counties"])
    assert any("976" in c["counties"] for c in cities)  # Mayotte is mapped; INSEE comparateur housing coverage is absent there.
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


def test_climate_and_hydrography_contracts():
    climate = web("climate.json")
    assert climate["covered_cells"] > 2500
    assert {l["id"] for l in climate["lenses"]} == {"temperature", "warming", "rainfall", "rainfall_change", "water_deficit", "water_deficit_change"}
    n = len(web("world.json")["owner"])
    for lens in climate["lenses"]:
        vals = [v for v in lens["values"] if v is not None]
        assert len(lens["values"]) == n
        assert len(vals) > 2500
    warming = next(l for l in climate["lenses"] if l["id"] == "warming")
    assert sum(v for v in warming["values"] if v is not None) / len([v for v in warming["values"] if v is not None]) > 0.5
    hydro = web("hydrography.json")
    assert len(hydro["rivers"]) > 1000
    assert any(r["name"] == "la Seine" for r in hydro["rivers"])


def test_connectivity_contracts():
    connectivity = web("connectivity.json")
    assert connectivity["covered_cells"] > 2500
    lens = connectivity["lenses"][0]
    assert lens["id"] == "fiber"
    vals = [v for v in lens["values"] if v is not None]
    assert len(vals) == connectivity["covered_cells"]
    assert all(0 <= v <= 1 for v in vals)
    ev = connectivity["lenses"][1]
    ev_vals = [v for v in ev["values"] if v is not None]
    assert ev["id"] == "ev_charging" and len(ev_vals) > 2500 and max(ev_vals) > 50
    assert connectivity["sources"] == ["fr_broadband", "fr_ev_charging", "fr_mobile_network"]
    mobile = next(l for l in connectivity["lenses"] if l["id"] == "mobile_operators")
    fiveg = next(l for l in connectivity["lenses"] if l["id"] == "mobile_5g")
    mv = [v for v in mobile["values"] if v is not None]
    fv = [v for v in fiveg["values"] if v is not None]
    assert len(connectivity["lenses"]) == 4 and len(mv) > 2500 and max(mv) <= 4
    assert len(fv) > 2500 and all(0 <= v <= 1 for v in fv)
    infra = web("infrastructure.json")
    assert len(infra["stations"]) >= 500
    assert len(infra["ports"]) >= 30
    assert max(s["passengers"] for s in infra["stations"]) > 100_000_000
    assert "methodology" in infra["rules"]["stations"]


def test_quality_of_life_contracts():
    quality = web("quality_life.json")
    assert {l["id"] for l in quality["lenses"]} == {"house_price", "apartment_price", "housing_liquidity", "apartment_sale_share", "gp_access", "nurse_access", "dentist_access", "midwife_access", "social_housing", "energy_poor_housing", "efficient_housing"}
    n = len(web("world.json")["owner"])
    assert all(len(l["values"]) == n for l in quality["lenses"])
    by_id = {l["id"]: l for l in quality["lenses"]}
    houses = [v for v in by_id["house_price"]["values"] if v is not None]
    gps = [v for v in by_id["gp_access"]["values"] if v is not None]
    assert len(houses) > 2500 and 500 < sum(houses) / len(houses) < 6000
    assert len(gps) > 2500 and 1 < sum(gps) / len(gps) < 5
    social = [v for v in by_id["social_housing"]["values"] if v is not None]
    assert len(social) > 2500 and 0.02 < sum(social) / len(social) < 0.20
    assert "Alsace-Moselle" in by_id["house_price"]["description"]


def test_cycling_contract():
    data = web("cycling.json")
    assert data["sources"] == ["fr_cycling"] and len(data["lenses"]) == 2
    vals = [v for v in data["lenses"][0]["values"] if v is not None]
    prot = [v for v in data["lenses"][1]["values"] if v is not None]
    assert len(vals) > 2500 and max(vals) > 5 and len(prot) > 2000
    assert data["unmatched_network_km"] < 100


def test_economy_contract():
    data = web("economy.json")
    assert data["sources"] == ["fr_insee_stats"] and len(data["lenses"]) == 5
    for lens in data["lenses"]:
        vals = [v for v in lens["values"] if v is not None]
        assert len(vals) > 2500 and all(0 <= v <= 1 for v in vals)
    assert "knowledge_jobs" in {l["id"] for l in data["lenses"]}


def test_transit_contract():
    data = web("transit.json")
    assert data["sources"] == ["fr_transit_stops"] and len(data["lenses"]) == 1
    vals = [v for v in data["lenses"][0]["values"] if v is not None]
    assert len(vals) > 2500 and data["out_of_map_stops"] < 20000
    assert any(v > 0 for v in vals) and "frequency" in data["lenses"][0]["description"]


def test_energy_system_contract():
    data = web("energy_system.json")
    assert data["sources"] == ["fr_energy"] and len(data["lenses"]) == 4
    assert data["unmatched_capacity_mw"] < 1000
    for lens in data["lenses"]:
        vals = [v for v in lens["values"] if v is not None]
        assert len(vals) > 2500 and len([v for v in vals if v]) > 10


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
    assert sum((s["energy"] or {}).get("total", 0) > 0 for s in states) == 14
    resources = web("resources.json")
    national = resources["summary"]["national"]
    assert national["tidal"]["count"] == 1 and national["tidal"]["value"] == 240
    assert national["battery"]["count"] >= 8 and national["battery"]["value"] >= 900
    assert national["wind"]["count"] >= 140
    assert any(i["type"] == "tidal" and i["state"] == "BRE" for i in resources["items"])


def test_freight_trade_contract_uses_french_units():
    trade = web("trade.json")
    assert trade["sources"] == ["fr_freight"]
    assert trade["year"] == 2019
    assert len(trade["routes"]) == 40
    assert len(trade["zones"]) == 18
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
    assert paris[cols["epci_name"]] == "Métropole du Grand Paris" and paris[cols["epci_population"]] > 7_000_000
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


def test_agriculture_tourism_electricity_contracts():
    agriculture = web("agriculture.json")
    assert agriculture["sources"] == ["fr_corine", "fr_agreste"]
    assert {l["id"] for l in agriculture["lenses"]} == {"vineyards", "orchards", "farm_density", "average_farm_size"}
    vineyard_vals = [v for v in agriculture["lenses"][0]["values"] if v]
    assert len(vineyard_vals) > 100 and max(vineyard_vals) > 0.1
    density = next(l for l in agriculture["lenses"] if l["id"] == "farm_density")
    size = next(l for l in agriculture["lenses"] if l["id"] == "average_farm_size")
    density_vals = [v for v in density["values"] if v is not None]
    size_vals = [v for v in size["values"] if v is not None]
    assert len(density_vals) > 2500 and max(density_vals) > 100
    assert len(size_vals) > 2500 and 1 < sum(size_vals) / len(size_vals) < 100
    assert agriculture["agreste_blank_communes"] > 0

    tourism = web("tourism.json")
    assert tourism["sources"] == ["fr_tourism"]
    hotel = tourism["lenses"][0]
    vals = [v for v in hotel["values"] if v is not None]
    assert hotel["id"] == "hotel_tourism" and len(vals) > 2500
    assert 0.5 < sum(vals) / len(vals) < 10 and max(vals) > 10

    electricity = web("electricity.json")
    assert electricity["sources"] == ["fr_electricity"]
    assert {l["id"] for l in electricity["lenses"]} == {"electricity_use", "residential_electricity", "tertiary_electricity", "industrial_electricity", "agricultural_electricity"}
    use = electricity["lenses"][0]
    vals = [v for v in use["values"] if v is not None]
    assert use["id"] == "electricity_use" and len(vals) > 2500
    assert 2 < sum(vals) / len(vals) < 10 and max(vals) < 15
    for extra in electricity["lenses"][1:]:
        sector_vals = [v for v in extra["values"] if v is not None]
        assert len(sector_vals) > 2500 and max(sector_vals) > 0
    assert any(s["id"] == "fr_tourism" for s in web("sources.json"))
    assert any(s["id"] == "fr_electricity" for s in web("sources.json"))


def test_heritage_contract():
    data = web("heritage.json")
    assert data["sources"] == ["fr_heritage"] and len(data["lenses"]) == 2
    vals = [v for v in data["lenses"][0]["values"] if v is not None]
    share = [v for v in data["lenses"][1]["values"] if v is not None]
    assert len(vals) > 2500 and max(vals) > 5 and len(share) > 1500
    assert all(0 <= v <= 1 for v in share)


def test_public_services_contract():
    data = web("public_services.json")
    assert data["sources"] == ["fr_crime", "fr_schools", "fr_public_equipment"]
    assert {l["id"] for l in data["lenses"]} == {"burglary", "violence", "primary_schools", "secondary_schools", "essential_services", "food_shops", "pharmacies", "culture_sports"}
    for lens in data["lenses"]:
        vals = [v for v in lens["values"] if v is not None]
        assert len(vals) > 2500 and max(vals) > 0
    burglary = data["lenses"][0]["values"]
    assert 0.1 < sum(v for v in burglary if v is not None) / sum(v is not None for v in burglary) < 2
    assert any(s["id"] == "fr_crime" for s in web("sources.json"))
    assert any(s["id"] == "fr_schools" for s in web("sources.json"))
    essential = next(l for l in data["lenses"] if l["id"] == "essential_services")
    evs = [v for v in essential["values"] if v is not None]
    assert len(evs) > 2500 and max(evs) == 6


def test_risk_contract():
    data = web("risk.json")
    assert data["sources"] == ["fr_risk_zones", "fr_risk_perimeters"]
    assert {"clay_shrink_swell", "seismic_zone", "radon_potential", "forest_fire_perimeter", "avalanche_perimeter", "ground_movement_perimeter"} == {l["id"] for l in data["lenses"]}
    for lens in data["lenses"]:
        vals = [v for v in lens["values"] if v is not None]
        assert len(vals) > 2500 and all(0 <= v <= 1 for v in vals)
    clay = [v for v in data["lenses"][0]["values"] if v]
    assert len(clay) > 500


def test_nature_contract():
    data = web("nature.json")
    assert data["sources"] == ["fr_nature"]
    assert {l["id"] for l in data["lenses"]} == {"natura2000", "natura_habitat", "natura_birds", "znieff", "nature_reserve", "park_area"}
    vals = [v for v in data["lenses"][0]["values"] if v is not None]
    nonzero = [v for v in vals if v]
    assert len(vals) > 2500 and len(nonzero) > 1000
    assert 0.05 < sum(vals) / len(vals) < 0.3 and max(vals) == 1
    assert any(s["id"] == "fr_nature" for s in web("sources.json"))


def test_flood_contract():
    data = web("flood.json")
    assert data["sources"] == ["fr_flood"]
    assert [l["id"] for l in data["lenses"]] == ["flood_exposure", "coastal_submersion"]
    vals = [v for v in data["lenses"][0]["values"] if v is not None]
    nonzero = [v for v in vals if v]
    assert len(vals) > 2500 and len(nonzero) > 400
    assert max(vals) > 0.2 and 0.01 < sum(vals) / len(vals) < 0.4
    coastal = [v for v in data["lenses"][1]["values"] if v is not None]
    assert len([v for v in coastal if v]) > 70 and max(coastal) > 0.1
    assert any(s["id"] == "fr_flood" for s in web("sources.json"))
