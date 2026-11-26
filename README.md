# franceciv: France as a strategy game, built from real data

A French adaptation of Andrej Karpathy's MIT-licensed [`usaciv`](https://karpathy.ai/usaciv/) visualizer.
The original browser engine, rendering art, interaction model and pipeline architecture are vendored here with attribution; this repository replaces the United States data spine with French public data.

**Current status: metropolitan-France MVP.** It renders France and Corsica at 8 km hex resolution, with régions, départements, INSEE aires d'attraction des villes, terrain, land cover, population, GDP and employment-derived yields.

![France drawn as a 4X strategy map](docs/images/france-mvp.png)

## What works in the MVP

- Painted hex terrain for metropolitan France from ETOPO1 elevation and CORINE Land Cover 2018 land cover.
- 13 metropolitan régions and 96 départements from Etalab contour files.
- 172 city banners based on INSEE 2020 aires d'attraction des villes (AAV), including cross-border AAVs restricted to their French communes.
- Five yields: Food, Production, Gold, Science and Culture.
  - Gold is Eurostat NUTS-3 GDP in current euros.
  - The other yields are Eurostat employment by high-level NACE industry.
  - Because Eurostat data is département-level, AAV values are allocated in proportion to commune population and should be read as estimates.
- Population density, GDP per capita, employment density, industry, forest, farmland and built-up lenses.
- Power-generation and storage resources from the national ODRÉ registry: nuclear, hydro, pumped storage, gas/coal, wind, solar and batteries.
- The original interactive map, city panels, minimap, search, sharing and lens histogram UI.

## Explicitly not in the MVP yet

The original US layers for citizens, districts, infrastructure, military sites, wonders, trade routes and disasters are not yet implemented rather than shown with invalid American coordinates or statistics. The UI still contains some inherited US-oriented explanatory copy and advisor assumptions; those panels are best treated as scaffolding until the corresponding French datasets are implemented.

Other known limitations:

- GDP and employment are 2023 Eurostat NUTS-3 values, not true AAV-level accounts.
- NACE data is aggregated, so several original industry categories are approximate allocations rather than direct observations.
- Median income, rent, home values, unemployment, education, growth and yearly population series are currently null because the INSEE commune/AAV statistical extraction is not yet wired into the frontend contracts.
- Overseas France is excluded; Corsica is included.
- Some art classification rules inherited from the United States may need France-specific visual tuning.

## Quick start

Install [uv](https://docs.astral.sh/uv/), then:

```bash
uv run python -m pipeline serve
```

Open the printed local URL. The generated data in `web/data/` is committed, so no download is required for viewing.

## Rebuilding the data

```bash
uv run python -m pipeline fetch fr_boundaries fr_aav natural_earth etopo fr_corine fr_eurostat fr_energy
uv run python -m pipeline process fr_boundaries fr_aav natural_earth etopo fr_corine fr_eurostat fr_energy
uv run python -m pipeline build world france_core resources catalog
```

Downloads are cached under `data/raw/` with provenance manifests. Generated browser data is written to `web/data/`.

## Data sources

- Etalab / geo.api.gouv.fr: current région, département and commune boundaries, commune populations and centroids.
- INSEE: 2020 aires d'attraction des villes, 2026 vintage geography.
- Eurostat regional accounts: `nama_10r_3gdp`, `nama_10r_3gva`, `nama_10r_3empers` for 2023.
- CORINE Land Cover 2018, served through the IGN Géoplateforme WMS.
- ODRÉ national registry of electricity generation and storage installations.
- NOAA ETOPO1 elevation and bathymetry.
- Natural Earth 1:50m neighbouring countries, lakes and rivers.

The in-app Almanac/source catalogue is generated from the same source registry used by the pipeline.

## Architecture

The project intentionally keeps Karpathy's simple architecture:

- `pipeline/sources/`: download and normalize source data into `data/interim/`.
- `pipeline/build/`: reconcile data onto the shared hex grid and write browser JSON contracts.
- `web/`: dependency-free ES modules and Canvas 2D; no npm, framework or frontend build step.

See `docs/DATA_CONTRACTS.md` for the browser/pipeline interface. French concepts are deliberately mapped onto the original contract: région → state, département → county, and aire d'attraction des villes → metro/city. That mapping is a compatibility layer, not a claim that the legal or statistical concepts are identical.

## License and attribution

The upstream `usaciv` source is MIT-licensed and its license is preserved in `LICENSE`. France-specific modifications in this repository are also available under the MIT license. Public data remains subject to the terms of its respective publishers.
