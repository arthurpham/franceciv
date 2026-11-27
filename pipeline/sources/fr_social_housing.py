"""Commune-level social-housing share."""

import csv

from ..core.source import Source, SourceInfo

URL = "https://opendata.caissedesdepots.fr/api/explore/v2.1/catalog/datasets/logements-sociaux-dans-les-communes/exports/csv?select=code_commune,taux_de_logements_sociaux"


class FrenchSocialHousing(Source):
    info = SourceInfo(
        id="fr_social_housing",
        title="Taux de logements sociaux dans les communes",
        publisher="Caisse des Dépôts, SDES and INSEE",
        homepage="https://www.data.gouv.fr/datasets/taux-de-logements-sociaux-dans-les-communes-en-2023",
        license="Licence Ouverte 2.0",
        description="2023 commune-level social-housing units in the RPLS as a percentage of primary residences. The published "
        "indicator excludes habitat spécifique and certain SEM stock and is not directly comparable with the legal SRU article-55 rate.",
        used_for=["Social-housing lens"],
    )

    def fetch(self, force=False):
        self.download(URL, "social_housing.csv", force=force)

    def process(self):
        rows = {}
        with open(self.raw_dir / "social_housing.csv", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f, delimiter=";"):
                code = (r.get("code_commune") or "").strip().zfill(5)
                try: value = float(r.get("taux_de_logements_sociaux") or "")
                except ValueError: continue
                if len(code) == 5 and 0 <= value <= 100: rows[code] = value
        print(f"    {len(rows)} communes with social-housing shares; mean {sum(rows.values())/len(rows):.1f}%")
        if len(rows) < 30_000:
            raise ValueError("unexpectedly low social-housing coverage")
        return {"vintage": "RPLS 2023 / INSEE primary residences", "_files": ["social_housing.csv"], "rows": rows}
