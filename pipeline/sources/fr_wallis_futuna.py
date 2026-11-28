"""INSEE/STSEE Wallis-et-Futuna census publication tables."""

import unicodedata

from ..core.source import Source, SourceInfo
from .fr_functional_geographies import workbook_from_xlsx

URL = "https://www.insee.fr/fr/statistiques/fichier/8272934/IP2021.xlsx"
FILE = "wallis-futuna-2023.xlsx"


def norm(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "")).lower() if c.isalnum())


def pct(v):
    return v / 100 if isinstance(v, (int, float)) else None


class WallisFutunaCensus(Source):
    info = SourceInfo(
        id="fr_wallis_futuna",
        title="Wallis-et-Futuna census indicators 2023",
        publisher="INSEE / STSEE",
        homepage="https://www.insee.fr/fr/statistiques/8272934",
        license="Licence Ouverte 2.0",
        description="Population, age, household, employment and education indicators from the 2023 Wallis-et-Futuna census publication.",
        used_for=["Wallis-et-Futuna circonscription-level demographic and employment lenses"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=True)

    def process(self):
        wb = workbook_from_xlsx((self.raw_dir / FILE).read_bytes())
        fig1 = list(wb["Figure 1"].iter_rows(values_only=True))
        comp = {str(r[0]).strip(): r for r in wb["Tableau complémentaire 1"].iter_rows(values_only=True) if r and r[0]}
        emp = {str(r[0]).strip(): r for r in wb["Figure 5"].iter_rows(values_only=True) if r and r[0]}
        pop_rows = {}
        for row in fig1:
            label = str(row[0] or "")
            for prefix, key in [("    Circonscription d'Alo", "alo"), ("    Circonscription de Sigave", "sigave"), ("Île de Wallis, circonscription d'Uvea", "uvea")]:
                if label.startswith(prefix):
                    pop_rows[key] = {"change_2018_2023": pct(row[4]), "change_2003_2023": pct(row[5])}
        out = {}
        for key, island in [("alo", "Futuna"), ("sigave", "Futuna"), ("uvea", "Wallis")]:
            col = 4 if island == "Wallis" else 5
            out[key] = {
                **pop_rows[key],
                "median_age": comp["Âge médian"][col],
                "children": pct(comp["Part des 0-14 ans"][col]),
                "seniors": pct(comp["Part des 65 ans ou plus"][col]),
                "employment": pct(emp[island][1]),
                "unemployment": pct(emp[island][2]),
                "source_resolution": "circonscription" if key != "uvea" else "circonscription",
                "island_resolution": island,
            }
        print(f"    circonscriptions: {len(out)}")
        return {
            "vintage": "INSEE/STSEE recensement de Wallis-et-Futuna 2023, Insee Première 2021 (published 2024-10-24)",
            "_files": [FILE],
            "year": 2023,
            "circonscriptions": out,
        }
