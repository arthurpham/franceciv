"""French presidential election results by commune."""

from __future__ import annotations

import csv

import xlrd

from ..core.source import Source, SourceInfo

URL_2022 = "https://static.data.gouv.fr/resources/election-presidentielle-des-10-et-24-avril-2022-resultats-definitifs-du-2nd-tour/20220428-142333/resultats-par-niveau-subcom-t2-france-entiere.txt"
FILE_2022 = "presidentielle-2022-t2-communes.txt"
URL_2017 = "https://static.data.gouv.fr/resources/election-presidentielle-des-23-avril-et-7-mai-2017-resultats-definitifs-du-2nd-tour-par-communes/20170511-093054/Presidentielle_2017_Resultats_Communes_Tour_2_c.xls"
FILE_2017 = "Presidentielle_2017_Resultats_Communes_Tour_2_c.xls"
OVERSEAS = {"ZA": "971", "ZB": "972", "ZC": "973", "ZD": "974", "ZM": "976"}


def commune_code_2022(vals):
    if vals[0] in OVERSEAS:
        return OVERSEAS[vals[0]] + vals[2][-2:]
    if vals[0] in {"ZN", "ZP", "ZS", "ZW", "ZX", "ZZ"}:
        return None
    return (vals[0] + vals[2]).zfill(5)


def xls_text(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def commune_code_2017(dep_value, commune_value):
    dep = xls_text(dep_value)
    commune = xls_text(commune_value)
    if dep in OVERSEAS:
        return OVERSEAS[dep] + commune.zfill(2)[-2:]
    if dep in {"ZN", "ZP", "ZS", "ZW", "ZX", "ZZ"}:
        return None
    if dep in {"2A", "2B"}:
        return dep + commune.zfill(3)[-3:]
    try:
        return f"{int(dep):02d}{int(commune):03d}"
    except ValueError:
        return None


class FrenchElections(Source):
    info = SourceInfo(
        id="fr_elections",
        title="2017 and 2022 presidential elections, definitive second-round results",
        publisher="Ministère de l'Intérieur",
        homepage="https://www.data.gouv.fr/datasets/election-presidentielle-des-10-et-24-avril-2022-resultats-definitifs-du-2nd-tour",
        license="License not specified in the mirrored datasets",
        description="Definitive second-round results by commune for 2017 and 2022, mirrored by data.gouv. Rows carry "
        "registered voters, abstention, valid ballots, and Macron/Le Pen votes; both elections opposed the same two candidates.",
        used_for=["2022 election lenses", "Election history lenses"],
    )

    def fetch(self, force=False):
        self.download(URL_2022, FILE_2022, force=force, expect_binary=False)
        self.download(URL_2017, FILE_2017, force=force, expect_binary=True)

    def process_2022(self):
        rows = {}
        with open(self.raw_dir / FILE_2022, encoding="cp1252", newline="") as f:
            for vals in csv.reader(f, delimiter=";"):
                if len(vals) < 33 or vals[0] == "Code du département":
                    continue
                commune = commune_code_2022(vals)
                if not commune:
                    continue
                try:
                    rows[commune] = {
                        "registered": int(vals[5]), "abstentions": int(vals[6]), "voters": int(vals[8]),
                        "valid": int(vals[16]), "macron": int(vals[23]), "le_pen": int(vals[30]),
                    }
                except (ValueError, IndexError):
                    continue
        return rows

    def process_2017(self):
        rows = {}
        sheet = xlrd.open_workbook(self.raw_dir / FILE_2017).sheet_by_index(0)
        for r in range(4, sheet.nrows):
            commune = commune_code_2017(sheet.cell_value(r, 0), sheet.cell_value(r, 2))
            if not commune:
                continue
            try:
                rows[commune] = {
                    "registered": int(sheet.cell_value(r, 4)), "abstentions": int(sheet.cell_value(r, 5)),
                    "voters": int(sheet.cell_value(r, 7)), "valid": int(sheet.cell_value(r, 15)),
                    "macron": int(sheet.cell_value(r, 22)), "le_pen": int(sheet.cell_value(r, 29)),
                }
            except (ValueError, IndexError):
                continue
        return rows

    def process(self):
        rows2022 = self.process_2022()
        rows2017 = self.process_2017()
        print(f"    {len(rows2022)} commune results in 2022; {len(rows2017)} in 2017")
        return {
            "vintage": "2017 and 2022 presidential elections, definitive second-round results",
            "_files": [FILE_2022, FILE_2017],
            "communes": rows2022,
            "history": {"2017": rows2017, "2022": rows2022},
        }
