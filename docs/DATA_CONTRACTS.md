# Data contracts (v2, France)

### wider-France inset coverage matrix

| Territory | Map/search/population boundary | Elevation/relief | Metropolitan lens coverage | Cartographic treatment |
|---|---|---|---|---|
| Saint-Pierre-et-Miquelon | yes | yes | mostly null where a source is metropolitan/departmental | enlarged affine inset |
| Saint-Barthélemy | yes | yes | mostly null | enlarged affine inset |
| Saint-Martin | yes | yes | mostly null | enlarged affine inset |
| Wallis-et-Futuna | yes | yes | mostly null | inset plus representative commune hexes where islands are smaller than the 8 km grid |
| French Polynesia | yes | yes | mostly null | compressed archipelago inset plus representative commune hexes |
| New Caledonia | yes | yes | mostly null | enlarged affine inset |

All eleven non-metropolitan insets are cartographic placements, not real positions. Small-island representative hexes are visibility/accessibility simplifications, not area measurements; density and area-normalized lenses may be missing or uncertain there. Many statistical sources cover only metropolitan France, the five overseas departments, or a subset of collectivities, so null means no validated coverage rather than zero.

The Python pipeline and the browser agree on the JSON files in `web/data/`. All coordinates are **map kilometres** in the Albers equal-area projection fitted to the whole map, origin top-left, y down. Overseas departments are first affine-transformed into cartographic inset slots west of the mainland, then projected by the same Albers transform. Pointy-top odd-r hex index is `row * cols + col`. `null` means unavailable; `0` is never a stand-in for unknown.

## French naming inherited from the original schema

The file and object names `states`, `counties`, and `metros` are retained only as browser/pipeline compatibility names. Their meanings in this repository are always French:

| Schema name | French geography |
|---|---|
| `state`, `state_fips`, region abbreviation | metropolitan or overseas région |
| `county`, `geoid` | département (`2A`/`2B` in Corsica) |
| `metro`, city id, `aav` | INSEE aire d'attraction des villes (AAV), three-digit code |
| commune | French commune, five-character INSEE code |

Money is euros. Use `eur` for new fields. `usd` may remain only as a backwards-compatible formatter alias and must format euros, never dollars. Population values are INSEE municipal/legal populations unless a file says otherwise. “Metropolitan France” means the 13 metropolitan régions including Corsica. The map also includes the five overseas department-region collectivities as insets; other overseas collectivities are outside the map.

## Pipeline conventions

* `pipeline/sources/*.py` download and normalize public source data into `data/interim/<source>.json`; every `Source` records raw-file provenance.
* `pipeline/build/*.py` modules with `REQUIRES`, `PRODUCES` and `build()` are discovered automatically and run in dependency order. Builder interims start with `_`.
* Builders may define `check(web_dir)`; `pipeline check` discovers those checks. A missing optional output is a NOTE in synthetic test data, not a failure.
* Python is standard-library only. Downloads are cached under `data/raw/` and checksummed in manifests.
* The `_world` interim contains `grid`, `projection`, `owner`, `county`, seven-point `county_samples`, `states`, `counties`, `water`, `cover`, and `pct`. `owner[cell] >= 0` is French land; `-1` is water and `-2` foreign land.

## Core files

### world.json

`{"version":2,"grid":{cols,rows,radius},"states":[...],"counties":[...],"owner":[],"county":[],"france_share":[],"water":[],"cover":[],"pct":{...},"rivers":[]}`.

* `owner`, `county`, `france_share`, `water` and `cover` are per-cell arrays. `france_share` is the approximate 0..1 share of the hex inside French departmental territory (seven-sample estimate); it is used for population-density integration and partial-hex estimates, not as a land-cover class.
* `states` rows have `fips` (INSEE region code), `abbr`, `name`, `color`, `label` anchor and yield metadata added by builders.
* `counties` rows have `geoid`, `name`, `state_fips` and area/population metadata. These are departments.
* `pct` values are whole-percent shares (0–100) of each hex's classified land samples, excluding water/no-data samples. They are grouped from CORINE Land Cover for the renderer. Renderer keys such as `cropland` are visual categories, not claims that the source is US NLCD.
* Rivers and lakes are clipped to map coordinates and used for terrain rendering.

### cities.json

One object per displayed AAV. Important fields:

* identity/geography: `id`, `name`, `full`, `short`, `x`, `y`, `cell`, `footprint`, `counties` (department ids);
* people/economy: `population`, `pop_series`, `growth`, `growth_years`, `employed`, `jobs`, `gdp`, `gdp_year`, `gdp_per_capita`, `median_income`, `poverty`, `unemployment`;
* housing: `homeownership`, `second_homes`, `vacancy` as 0..1 shares from INSEE Comparateur;
* game-style aggregates: `yields` (`food`, `production`, `gold`, `science`, `culture`), `specialisation`, ranks.

AAV employment is direct INSEE census workplace employment. Department GDP is Eurostat regional accounts; AAV GDP is allocated by workplace employment and must be described as an estimate. City industry value-added breakdowns are omitted when no official AAV-level industry GDP exists.

### states.json

One object per mapped région, using the same economic shape as cities plus `abbr`, `color`, ranks, land and energy summary metadata. Regional GDP/employment are direct Eurostat aggregates; census-derived social rates are aggregate or population-weighted as documented in the builder.

### nation.json

`{"version":1,"year":2023,"sources":[...],"nation":{...},"yields":[...]}`.

`nation` is the aggregate of the mapped French territory with the same economic/housing shape as cities. `yields` describe the five displayed yields; monetary/value-added yield units are `eur`.

### lenses.json

`{"version":1,"source":"...","groups":[...],"lenses":[...]}`. Each lens has `id`, `group`, `name`, `icon`, `unit`, `format`, `scale`, `higher_is`, `description`, and a per-cell `values` array of world-grid length. `pct` and `signed` values are 0..1 fractions. Values must be null off French land.

Current lenses cover French population/economy, housing, education, age, immigration, commuting, elections, hazard recognitions, climate, connectivity, healthcare, agriculture, tourism, electricity use, public services, protected nature, physical flood exposure, and CORINE land-cover shares. Department-level density and employment lenses are area-weighted across hexes using `_world.county_samples`; this preserves departmental totals rather than duplicating population in border hexes.

### counties.json

Despite the filename, rows are departments. Shape: `{"version":1,"vintage":"...","fields":[...],"columns":[...],"rows":[...]}`. Required identity columns are `geoid`, `name`, `state`, `population`, `land_km2`, `density`, `aav`, `cell`; other columns mirror published lens metrics. `aav` is the principal AAV id used for rollups. `cell` is a representative display hex. Departments smaller than one hex may own no majority hex; the builder must then choose the nearest suitable land hex from the population-weighted centroid so `cell` is always a valid in-range integer. This representative cell is only for framing/highlighting, not statistical geography.

### sources.json

Machine-readable bibliography for every source: id, title, publisher, url, license, retrieval date, files, hashes, and notes. User-facing source claims should be consistent with this file.

## Optional layer files

Small eager layers are loaded after first paint; large layers are lazy.

### resources.json

Energy and agricultural resource sites. Items have `type`, `name`, `x`, `y`, `cell`, numeric-or-null `value`, `detail`, `state`, `aav`. Electricity sites use the ODRÉ generation registry; `value` is MW where applicable. The builder also post-processes regional energy summaries into `states.json` before writing `resources.json` (this ordering is cache-significant).

### infrastructure.json

Transport infrastructure. Airport passengers come from Eurostat `avia_paoa`, coordinates from OurAirports. Port tonnage comes from Eurostat maritime statistics with Natural Earth fallback positions. Passenger-station traffic comes from SNCF. Railway tile links use official active SNCF Réseau line geometry, with Natural Earth retained only for Corsica because it is outside the RFN export; ordinary lines are main-line display tier and connections/main/port tracks are secondary. Roads remain schematic Natural Earth geometry. Labels are local French display-size buckets. `aav` is the containing AAV inferred from the point.

### trade.json

SDES 2019 interregional freight flows. Routes are schematic arcs between regional anchors: tonne-kilometres and tonnes are real aggregate statistics, but paths are not physical truck/rail routes. Rail suppression is represented explicitly. Fields use metric units; obsolete `value_musd` must not be emitted.

### climate.json

Météo-France SIM2 climate lenses. Temperature and precipitation use 1991–2020 normals; warming/rainfall change compare 1996–2025 with 1961–1990. `water_deficit` is mean annual potential evapotranspiration minus total precipitation in the normal period; it is a climatic moisture-balance indicator before soil storage, irrigation, runoff and groundwater are considered. `water_deficit_change` is the recent-period minus baseline change in that annual balance.

### connectivity.json

Commune connectivity lenses. Fiber values are eligible premises shares from ARCEP; EV-charging values are consolidated public charge points per 10,000 residents. Mobile lenses use ARCEP operator-reported physical site deployment: `mobile_operators` is the population-weighted number of operators with a local 4G-capable site, and `mobile_5g` is the population share in communes with a local 5G-capable site. Mobile values measure infrastructure presence, not theoretical signal coverage or measured quality; a commune without a site may still receive signal from neighbouring communes. Commune values are aggregated to hexes by centroid. IRVE zero means no published public charge point, not missing data; arrondissement charge points are attributed to Paris, Lyon and Marseille commune totals.

### cycling.json

National BNAC/OpenStreetMap cycling-infrastructure lenses. Segment lengths are computed from WGS84 geometries, attributed to current communes through INSEE municipal-merger mappings, split across boundary-crossing communes, and aggregated by commune centroid. `cycling_network` counts explicit cycling amenities; `protected_cycling` counts pistes cyclables, voies vertes, bus-bike corridors, mixed pedestrian/cycle facilities, protected shoulders and goulotte lanes. OpenStreetMap completeness varies by territory.


### economy.json

INSEE census workplace-employment composition lenses. Commune job counts are summed within each map hex before calculating shares, so values describe where jobs are located rather than where workers live. Manufacturing uses NACE CA–CM; knowledge services use information/communication, finance/insurance and professional/scientific/technical divisions; public and care uses public administration, education, health and social work.



### transit.json

Experimental national GTFS stop availability. Rows are deduplicated by normalized stop name and approximately 100-metre rounded coordinates because overlapping feeds often publish the same physical stop. Values are stops per 10,000 residents. Stop presence does not measure service frequency, operating span, speed or reliability; catalog coverage can vary, and seasonal/tourist territories can score high because the denominator is resident population.

### epci.json, iris_index.json and neighborhoods.json

First-class statistical geography. `epci.json` aggregates existing INSEE Comparateur EPCI rows and positions each EPCI at the population-weighted centroid of member communes. `iris_index.json` is the compact browser search/panel index of true IRIS. Whole-commune pseudo-IRIS are omitted there because they duplicate commune search, but they are included in the statistical partition used for the neighborhood lenses. Positions and areas are derived from Contours IRIS polygons. `neighborhoods.json` lenses aggregate IRIS population, age and immigration to hexes by assigning each whole IRIS by centroid; this is finer than department-level statistics but approximate at hex boundaries. The 2022 population extract excludes Mayotte; other overseas collectivities outside the current map frame are omitted until their insets exist.

### public_services.json — additional equipment detail

Postal access points combine bureaux de poste, agences postales and relais poste. Libraries, France Services sites, déchèteries and police/gendarmerie stations are population-normalized counts of INSEE BPE equipment records. They describe recorded facility presence, not opening hours, capacity, staffing, response time, service range or quality. Counts use `NBEQUIDENT` where INSEE groups identical facilities and are aggregated by commune then hex.

### transit.json frequency layer

`transit_frequency` counts scheduled GTFS stop calls after applying `calendar.txt` and `calendar_dates.txt`; frequency-based trips in `frequencies.txt` are expanded across their published headway windows. The pipeline chooses a representative Wednesday from the consolidated regional feeds, then uses the nearest valid Wednesday inside each supplemental feed's published validity range. It is theoretical supply, not reliability, speed, crowding or observed operation.

Coverage combines consolidated feeds for Île-de-France, Auvergne-Rhône-Alpes, Nouvelle-Aquitaine, Grand Est, Pays de la Loire, Bretagne, Normandie and Centre-Val de Loire with supplemental local/regional feeds selected from catalog `covered_area` metadata for the other regions and overseas departments. Aggregate publications are preferred over their granular duplicates where network metadata shows that relationship; exact duplicate zip snapshots are skipped; coordinate/time trip signatures suppress feed publications whose service is overwhelmingly contained in another feed; supplemental stops inside consolidated-feed regions are suppressed; and stops outside mapped French departments are excluded. This prevents the major known double-counting paths, although GTFS catalog network labels are imperfect and residual publisher overlap cannot be ruled out. Departments with at least one extracted usable stop are treated as covered: cells with no extracted stop calls there are zero, while departments with no usable extracted GTFS remain null rather than zero.

### mobility.json

Official annual-average-daily-traffic sections on the national road network. `road_traffic` is a length-weighted sampled average in vehicles/day and `heavy_vehicle_share` is traffic-weighted. Coverage excludes departmental and municipal roads; section measurement years can precede the 2024 reference year. Heavy-share outliers above 100% in the source are treated as invalid rather than plausible shares. The same geometry replaces schematic Natural Earth major-road links for mainland France; Corsica retains schematic geometry.

### time.json

Historical time-series lenses. Temporal lenses carry `time: {label, years, default, encoding, series}`; with `sparse-index-v1`, `series` maps each measured year to an object of populated grid indexes and the frontend expands it to a dense array, then switches `values` to the selected exact year without interpolating missing vintages. Colour domains are fixed across years. INSEE population, housing and residential-migration commune counts are distributed across current commune polygons on a 1 km lattice, uniformly within each commune, with centroid fallback for very small/sparsely sampled polygons. Missing or suppressed commune values produce null hexes rather than zero. Density denominators convert affine overseas-inset display area back to real spherical ground area; `methodology.inset_display_area_over_real_area` records the correction ratios. Residential-mobility lenses are gross one-year moves/in-migration, not net migration balances; out-of-department in-migration includes arrivals from abroad or other overseas territories, and the INSEE extract contains no Mayotte commune rows.

Election lenses aggregate definitive commune vote counts to stable departments for the 2017 and 2022 presidential second rounds. Housing-price history exposes Terralyse's annual DVF commune medians for existing dwellings in 2021–2025, with new-build sales and dwellings outside the source's 20–500 m² and €1,000–50,000/m² filters excluded; commune medians are combined as transaction-count-weighted means rather than true hex medians. Estimates based on fewer than five spatially allocated sales are suppressed, sparse commune coverage and the exclusion of Alsace-Moselle/Mayotte are null rather than zero, and Paris/Lyon/Marseille arrondissement detail begins in 2021. Pre-2021 rows are not exposed because the published file includes commune medians below the source's own €1,000/m² transaction floor, so they cannot be treated as the same measurement. Climate history averages SIM2 grid points inside metropolitan hexes for the individual 1985, 1995, 2005, 2015 and 2025 reanalysis years; these are weather-year snapshots rather than climate normals and overseas departments are outside SIM2 coverage.

Sparse index encoding keeps uncompressed `time.json` near 2.4 MB rather than about 6.7 MB. It remains an eager lens-catalog layer so the lenses are discoverable and temporal deep links resolve synchronously; a future split manifest/series format can make it fully lazy.

### society.json

INSEE Comparateur de territoires commune aggregates. `natural_balance` is births minus deaths as a share of residents in 2023. `net_migration` is a residual estimate: population change 2017–2023 minus summed natural increase, divided by 2017 population; it omits statistical adjustments and is sensitive to municipal-boundary change. `business_density` counts establishments (local business units), not enterprises or employment. The `commune_*` lenses expose commune-level median income, poverty, homeownership, second homes and vacancy rather than the headline department-level aggregates; income/poverty are population-weighted within hexes and suppressed communes remain null rather than zero.

### quality_life.json

DVF housing-price/market and DREES healthcare-access lenses are weighted commune aggregates with source-specific geographic exclusions documented in each lens. `housing_liquidity` is sales per 10,000 residents over roughly two years, not dwelling turnover; `apartment_sale_share` describes transacted stock rather than the full dwelling stock. `social_housing` is the population-weighted commune share of primary residences that are social housing in the 2023 RPLS; it excludes habitat spécifique and certain SEM stock and is not comparable with the legal SRU article-55 rate.

Housing energy lenses use ADEME post-July-2021 DPE records; because diagnostics are transaction/rental-triggered, commune A-G distributions are a biased sample rather than a census of all housing.

### flood.json

Physical river-flood and coastal-submersion exposure. Values are approximate hex-area shares derived from official TRI/Géorisques rare-or-millennial river-overflow and marine-submersion WMS rasters. They are not parcel-level risk determinations, erosion/groundwater-rise estimates, damage estimates, or a substitute for regulatory hazard maps.

### risk.json

Natural-risk zoning lenses sampled from official Géorisques/BRGM WMS rasters. `clay_shrink_swell`, `seismic_zone` and `radon_potential` are normalized area-weighted class indices, not probabilities, damage estimates or measurements. Clay low/medium/high and radon low/moderate/high classes are weighted ⅓, ⅔ and 1; seismic zones 1–5 are weighted 0.2–1. Values are raster-sampled hex estimates and may be null outside the published mainland raster coverage. Forest-fire, avalanche and ground-movement perimeter lenses are approximate hex-area shares inside official risk-prevention servitude perimeters; they are administrative exposure/regulation areas rather than probabilities, intensity measurements or damage estimates.

### energy_system.json

ODRÉ installed-generation-capacity lenses in kW per resident. Commune capacities are aggregated by map hex. Per-capita normalization is a spatial intensity measure, not local ownership or consumption: electricity is transmitted across the national grid. Hydro includes conventional, run-of-river, pumped-storage and tidal installations where present.

RTE transmission-network lenses are departmental statistics rather than exact infrastructure geometry. RTE no longer publishes precise public line and substation coordinates for security reasons. Circuit length counts each electrical circuit, so multi-circuit lines contribute multiple circuit-kilometres; pylon-route length counts the shared overhead corridor. Because circuit and corridor lengths are allocated independently at department boundaries, a rare aggregate ratio below the physically meaningful minimum of one is treated as missing rather than shown as false precision. Non-overhead share combines underground and submarine circuits. Transformation-site and connection-point densities count operating registry records per department area without exact public locations. A small number of registry rows have a blank department field; they are omitted rather than geocoded or guessed, so site densities slightly undercount the true network.

### nature.json

INPN/API Carto Nature protected-area lenses. Natura 2000 and national nature reserves are statutory protection designations. ZNIEFF type 1/2 polygons are ecological knowledge and land-planning inventories, not by themselves legal protection regimes. National/regional park perimeter shares do not imply uniform strict protection throughout the perimeter. Values are approximate sampled hex-area shares.

### electricity.json

Enedis electricity-consumption lenses. Values are 2025 commune-level MWh per resident for total consumption and broad residential, tertiary, industrial, agricultural and small-professional customer categories, distributed approximately over commune polygons at a 1 km lattice. Small professionals (category PRO) cut across broad activity sectors and must not be added to those sector totals as an additional component. Residential share is the ratio of allocated residential MWh to allocated total published MWh within each hex. Electric-heating and winter heating-thermosensitivity lenses are commune statistics population-weighted within hexes. The electric-heating lens uses the most recent residential rows still publishing that housing attribute (currently 2024) because the 2025 rows omit it. Enedis privacy rules withhold some residential and small-professional rows; absences are not zeros. Customer-class lenses therefore omit commune populations where that class has no published row, and totals are published consumption rather than a complete privacy-free national accounting. The uniform-within-commune distribution is a spatial approximation rather than meter locations or real within-commune population density. Enedis coverage gaps (including Corsica, overseas France and local-distribution areas) mean missing or low values are not always low use.

### water_circular.json

Water and circular-economy lenses. SISPEA service-price/performance values are population-weighted service aggregates for 2024 assigned to the managing body's headquarters department; multi-commune services may cross department boundaries, so they are departmental service approximations rather than exact territorial averages. Hub'eau drinking-water quality lenses use 2025 routine Escherichia coli rows as sample carriers for whole-sample regulatory conclusions; communes with fewer than three samples are missing rather than scored from noisy tiny counts. ADEME circular-infrastructure lenses count current SINOE recycling centres and distinct Que Faire De Mes Objets et Déchets actors by commune, distributed approximately over commune polygons at a 1 km lattice. The circular database is composite/contributed and not a statutory exhaustive business registry.

### risk_depth.json

Technological-risk, transport-noise and air-quality lenses. Industrial-risk values are approximate shares of official administrative prevention perimeters, not accident probabilities or expected damage. CEREMA noise lenses use 2022 type-A Lden polygons for qualifying non-conceded roads/railways only: concessionaire networks, agglomeration noise maps, airports and industrial noise are outside scope, and Paris/Hauts-de-Seine/Seine-Saint-Denis/Val-de-Marne are absent from the source. Polygon areas are spatially approximated in 250 m local-projection bins, with overlapping infrastructure contributions capped at bin area; shares use real land area including overseas inset correction. INERIS air lenses are commune annual mean background concentrations combining measurements and CHIMERE modelling. They do not characterize local traffic/industrial peaks, cover metropolitan France including Corsica rather than overseas territories, and the upstream indicator is marked as under review.

### environment_depth.json

Land-artificialization and ecological-cover lenses. Cerema communal values are land-registry-derived indicators for 2011–2025: cumulative/recent natural-agricultural-forest land consumption and per-capita land-take intensity, and housing share of consumption. They are legal land-use measures rather than continuous-impervious-surface measurements; commune ratios are distributed approximately over polygons at a 1 km lattice. CORINE wetland and natural/semi-natural lenses use the coarse metropolitan 2018 land-cover extract and do not cover overseas territories. The natural/semi-natural lens is a structural land-cover proxy, not a validated ecological-corridor network.

### living_basins.json and employment_zones.json

First-class bassin-de-vie and zone-d'emploi search/card rows. Geography composition and labels are official INSEE bassins de vie 2022 and zones d'emploi 2020 at 1 January 2025. Positions are population-weighted centroids of member communes, not geometric centroids or administrative seats. Population, density and commune counts are aggregated over current mapped commune boundaries; existing-home price/sales are 2025 transaction-weighted commune aggregates where coverage exists; residential mobility and out-of-department in-migration use census 2023 rows. These are functional statistical geographies, not administrative governments.

### public_services.json

Recorded-crime, school-density and INSEE Base permanente des équipements lenses. Crime is department-level recorded crime and not victimization prevalence. Equipment lenses use detailed BPE 2024 rows aggregated by commune centroid to map hexes. `essential_services` is the population-weighted count of six categories present in a commune: food shops, pharmacy, general practitioner, primary school, post office/relais and library. Equipment counts use `NBEQUIDENT` where INSEE groups identical facilities; they measure presence/density, not quality or capacity. `hospital_services` counts service records and multiple services can belong to one hospital; childcare uses total residents rather than target-age population; eldercare counts service records rather than beds; rail-station counts do not measure service frequency; swimming-pool counts do not measure public opening hours or quality. Paris, Lyon and Marseille arrondissement records are attributed to commune totals.

### agriculture.json

CORINE vineyard/orchard land-cover shares plus Agreste 2020 farm density and average farm size. Agreste values are commune census statistics aggregated to hexes by commune centroid. Blank commune cells conflate no farm and statistical suppression, so they are omitted from both numerator and denominator rather than zero-filled. Utilised agricultural area is assigned to the farm headquarters commune and may include land worked elsewhere.

### heritage.json

Ministry of Culture Mérimée protected-building lenses. Counts are attributed to current communes through INSEE municipal-merger mappings where unambiguous, then aggregated by commune centroid. `heritage_sites` is protected buildings per 10,000 residents; `classified_heritage` is the share of protected buildings whose protection text includes classement and is null where no protected building is recorded.

### military.json

Ministry of the Armed Forces 2012 `bases de défense` personnel table. Installations are support-group seat communes, not boundaries, ranges, barracks-level geography, or a current order of battle. City garrison tiers are derived only from stationed-personnel thresholds; `share` is a contextual scale mixing the 2012 personnel count with current population and must not be presented as a current rate.

### wonders.json

French wonders selected by published rules: UNESCO properties, national parks, most-visited museums (Ministry attendance plus Muséofile locations), and largest universities (MESRI/SISE enrolment). Museum attendance is aggregated across distinct physical sites sharing one institution when appropriate. University locations are administrative headquarters, not every campus.

### citizens.json (lazy)

INSEE census-derived citizen mixes by AAV: broad socio-professional categories, age bands, commuting modes, highest diploma, and immigrant status. Keys such as `born_in_state` are inherited schema names; in France the nativity pair means non-immigrant vs immigrant. Education keys are display categories aligned to French diploma levels; descriptions must use bac/bac+ terminology rather than US degree assumptions.

### districts.json (lazy)

INSEE workplace-employment specialization by AAV and department. Internal industry keys are inherited compatibility keys, but their labels and definitions are broad NACE sections. There is no equivalent public pay, annual-change, suppression, or county-series dataset in the chosen French source; those fields must be absent or null rather than fabricated.

### communes.json (lazy)

Search/card data for communes: population, department, AAV, income where available, election results and hazard summaries. This file is large and must remain lazy-loaded on first search use.

### disasters.json (lazy), if present

Commune-level GASPAR detail. Recognitions are administrative catastrophe-naturelle decisions, not measurements of physical damage or hazard exposure. Municipal-merger attribution follows INSEE COG movement files; ambiguous splits, obsolete links and cycles must not be silently invented.

## Browser boundaries

`web/js` renders the contracts above; it must not hard-code replacement statistics. User-facing geography labels are Region, Department, Urban area/AAV and Commune. Internal variables named `state`, `county` or `metro` may remain only because they implement the inherited schema. User-facing text, source notes, tooltips and caveats must describe French geography, French/European sources, euros and metric units. Concepts that have no comparable French public dataset (for example census religion, health-insurance coverage, veteran status, disaster-assistance geography, or employer pay microdata) are intentionally absent rather than approximated.

### automation and trust report

`trust.json` is generated after the source catalog and is loaded by the Almanac's **Data trust** page. Its schema is:

- `generated` — UTC build timestamp;
- `summary` — source counts by freshness status, current grid/owned-cell counts, lens count, duplicate lens ids, mean coverage and the number of lenses under half coverage;
- `sources[]` — one row per source with `vintage`, latest cache `retrieved` timestamp, `age_days`, declared `refresh_cadence_days`, freshness `status` (`fresh`, `attention`, `due`, `unknown`) and an input checksum fingerprint;
- `layers[]` — one row per lens with data file, source id, non-null cell count, total/metropolitan/overseas coverage shares and time-series year count;
- `reproducibility` — offline rebuild and validation commands plus a combined `source_fingerprint`.

Freshness cadences are maintainer refresh policy, not upstream publication guarantees. `attention` starts at 80% of the cadence and `due` after it. Coverage is measured on owned hexes at the lens default/latest year; overseas coverage is separated so structural source gaps are visible. These are report fields, not rendering rules.
