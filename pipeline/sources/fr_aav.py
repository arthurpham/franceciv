"""INSEE aires d'attraction des villes (AAV), France's functional urban areas."""

from __future__ import annotations

import zipfile

from ._resource_util import xlsx_rows
from ..core.source import Source, SourceInfo

URL = "https://www.insee.fr/fr/statistiques/fichier/4803954/AAV2020_au_01-01-2026.zip"
FILE = "AAV2020_au_01-01-2026.zip"
XLSX = "AAV2020_au_01-01-2026.xlsx"


def records(path, sheet):
    rows = xlsx_rows(path, sheet)
    header = None
    for row in rows:
        if row.get("A") in {"AAV2020", "CODGEO"}:
            # Machine-name row: the French label row immediately above it is presentation only.
            header = row
            continue
        if header and row.get("A"):
            yield {name: row.get(col, "") for col, name in header.items()}


class FrenchAAV(Source):
    info = SourceInfo(
        id="fr_aav",
        title="Aires d'attraction des villes 2020",
        publisher="Insee",
        homepage="https://www.insee.fr/fr/information/4803954",
        license="Licence Ouverte 2.0",
        description="Functional urban areas: a dense employment/population pole plus the communes sending at least 15% "
        "of workers to it. This is the closest French equivalent of US metropolitan areas.",
        used_for=["City list and membership", "City footprints", "Metro aggregation"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=True)

    def process(self):
        with zipfile.ZipFile(self.raw_dir / FILE) as z:
            z.extract(XLSX, self.raw_dir)
        path = self.raw_dir / XLSX
        areas = []
        for r in records(path, "AAV2020"):
            code = r.get("AAV2020")
            if not code or code == "000":
                continue
            areas.append({
                "code": code,
                "name": r.get("LIBAAV2020"),
                "class": r.get("TAAV2017"),
                "detailed_class": r.get("TDAAV2017"),
                "commune_count": int(r.get("NB_COM") or 0),
            })
        composition = []
        for r in records(path, "Composition_communale"):
            code = r.get("CODGEO")
            if not code:
                continue
            composition.append({
                "commune": code,
                "name": r.get("LIBGEO"),
                "aav": r.get("AAV2020"),
                "aav_name": r.get("LIBAAV2020"),
                "category": r.get("CATEAAV2020"),
                "department": r.get("DEP"),
                "region": r.get("REG"),
            })
        return {
            "vintage": "AAV 2020, géographie au 01/01/2026",
            "_files": [FILE],
            "areas": areas,
            "composition": composition,
        }
