# franceciv: France as a strategy game, built from real data

A French adaptation of Andrej Karpathy's MIT-licensed [`usaciv`](https://karpathy.ai/usaciv/) visualizer.
The original browser engine, rendering art, interaction model and pipeline architecture are vendored here with attribution; this repository replaces the United States data spine with French public data.

**Live website: [www.arthurpham.com/franceciv](https://www.arthurpham.com/franceciv/).**

**Current status: France MVP.** It renders metropolitan France, Corsica and eleven overseas department/collectivity insets at 8 km hex resolution, with régions, départements, INSEE aires d'attraction des villes, terrain, land cover, population, GDP and employment-derived yields.

![France drawn as a 4X strategy map](docs/images/france-mvp.png)

## What works in the MVP

- Painted hex terrain from ETOPO1 elevation and CORINE Land Cover 2018 land cover; overseas elevation is included, while CORINE land-cover lenses remain metropolitan-only.
- 24 régions/collectivities and 107 départements or single-territory collectivities from Etalab contour files. Guadeloupe, Martinique, Guyane, La Réunion, Mayotte, Saint-Pierre-et-Miquelon, Saint-Barthélemy, Saint-Martin, Wallis-et-Futuna, French Polynesia and New Caledonia are affine-placed as cartographic insets; sparse Pacific archipelagos use representative commune hexes at the 8 km resolution.
- 699 city banners covering INSEE 2020 aires d'attraction des villes (AAV), including overseas AAVs and cross-border AAVs restricted to their French communes; small areas appear through zoom-dependent de-cluttering and search.
- Five yields: Food, Production, Gold, Science and Culture.
  - Gold is Eurostat NUTS-3 GDP in current euros.
  - The other yields are census workplace employment by industry, observed directly for each aire d'attraction.
  - AAV GDP remains an estimate: department GDP is allocated in proportion to workplace employment.
- Population, prosperity, housing, election, natural-hazard and climate lenses, including income, poverty, unemployment, education, age, immigration, commuting, growth, homeownership, vacancy, 2022 presidential results, GASPAR catastrophe recognitions, temperature, warming, rainfall and climatic water deficit.
- Historical time lenses with a year selector and fixed colour scales: population density in nine census snapshots from 1968 to 2023; housing-stock density, homeownership, second-home and vacancy shares for 2012, 2017 and 2023; presidential second-round votes and abstention for 2017 and 2022; annual DVF existing-dwelling prices for 2021–2025; residential mobility and out-of-department in-migration for 2012, 2017 and 2023; and annual SIM2 temperature, rainfall and climatic water-deficit snapshots for 1985, 1995, 2005, 2015 and 2025.
- Power-generation and storage resources from the national ODRÉ registry: nuclear, hydro, pumped storage, tidal, gas/coal, wind, solar and batteries.
- Detailed named watercourses from IGN BD CARTO, official national-road geometry/traffic and active SNCF railway geometry, real airports and ports, busy SNCF passenger stations, first-class EPCI, IRIS/neighborhood, bassin-de-vie and zone-d'emploi search and statistics, commune-derived fiber, EV-charging and mobile-site lenses, national cycling-infrastructure lenses, national GTFS scheduled-frequency lens, DVF housing-price/market lenses, DREES healthcare-access lenses, social-housing shares, housing energy-performance lenses, CORINE vineyard/orchard and Agreste farm-structure and workplace economic-composition and demographic/business-dynamism lenses, INSEE hotel-tourism intensity, Mérimée protected-heritage lenses, ODRÉ installed-capacity/storage lenses, RTE transmission-network/site-density lenses and commune-level Enedis electricity-use/heating lenses, recorded-crime lenses, school-density lenses, Géorisques/BRGM natural-risk zoning and prevention-perimeter lenses, INSEE everyday-services, health/social-care, cinema, swimming-pool, rail-station, postal, library, France Services, recycling-center, police/gendarmerie and sports/culture lenses, INPN Natura 2000, ZNIEFF, nature-reserve and park lenses, physical river-flood/coastal-submersion exposure lenses, and SISPEA/Hub'eau drinking-water/wastewater and ADEME circular-economy infrastructure lenses, and CEREMA/INERIS technological-noise/air-quality depth lenses, plus Cerema land-consumption and CORINE wetland/natural-cover lenses.


- UNESCO World Heritage wonders from the official UNESCO XML export, plus the most-visited Musées de France and largest universities from ministry open data.
- Regional road, rail and inland-water freight routes from SDES 2019 goods-flow tables.
- The original interactive map, city panels, minimap, sharing, searchable/favorite lens heritage catalog, coverage-aware legends, and lens histogram UI, plus search and compact public-data cards for metropolitan and overseas communes, including EPCI/intercommunality names and populations. City, region, commune, EPCI and IRIS cards include a local multi-layer inspector with hex-level lens values, rankings, source vintages and explicit no-data states.
- The Almanac includes a build-generated Data trust report: source freshness cadences, per-lens coverage metrics and reproducibility fingerprints.

## Explicitly not in the MVP yet

Citizens, districts, infrastructure, wonders, elections, natural hazards and historical defense-base personnel now use French public data. Some detailed panel assumptions and lesser-used inherited advisor copy still need France-specific review.

Other known limitations:

- AAV GDP remains allocated from department GDP using workplace-employment shares; it is an estimate, not a true AAV account.
- Road and rail geometry is schematic Natural Earth cartography, not an exhaustive network inventory.
- Election and hazard lenses are currently aggregated from communes to departments because the browser contract does not yet carry a commune hex index.
- Catastrophe-naturelle counts are administrative recognition frequency. The separate flood-exposure lenses are raster-sampled rare/millennial river-overflow and marine-submersion estimates, not parcel-level risk or damage.
- UNESCO serial properties are represented by one French component point rather than full site boundaries. Museum attendance sums distinct physical sites sharing one Muséofile institution; universities are mapped at administrative headquarters communes rather than campus footprints.
- Enedis electricity and RTE transmission-network lenses do not cover overseas France; Enedis also does not serve Corsica and some local-distribution areas, so electricity-use lenses reflect network coverage as well as demand.
- Freight is inter-regional only, non-directional, excludes foreign trade and has suppressed rail cells. Military markers use a sparse 2012 Ministry personnel table: they are historical base-seat aggregates, not current units, boundaries, ranges or a full order of battle.

## Quick start

Install [uv](https://docs.astral.sh/uv/), then:

```bash
uv run python -m pipeline serve
```

Open the printed local URL. The generated data in `web/data/` is committed, so no download is required for viewing.

## Rebuilding the data

```bash
uv run python -m pipeline fetch fr_boundaries fr_aav natural_earth etopo fr_corine fr_eurostat fr_energy fr_energy_network fr_climate fr_hydrography fr_rail_network fr_rail_stations fr_broadband fr_ev_charging fr_mobile_network fr_cycling fr_transit_stops fr_transit_frequency fr_road_traffic fr_housing fr_housing_history fr_healthcare fr_social_housing fr_housing_energy fr_tourism fr_electricity fr_crime fr_schools fr_risk_zones fr_risk_perimeters fr_public_equipment fr_nature fr_flood fr_insee_stats fr_migration fr_iris fr_transport fr_unesco fr_elections fr_hazards fr_freight fr_culture fr_heritage fr_military fr_water_services fr_water_quality fr_circular_economy fr_noise fr_air_quality fr_land_consumption fr_functional_geographies
uv run python -m pipeline process fr_boundaries fr_aav natural_earth etopo fr_corine fr_eurostat fr_energy fr_energy_network fr_climate fr_hydrography fr_rail_network fr_rail_stations fr_broadband fr_ev_charging fr_mobile_network fr_cycling fr_transit_stops fr_transit_frequency fr_road_traffic fr_housing fr_housing_history fr_healthcare fr_social_housing fr_housing_energy fr_tourism fr_electricity fr_crime fr_schools fr_risk_zones fr_risk_perimeters fr_public_equipment fr_nature fr_flood fr_insee_stats fr_migration fr_iris fr_transport fr_unesco fr_elections fr_hazards fr_freight fr_culture fr_heritage fr_military fr_water_services fr_water_quality fr_circular_economy fr_noise fr_air_quality fr_land_consumption fr_functional_geographies
uv run python -m pipeline build world france_core climate hydrography connectivity cycling transit mobility economy energy_system society statistical_geography quality_life agriculture tourism electricity risk public_services nature flood citizens districts military resources infrastructure wonders trade communes heritage time_dimension water_circular risk_depth environment_depth functional_geographies catalog
```

Downloads are cached under `data/raw/` with provenance manifests. Generated browser data is written to `web/data/`.

## Data sources

- Etalab / geo.api.gouv.fr: current région, département and commune boundaries, commune populations/centroids, and EPCI reference data.
- INSEE: 2020 aires d'attraction des villes, census/comparateur demographic and housing series, residential-migration principal indicators, 2026 vintage geography.
- Eurostat regional accounts: `nama_10r_3gdp`, `nama_10r_3gva`, `nama_10r_3empers` for 2024.
- CORINE Land Cover 2018, served through the IGN Géoplateforme WMS.
- ODRÉ national registry of electricity generation and storage installations, plus RTE departmental transmission-network lengths and electrical-site counts. RTE no longer publishes exact public network geometry for security reasons, so transmission lenses are departmental statistics rather than line geometry.
- Météo-France SIM2 monthly climate reanalysis, 1961–2025.
- IGN BD CARTO named watercourse segments.
- SNCF Gares & Connexions station traffic and station reference coordinates.
- ARCEP Ma connexion internet commune technology-eligibility statistics.
- transport.data.gouv.fr national GTFS stop extraction and scheduled-service frequency extraction, with consolidated regional feeds, supplemental local feeds and duplicate/overlap suppression.
- OpenParcels current commune medians and Terralyse annual commune series, both derived from DGFiP/Etalab DVF transactions.
- DREES localized potential accessibility (APL) to health professionals.
- INSEE Melodi tourist-accommodation occupancy statistics.
- Enedis annual electricity consumption by commune and activity sector/customer category, plus residential electric-heating and winter thermosensitivity indicators.
- SISPEA drinking-water/wastewater service prices and performance, Hub'eau drinking-water control samples, ADEME SINOE recycling centres and circular-economy repair/reuse actors.
- CEREMA strategic noise maps for qualifying transport infrastructure, INERIS annual background air concentrations and Géorisques industrial-risk prevention perimeters.
- Cerema national soil-artificialization communal indicators and CORINE wetland/natural land cover.
- INSEE bassins de vie 2022 and zones d'emploi 2020 communal composition.
- Ministry of the Interior departmental recorded-crime statistics.
- INSEE Base permanente des équipements 2024 detailed equipment registry.
- Ministry of National Education school directory.
- INPN Natura 2000, ZNIEFF, national nature reserve, national park and regional natural park geometries through the IGN API Carto Nature module.
- TRI/Géorisques 2020 rare-or-millennial river-overflow and marine-submersion flood surfaces, rasterized through the official WMS.
- NOAA ETOPO1 elevation and bathymetry.
- Natural Earth 1:50m neighbouring countries, lakes and rivers; 1:10m roads, railroads and ports.
- OurAirports and Eurostat `avia_paoa` / `mar_go_aa` transport traffic.
- UNESCO World Heritage Centre official XML export.
- Ministry of the Interior definitive 2017 and 2022 presidential election results, mirrored on data.gouv.
- GASPAR catastrophe-naturelle recognitions from Géorisques.
- Géorisques forest-fire, avalanche and ground-movement risk-prevention servitude perimeters, rasterized through the official WMS.
- SDES 2019 road, rail and inland-waterway goods-flow workbooks.
- Ministry of Culture museum attendance and Muséofile directory; MESRI SISE university enrolment.
- Ministry of the Armed Forces: 2012 defense-base stationed personnel, preserved through the data.gouv.fr Tabular API extraction.

The in-app Almanac/source heritage catalogue is generated from the same source registry used by the pipeline.

## Architecture

The project intentionally keeps Karpathy's simple architecture:

- `pipeline/sources/`: download and normalize source data into `data/interim/`.
- `pipeline/build/`: reconcile data onto the shared hex grid and write browser JSON contracts.
- `web/`: dependency-free ES modules and Canvas 2D; no npm, framework or frontend build step.

See `docs/DATA_CONTRACTS.md` for the browser/pipeline interface. French concepts are deliberately mapped onto the original contract: région → state, département → county, and aire d'attraction des villes → metro/city. That mapping is a compatibility layer, not a claim that the legal or statistical concepts are identical.

## License and attribution

The upstream `usaciv` source is MIT-licensed and its license is preserved in `LICENSE`. France-specific modifications in this repository are also available under the MIT license. Public data remains subject to the terms of its respective publishers.
