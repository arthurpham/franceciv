"""Annual commune housing-price series derived from DVF transactions."""

from __future__ import annotations

import csv
from collections import defaultdict

from ..core.source import Source, SourceInfo

URL = "https://static.data.gouv.fr/resources/prix-immobilier-par-commune-ventes-2014-a-2025-dvf-millesime-2026/20261026-112727/prix-immobilier-communes-series-2014-2025.csv"
FILE = "prix-immobilier-communes-series-2014-2025.csv"


def integer(text):
    try:
        return int(text) if text else None
    except ValueError:
        return None


def number(text):
    try:
        return float(text) if text else None
    except ValueError:
        return None


class FrenchHousingHistory(Source):
    info = SourceInfo(
        id="fr_housing_history",
        title="Annual housing prices by commune, DVF 2014–2025",
        publisher="Terralyse, derived from DGFiP DVF",
        homepage="https://www.data.gouv.fr/datasets/prix-immobilier-par-commune-ventes-2014-a-2025-dvf-millesime-2026",
        license="Licence Ouverte 2.0 (Etalab)",
        description="Annual median sale price per square metre and sale counts by commune for 2014–2025. Terralyse groups "
        "DVF lines by transaction and covers communes with enough usable sales; sparse commune coverage is intentional "
        "missingness rather than zero-priced housing. Municipal-arrondissement rows in Paris, Lyon and Marseille are aggregated "
        "back to their parent communes with transaction-count weights. That arrondissement detail begins in 2021, so the three parent communes have no earlier annual rows. DVF excludes Alsace-Moselle and Mayotte.",
        used_for=["Housing-price history lens"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=False)

    @staticmethod
    def parent_code(code):
        if code.startswith("751"):
            return "75056"
        if code.startswith("132") and len(code) == 5:
            return "13055"
        if code.startswith("6938"):
            return "69123"
        return code

    @staticmethod
    def combine(entries):
        if len(entries) == 1:
            return entries[0]
        sales = sum(e["sales"] for e in entries)

        def weighted(key):
            present = [e for e in entries if e.get(key) is not None]
            weight = sum(e["sales"] for e in present)
            return round(sum(e[key] * e["sales"] for e in present) / weight, 2) if weight else None

        return {
            "price": weighted("price"),
            "sales": sales,
            "house_price": weighted("house_price"),
            "apartment_price": weighted("apartment_price"),
        }

    def process(self):
        entries = defaultdict(list)
        years = set()
        with open(self.raw_dir / FILE, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                code = row.get("code_insee")
                year = integer(row.get("annee"))
                price = number(row.get("prix_m2_median"))
                sales = integer(row.get("ventes"))
                if not code or year is None or price is None or not sales:
                    continue
                entries[(self.parent_code(code), str(year))].append({
                    "price": price,
                    "sales": sales,
                    "house_price": number(row.get("prix_m2_median_maison")),
                    "apartment_price": number(row.get("prix_m2_median_appartement")),
                })
                years.add(year)
        rows = defaultdict(dict)
        for (code, year), group in entries.items():
            rows[code][year] = self.combine(group)
        print(f"    {len(rows)} communes with annual price rows, {min(years)}–{max(years)}")
        return {
            "vintage": "Terralyse DVF commune annual series, sales 2014–2025, millésime 2026",
            "_files": [FILE],
            "years": sorted(years),
            "communes": dict(rows),
        }
