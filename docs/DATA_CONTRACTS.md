# Data contracts (v2, France)

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

### connectivity.json

Commune connectivity lenses. Fiber values are eligible premises shares from ARCEP; EV-charging values are consolidated public charge points per 10,000 residents. Mobile lenses use ARCEP operator-reported physical site deployment: `mobile_operators` is the population-weighted number of operators with a local 4G-capable site, and `mobile_5g` is the population share in communes with a local 5G-capable site. Mobile values measure infrastructure presence, not theoretical signal coverage or measured quality; a commune without a site may still receive signal from neighbouring communes. Commune values are aggregated to hexes by centroid. IRVE zero means no published public charge point, not missing data; arrondissement charge points are attributed to Paris, Lyon and Marseille commune totals.

### quality_life.json

DVF housing-price and DREES healthcare-access lenses are weighted commune aggregates with source-specific geographic exclusions documented in each lens. `social_housing` is the population-weighted commune share of primary residences that are social housing in the 2023 RPLS; it excludes habitat spécifique and certain SEM stock and is not comparable with the legal SRU article-55 rate.

### flood.json

Physical river-flood exposure. Values are approximate hex-area shares derived from official TRI/Géorisques rare-or-millennial river-overflow WMS rasters. They are not parcel-level risk determinations, damage estimates, or a substitute for regulatory hazard maps.

### risk.json

Natural-risk zoning lenses sampled from official Géorisques/BRGM WMS rasters. `clay_shrink_swell`, `seismic_zone` and `radon_potential` are normalized area-weighted class indices, not probabilities, damage estimates or measurements. Clay low/medium/high and radon low/moderate/high classes are weighted ⅓, ⅔ and 1; seismic zones 1–5 are weighted 0.2–1. Values are raster-sampled hex estimates and may be null outside the published mainland raster coverage.

### electricity.json

Enedis electricity-consumption lenses. Values are 2024 MWh per department resident for total consumption and broad residential, tertiary, industrial and agricultural sectors. Department values reflect where metered load is located; Enedis coverage gaps (including Corsica and local-distribution areas) mean low values are not always low use.

### public_services.json

Recorded-crime, school-density and INSEE Base permanente des équipements lenses. Crime is department-level recorded crime and not victimization prevalence. Equipment lenses use detailed BPE 2024 rows aggregated by commune centroid to map hexes. `essential_services` is the population-weighted count of six categories present in a commune: food shops, pharmacy, general practitioner, primary school, post office/relais and library. Equipment counts use `NBEQUIDENT` where INSEE groups identical facilities; they measure presence/density, not quality or capacity. Paris, Lyon and Marseille arrondissement records are attributed to commune totals.

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
