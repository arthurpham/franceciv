"""Interior Ministry recorded crime by department."""

import csv

from ..core.source import Source, SourceInfo

URL = "https://static.data.gouv.fr/resources/bases-statistiques-communale-departementale-et-regionale-de-la-delinquance-enregistree-par-la-police-et-la-gendarmerie-nationales/20260709-120038/donnee-dep-data.gouv-2025-geographie2026-produit-le2026-06-25.csv"


class FrenchCrime(Source):
    info = SourceInfo(
        id="fr_crime",
        title="Recorded crime by department",
        publisher="Ministry of the Interior",
        homepage="https://www.data.gouv.fr/datasets/bases-statistiques-communale-departementale-et-regionale-de-la-delinquance-enregistree-par-la-police-et-la-gendarmerie-nationales",
        license="Licence Ouverte 2.0",
        description="Departmental recorded-crime counts and rates per thousand residents from police and gendarmerie statistics.",
        used_for=["Burglary and violence lenses"],
    )

    def fetch(self, force=False):
        self.download(URL, "crime_departments.csv", force=force)

    def process(self):
        rows = []
        with open(self.raw_dir / "crime_departments.csv", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f, delimiter=";"):
                rows.append({
                    "department": r["Code_departement"], "year": int(r["annee"]), "indicator": r["indicateur"],
                    "count": float(r["nombre"] or 0), "rate": float((r["taux_pour_mille"] or "0").replace(",", ".")),
                    "population": int(r["insee_pop"] or 0),
                })
        year = max(r["year"] for r in rows)
        return {"vintage": f"Interior Ministry recorded crime, {year}", "_files": ["crime_departments.csv"], "rows": rows, "year": year}
