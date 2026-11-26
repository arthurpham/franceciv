"""Commune-level median housing prices derived from DVF transactions."""

import csv

from ..core.source import Source, SourceInfo

URL = "https://static.data.gouv.fr/resources/prix-immobiliers-medians-au-m2-par-commune-dvf-2024-2025/20261026-120736/prix-medians-dvf-par-commune.csv"


class FrenchHousing(Source):
    info = SourceInfo(
        id="fr_housing",
        title="Median housing prices per m² by commune",
        publisher="OpenParcels, derived from DGFiP/Etalab DVF",
        homepage="https://www.data.gouv.fr/datasets/prix-immobiliers-medians-au-m2-par-commune-dvf-2024-2025",
        license="Licence Ouverte 2.0 (Etalab)",
        description="Median sale prices per square metre by commune for apartments and houses, calculated from "
        "geolocated DVF transactions in 2024–2025. No individual transaction, parcel or address is redistributed. "
        "DVF excludes Alsace-Moselle and Mayotte.",
        used_for=["House-price lens", "Apartment-price lens"],
    )

    def fetch(self, force=False):
        self.download(URL, "prix-medians-dvf-par-commune.csv", force=force)

    def process(self):
        rows = []
        with open(self.raw_dir / "prix-medians-dvf-par-commune.csv", newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                def num(key):
                    try: return float(r[key]) if r.get(key) else None
                    except ValueError: return None
                def integer(key):
                    try: return int(r[key]) if r.get(key) else 0
                    except ValueError: return 0
                rows.append({
                    "code": r["code_insee"], "apartment_price": num("prix_median_m2_appartement"), "apartment_sales": integer("ventes_appartement"),
                    "house_price": num("prix_median_m2_maison"), "house_sales": integer("ventes_maison"),
                    "period": [r.get("periode_debut"), r.get("periode_fin")],
                })
        return {"vintage": "DVF commune medians, sales in 2024–2025", "_files": ["prix-medians-dvf-par-commune.csv"], "rows": rows}
