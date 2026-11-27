"""ADEME waste and circular-economy infrastructure aggregations."""

import json
import urllib.parse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from ..core.source import Source, SourceInfo

DEPARTMENTS = [*(f"{i:02d}" for i in range(1, 20)), "2A", "2B", *(f"{i:02d}" for i in range(21, 96)), "971", "972", "973", "974", "976"]
SINOE = "https://data.ademe.fr/data-fair/api/v1/datasets/sinoe-(r)-annuaire-des-decheteries-dma/values_agg"
QFDMOD = "https://data.ademe.fr/data-fair/api/v1/datasets/longue-vie-aux-objets-acteurs-de-leconomie-circulaire/values_agg"
SINOE_YEAR = 2026


def encode(params):
    return urllib.parse.urlencode(params)


def sinoe_url(dep):
    return SINOE + "?" + encode({
        "field": "C_COMM", "metric": "cardinality", "metric_field": "C_SERVICE",
        "qs": f"ANNEE:{SINOE_YEAR} AND C_DEPT:{dep}", "size": "0", "agg_size": "1000",
    })


def circular_url(dep):
    return QFDMOD + "?" + encode({
        "field": "code_commune,type_de_services", "metric": "cardinality", "metric_field": "identifiant",
        "qs": f"_reverse_geoloc-departement.insee_dep:{dep}", "size": "0", "agg_size": "1000",
    })


class FrenchCircularEconomy(Source):
    info = SourceInfo(
        id="fr_circular_economy",
        title="Waste and circular-economy infrastructure",
        publisher="ADEME Open Data",
        homepage="https://data.ademe.fr/",
        license="Licence Ouverte 2.0",
        description="Current SINOE recycling-centre registry and server-side distinct-actor aggregations from ADEME's Que Faire De Mes Objets et Déchets circular-economy actor database. Circular-economy actors include crowd/contributed entries and a small number of establishments whose SIREN status is closed, so densities are infrastructure availability indicators rather than a statutory registry.",
        used_for=["Recycling-centre, repair-service and reuse-infrastructure lenses"],
    )

    def fetch(self, force=False):
        jobs = [(sinoe_url(dep), f"sinoe_{dep}.json") for dep in DEPARTMENTS]
        jobs += [(circular_url(dep), f"circular_{dep}.json") for dep in DEPARTMENTS]
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda job: self.download(job[0], job[1], force=force), jobs))

    def process(self):
        recycling = defaultdict(int)
        services = defaultdict(lambda: defaultdict(float))
        files = []
        for dep in DEPARTMENTS:
            name = f"sinoe_{dep}.json"
            files.append(name)
            data = json.load(open(self.raw_dir / name, encoding="utf-8"))
            if data.get("total_other"):
                raise ValueError(f"truncated SINOE commune aggregation: {dep}")
            for commune in data.get("aggs", []):
                code = str(commune.get("value") or "").zfill(5)
                if code and code != "00000":
                    recycling[code] += int(commune.get("metric") or 0)
        for dep in DEPARTMENTS:
            name = f"circular_{dep}.json"
            files.append(name)
            data = json.load(open(self.raw_dir / name, encoding="utf-8"))
            if data.get("total_other"):
                raise ValueError(f"truncated circular-economy commune aggregation: {dep}")
            for commune in data.get("aggs", []):
                code = str(commune.get("value") or "").zfill(5)
                if not code or code == "00000":
                    continue
                services[code]["actors"] += commune.get("metric") or 0
                for service in commune.get("aggs", []):
                    key = service.get("value")
                    if key:
                        services[code][key] += service.get("metric") or 0
        if len(recycling) < 4_000 or len(services) < 20_000:
            raise ValueError(f"unexpected circular infrastructure coverage: {len(recycling)} recycling communes, {len(services)} actor communes")
        return {
            "vintage": f"ADEME SINOE recycling centres, {SINOE_YEAR}; circular-economy actors, current open-data extract",
            "_files": files,
            "year": SINOE_YEAR,
            "recycling_centres": dict(recycling),
            "services": {k: dict(v) for k, v in services.items()},
        }
