"""Enedis annual electricity consumption by commune and activity sector."""

import json
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from ..core.source import Source, SourceInfo

DATASET = "https://opendata.enedis.fr/data-fair/api/v1/datasets/consommation-electrique-par-secteur-dactivite-commune"
BASE = DATASET + "/values_agg"
LINES = DATASET + "/lines"
YEAR = "2025"
HEATING_YEAR = "2024"  # Enedis 2025 rows no longer carry the electric-heating housing attribute.
DEPARTMENTS = [*(f"{i:02d}" for i in range(1, 20)), "2A", "2B", *(f"{i:02d}" for i in range(21, 96))]
RESIDENTIAL_SELECT = "code_commune,part_thermosensible,taux_de_chauffage_electrique,conso_totale_mwh,nb_sites,nombre_d_habitants"


def sector_url(dep):
    query = urllib.parse.urlencode({
        "field": "code_commune,code_grand_secteur", "metric": "sum", "metric_field": "conso_totale_mwh",
        "qs": f"annee:{YEAR} AND code_departement:{dep}", "size": "0", "agg_size": "1000",
    })
    return f"{BASE}?{query}"


def category_url(dep):
    query = urllib.parse.urlencode({
        "field": "code_commune,code_categorie_consommation", "metric": "sum", "metric_field": "conso_totale_mwh",
        "qs": f"annee:{YEAR} AND code_departement:{dep}", "size": "0", "agg_size": "1000",
    })
    return f"{BASE}?{query}"


def residential_url(year):
    query = urllib.parse.urlencode({
        "size": "1000", "qs": f"annee:{year} AND code_grand_secteur:RESIDENTIEL", "select": RESIDENTIAL_SELECT,
    })
    return f"{LINES}?{query}"


class FrenchElectricity(Source):
    info = SourceInfo(
        id="fr_electricity",
        title="Electricity consumption and thermosensitivity by commune and activity sector",
        publisher="Enedis Open Data",
        homepage="https://opendata.enedis.fr/datasets/consommation-electrique-par-secteur-dactivite-commune",
        license="Licence Ouverte 2.0",
        description="Annual electricity consumption on the Enedis distribution network, aggregated server-side by commune and broad activity sector, "
        "plus commune winter thermosensitivity indicators for the consumption year and electric-heating indicators from the most recent rows that publish that housing attribute. Enedis does not serve Corsica, overseas France or some local-distribution areas.",
        used_for=["Electricity-consumption and heating lenses"],
    )

    def fetch(self, force=False):
        jobs = [(sector_url(dep), f"commune_sector_{dep}.json") for dep in DEPARTMENTS]
        jobs += [(category_url(dep), f"commune_category_{dep}.json") for dep in DEPARTMENTS]
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda job: self.download(job[0], job[1], force=force), jobs))

        # Residential heating attributes are only present on residential rows. They are
        # paginated rather than server-aggregated so every commune is retained.
        for prefix, year in (("residential", YEAR), ("heating2024", HEATING_YEAR)):
            url = residential_url(year)
            page = 0
            while url and page < 100:
                name = f"{prefix}_page_{page:02d}.json"
                self.download(url, name, force=force)
                path = self.raw_dir / name
                if not path.exists():
                    break
                with open(path, encoding="utf-8") as f:
                    url = json.load(f).get("next")
                page += 1

    def process(self):
        rows = {}
        files = []
        for dep in DEPARTMENTS:
            name = f"commune_sector_{dep}.json"
            files.append(name)
            with open(self.raw_dir / name, encoding="utf-8") as f:
                data = json.load(f)
            for commune in data.get("aggs", []):
                code = str(commune.get("value") or "").zfill(5)
                if not code or code == "00000":
                    continue
                out = rows.setdefault(code, {"sectors": {}, "consumption_mwh": 0.0})
                for sector in commune.get("aggs", []):
                    value = sector.get("metric")
                    key = sector.get("value")
                    if key and value is not None:
                        out["sectors"][key] = out["sectors"].get(key, 0.0) + value
                        out["consumption_mwh"] += value

        for dep in DEPARTMENTS:
            name = f"commune_category_{dep}.json"
            files.append(name)
            with open(self.raw_dir / name, encoding="utf-8") as f:
                data = json.load(f)
            for commune in data.get("aggs", []):
                code = str(commune.get("value") or "").zfill(5)
                if not code or code == "00000":
                    continue
                out = rows.setdefault(code, {"sectors": {}, "consumption_mwh": 0.0})
                categories = out.setdefault("categories", {})
                for category in commune.get("aggs", []):
                    value = category.get("metric")
                    key = category.get("value")
                    if key and value is not None:
                        categories[key] = categories.get(key, 0.0) + value

        def page_sequence(prefix):
            names = []
            page = 0
            while (self.raw_dir / f"{prefix}_page_{page:02d}.json").exists():
                names.append(f"{prefix}_page_{page:02d}.json")
                page += 1
            return names

        residential_files = page_sequence("residential")
        heating_files = page_sequence("heating2024")
        files.extend(residential_files + heating_files)
        residential_count = heating_count = 0
        for name in residential_files:
            with open(self.raw_dir / name, encoding="utf-8") as f:
                data = json.load(f)
            for r in data.get("results", []):
                code = str(r.get("code_commune") or "").zfill(5)
                if not code or code == "00000":
                    continue
                residential_count += 1
                out = rows.setdefault(code, {"sectors": {}, "consumption_mwh": 0.0})
                out["heat_sensitive_share"] = round((r.get("part_thermosensible") or 0) / 100, 5) if r.get("part_thermosensible") is not None else None
                out["residential_sites"] = r.get("nb_sites")
                out["source_population"] = r.get("nombre_d_habitants")
        for name in heating_files:
            with open(self.raw_dir / name, encoding="utf-8") as f:
                data = json.load(f)
            for r in data.get("results", []):
                code = str(r.get("code_commune") or "").zfill(5)
                if not code or code == "00000":
                    continue
                heating_count += 1
                out = rows.setdefault(code, {"sectors": {}, "consumption_mwh": 0.0})
                out["electric_heating_share"] = round((r.get("taux_de_chauffage_electrique") or 0) / 100, 5) if r.get("taux_de_chauffage_electrique") is not None else None

        if len(rows) < 30_000 or residential_count < 30_000 or heating_count < 30_000:
            raise ValueError(f"unexpected Enedis commune coverage: {len(rows)} communes, {residential_count} residential rows, {heating_count} heating rows")
        return {
            "vintage": f"Enedis electricity consumption and thermosensitivity, {YEAR}",
            "_files": files,
            "year": YEAR,
            "heating_year": HEATING_YEAR,
            "communes": rows,
            "residential_rows": residential_count,
            "heating_rows": heating_count,
        }
