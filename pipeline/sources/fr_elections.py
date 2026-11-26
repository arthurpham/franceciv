"""French presidential election results by commune."""

from __future__ import annotations

import csv

from ..core.source import Source, SourceInfo

URL = "https://static.data.gouv.fr/resources/election-presidentielle-des-10-et-24-avril-2022-resultats-definitifs-du-2nd-tour/20220428-142333/resultats-par-niveau-subcom-t2-france-entiere.txt"
FILE = "presidentielle-2022-t2-communes.txt"


class FrenchElections(Source):
    info = SourceInfo(
        id="fr_elections",
        title="2022 presidential election, definitive second-round results",
        publisher="Ministère de l'Intérieur",
        homepage="https://www.data.gouv.fr/datasets/election-presidentielle-des-10-et-24-avril-2022-resultats-definitifs-du-2nd-tour",
        license="License not specified in the mirrored dataset",
        description="Definitive 2022 second-round results by commune, mirrored as a flat text file by data.gouv. "
        "Rows carry registered voters, abstention, valid ballots, and Macron/Le Pen votes.",
        used_for=["2022 election lenses"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=False)

    def process(self):
        rows = {}
        with open(self.raw_dir / FILE, encoding="cp1252", newline="") as f:
            for vals in csv.reader(f, delimiter=";"):
                if len(vals) < 33 or vals[0] == "Code du département":
                    continue
                commune = (vals[0] + vals[2]).zfill(5)
                try:
                    rows[commune] = {
                        "registered": int(vals[5]), "abstentions": int(vals[6]), "voters": int(vals[8]),
                        "valid": int(vals[16]), "macron": int(vals[23]), "le_pen": int(vals[30]),
                    }
                except (ValueError, IndexError):
                    continue
        print(f"    {len(rows)} commune results")
        return {"vintage": "2022 presidential election, definitive results", "_files": [FILE], "communes": rows}
