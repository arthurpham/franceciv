"""ARCEP commune fixed-broadband technology eligibility statistics."""

import csv

from ..core.source import Source, SourceInfo

URL = "https://data.arcep.fr/fixe/maconnexioninternet/statistiques/last/commune/commune_techno.csv"


class FrenchBroadband(Source):
    info = SourceInfo(
        id="fr_broadband",
        title="ARCEP fixed-broadband eligibility by commune",
        publisher="ARCEP",
        homepage="https://www.data.gouv.fr/datasets/ma-connexion-internet",
        license="Licence Ouverte 2.0 (Etalab)",
        description="Counts of connectable premises by commune and technology from the Ma connexion internet "
        "statistical extract. The map lens uses fiber-to-the-home eligible premises divided by all premises.",
        used_for=["Fiber eligibility lens"],
    )

    def fetch(self, force=False):
        self.download(URL, "commune_techno.csv", force=force)

    def process(self):
        rows = []
        with open(self.raw_dir / "commune_techno.csv", newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter=";"):
                if r.get("type") != "all":
                    continue
                try:
                    rows.append({"code": r["code_insee"], "premises": int(r["nbr"]), "fiber": int(r["elig_ftth"]), "date": r.get("date")})
                except (KeyError, ValueError):
                    continue
        date = max((r["date"] for r in rows if r.get("date")), default=None)
        return {"vintage": f"ARCEP Ma connexion internet commune statistics, reference date {date}", "_files": ["commune_techno.csv"], "date": date, "rows": rows}
