"""Ministry school directory."""

import csv
from collections import Counter, defaultdict

from ..core.source import Source, SourceInfo

URL = "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/fr-en-annuaire-education/exports/csv?use_labels=true"


class FrenchSchools(Source):
    info = SourceInfo(
        id="fr_schools",
        title="Annuaire de l'Éducation nationale",
        publisher="Ministry of National Education",
        homepage="https://www.data.gouv.fr/datasets/annuaire-de-leducation",
        license="Licence Ouverte 2.0",
        description="Directory of open public and private schools, including type, commune, department and location.",
        used_for=["School-access lenses"],
    )

    def fetch(self, force=False):
        self.download(URL, "annuaire_education.csv", force=force)

    def process(self):
        counts = defaultdict(Counter)
        total = 0
        with open(self.raw_dir / "annuaire_education.csv", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f, delimiter=";"):
                if r.get("etat") != "OUVERT":
                    continue
                dep = r.get("Code_departement") or ""
                if len(dep) == 3 and dep.startswith("0"):
                    dep = dep.lstrip("0").zfill(2)
                typ = r.get("Type_etablissement") or "Other"
                counts[dep][typ] += 1
                total += 1
        rows = [{"department": dep, **dict(c)} for dep, c in sorted(counts.items())]
        return {"vintage": "Annuaire de l'Éducation nationale, current export", "_files": ["annuaire_education.csv"], "departments": rows, "total": total}
