"""INSEE residential-migration indicators by commune and census year."""

from __future__ import annotations

import csv
import io
import zipfile
from collections import defaultdict

from ..core.source import Source, SourceInfo

URL = "https://api.insee.fr/melodi/file/DS_RP_MIGRES_PRINC/DS_RP_MIGRES_PRINC_2023_CSV_FR"
FILE = "DS_RP_MIGRES_PRINC_2023_CSV_FR.zip"
DATA = "DS_RP_MIGRES_PRINC_2023_data.csv"
YEARS = ("2012", "2017", "2023")
OUTSIDE_DEPARTMENT = ("22", "23", "24", "25T32")


class FrenchMigration(Source):
    info = SourceInfo(
        id="fr_migration",
        title="Residential migration, principal census indicators",
        publisher="INSEE",
        homepage="https://www.data.gouv.fr/datasets/migrations-residentielles-principaux-indicateurs-dossier-complet",
        license="Licence Ouverte 2.0 (Etalab)",
        description="Census principal indicators for residence one year earlier, published at commune level for the "
        "2012, 2017 and 2023 census vintages. Values are census-weighted population estimates, not net migration balances; the extract contains no Mayotte commune rows.",
        used_for=["Residential-mobility history", "Interdepartmental in-migration history"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=True)

    def process(self):
        rows = defaultdict(dict)
        counts = {y: 0 for y in YEARS}
        with zipfile.ZipFile(self.raw_dir / FILE) as zf:
            with zf.open(DATA) as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
                for row in csv.DictReader(text, delimiter=";"):
                    if (
                        row.get("GEO_OBJECT") != "COM"
                        or row.get("AGE") != "Y_GE1"
                        or row.get("TIME_PERIOD") not in YEARS
                        or row.get("RP_MEASURE") != "POP"
                    ):
                        continue
                    code = row["GEO"]
                    year = row["TIME_PERIOD"]
                    category = row["PREV_RES_AREA"]
                    if category not in {"_T", "20_30", *OUTSIDE_DEPARTMENT}:
                        continue
                    try:
                        value = float(row["OBS_VALUE"])
                    except ValueError:
                        continue
                    out = rows[code].setdefault(year, {"total": 0.0, "other_commune": 0.0, "outside_department": 0.0})
                    if category == "_T":
                        out["total"] = value
                    elif category == "20_30":
                        out["other_commune"] = value
                    else:
                        out["outside_department"] += value
                    counts[year] += 1

        communes = {}
        for code, by_year in rows.items():
            complete = {}
            for year in YEARS:
                row = by_year.get(year)
                if row and row["total"] > 0:
                    complete[year] = {k: round(v, 5) for k, v in row.items()}
            if complete:
                communes[code] = complete
        print(f"    {len(communes)} commune migration rows; category rows by year: {counts}")
        return {
            "vintage": "INSEE residential-migration principal indicators, census years 2012, 2017 and 2023",
            "_files": [FILE],
            "years": [int(y) for y in YEARS],
            "communes": communes,
        }
