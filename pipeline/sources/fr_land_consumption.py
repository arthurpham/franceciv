"""Communal artificialization and consumption of natural/agricultural/forest land."""

import csv

from ..core.source import Source, SourceInfo

URL = "https://static.data.gouv.fr/resources/consommation-despaces-naturels-agricoles-et-forestiers-du-1er-janvier-2011-au-1er-janvier-2025/20260724-142909/conso-com.csv"


def num(value):
    try:
        return float(value) if value not in (None, "", "NA") else None
    except ValueError:
        return None


class FrenchLandConsumption(Source):
    info = SourceInfo(
        id="fr_land_consumption",
        title="Consumption of natural, agricultural and forest land 2011–2025",
        publisher="Cerema / national soil-artificialization observatory",
        homepage="https://artificialisation.developpement-durable.gouv.fr/",
        license="Licence Ouverte 2.0",
        description="Annual commune indicators derived from French land-registry files: artificialized land stock and consumption of natural, agricultural and forest land by period and destination.",
        used_for=["Artificialized-land, land-consumption and housing-driven consumption lenses"],
    )

    def fetch(self, force=False):
        self.download(URL, "conso_com.csv", force=force)

    def process(self):
        rows = {}
        with open(self.raw_dir / "conso_com.csv", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                code = row["idcom"]
                surface = num(row.get("surfcom2025"))
                total = num(row.get("naf11art25"))
                recent = num(row.get("naf21art25"))
                housing = num(row.get("art11hab25"))
                if not surface:
                    continue
                rows[code] = {
                    "artificialized": num(row.get("artcom1125")),
                    "consumed_share": total / surface if total is not None else None,
                    "recent_consumed_share": recent / surface if recent is not None else None,
                    "housing_share": housing / total if housing is not None and total else None,
                    "surface_m2": surface,
                    "consumed_m2": total,
                    "recent_consumed_m2": recent,
                }
        return {
            "vintage": "Cerema national soil-artificialization observatory, 2011–2025 communal extract (COG 2025)",
            "_files": ["conso_com.csv"],
            "period": "2011-01-01 to 2025-01-01",
            "communes": rows,
        }
