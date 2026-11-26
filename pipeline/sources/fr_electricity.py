"""Enedis annual electricity consumption by department."""

import json
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..core.source import Source, SourceInfo

BASE = "https://opendata.enedis.fr/data-fair/api/v1/datasets/consommation-electrique-par-secteur-dactivite-commune/metric_agg"
YEAR = "2024"
DEPARTMENTS = [*(f"{i:02d}" for i in range(1, 20)), "2A", "2B", *(f"{i:02d}" for i in range(21, 96))]


def url_for(dep):
    query = urllib.parse.urlencode({
        "metric": "sum", "metric_field": "conso_totale_mwh", "qs": f"annee:{YEAR} AND code_departement:{dep}",
    })
    return f"{BASE}?{query}"


class FrenchElectricity(Source):
    info = SourceInfo(
        id="fr_electricity",
        title="Electricity consumption by commune and activity sector",
        publisher="Enedis Open Data",
        homepage="https://opendata.enedis.fr/datasets/consommation-electrique-par-secteur-dactivite-commune",
        license="Licence Ouverte 2.0",
        description="Annual electricity consumption on the Enedis distribution network. The pipeline uses the data-fair aggregation API to sum 2024 commune/sector rows by department.",
        used_for=["Electricity-consumption lens"],
    )

    def fetch(self, force=False):
        # The shared download manifest is not thread-safe; these responses are tiny.
        for dep in DEPARTMENTS:
            self.download(url_for(dep), f"consumption_{dep}.json", force=force)

    def process(self):
        rows = []
        for dep in DEPARTMENTS:
            with open(self.raw_dir / f"consumption_{dep}.json", encoding="utf-8") as f:
                d = json.load(f)
            rows.append({"code": dep, "consumption_mwh": d.get("metric"), "rows": d.get("total")})
        return {"vintage": f"Enedis electricity consumption, {YEAR}", "_files": [f"consumption_{dep}.json" for dep in DEPARTMENTS], "departments": rows}
