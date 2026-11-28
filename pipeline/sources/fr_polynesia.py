"""ISPF French Polynesia census commune workbooks."""

import unicodedata
from urllib.parse import quote

from ..core.source import Source, SourceInfo
from .fr_functional_geographies import workbook_from_xlsx

BASE = "https://www.ispf.pf/fiches-geo/2024/xlsx/Fiche géographique Commune - {}.xlsx"
COMMUNES = ["Anaa","Arue","Arutua","Bora Bora","Faa'a","Fakarava","Fangatau","Fatu Hiva","Gambier","Hao","Hikueru","Hitiaa O Te Ra","Hiva Oa","Huahine","Mahina","Makemo","Manihi","Maupiti","Moorea-Maiao","Napuka","Nuku Hiva","Nukutavake","Paea","Papara","Papeete","Pirae","Pukapuka","Punaauia","Raivavae","Rangiroa","Rapa","Reao","Rimatara","Rurutu","Tahaa","Tahuata","Taiarapu-Est","Taiarapu-Ouest","Takaroa","Taputapuatea","Tatakoto","Teva I Uta","Tubuai","Tumaraa","Tureia","Ua Huka","Ua Pou","Uturoa"]


def norm(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "")).lower() if c.isalnum())


def table(ws):
    rows = list(ws.iter_rows(values_only=True))
    return {str(r[0]).strip(): r for r in rows[1:] if r and r[0] is not None}


def findrow(rows, prefix):
    return next((r for k, r in rows.items() if k.startswith(prefix)), [])


def num(row, i):
    v = row[i] if len(row) > i else 0
    return v if isinstance(v, (int, float)) else 0


class FrenchPolynesiaCensus(Source):
    info = SourceInfo(
        id="fr_polynesia",
        title="French Polynesia geographic census workbooks",
        publisher="ISPF / INSEE",
        homepage="https://www.ispf.pf/fiche-geo/Polyn%C3%A9sie%20fran%C3%A7aise",
        license="Open data / official statistics",
        description="Commune-level population, education, activity, commuting, housing and household-equipment tables from the 2022 French Polynesia census geographic workbooks.",
        used_for=["French Polynesia commune-level demographic, housing and mobility lenses"],
    )

    def fetch(self, force=False):
        for name in COMMUNES:
            self.download(quote(BASE.format(name), safe=":/?"), norm(name) + ".xlsx", force=force, expect_binary=True)

    def process(self):
        out = {}
        for name in COMMUNES:
            wb = workbook_from_xlsx((self.raw_dir / (norm(name) + ".xlsx")).read_bytes())
            age = table(wb["POP.T0"]); housing = table(wb["LOG.T2"]); tenure = table(wb["LOG.T7"])
            education = table(wb["FOR.T2"]); commute = table(wb["ACT.T4"]); equipment = table(wb["LOG.T9"])
            agriculture = table(wb["EMP.G3"]); unemployment = table(wb["EMP.T4"]); activity = table(wb["EMP.T2"])
            out[norm(name)] = {
                "population": num(age.get("Ensemble", []), 7),
                "seniors60": num(age.get("60 à 74 ans", []), 7) + num(age.get("75 ans et plus", []), 7),
                "adults15": num(activity.get("Ensemble", []), 1),
                "labour_force": num(activity.get("Ensemble", []), 2),
                "employed": num(activity.get("Ensemble", []), 3),
                "higher_education": num(education.get("Diplôme de 1er cycle, BTS, IUT", []), 1) + num(education.get("Diplôme de 2ième et 3ième cycle sans d'autre précision", []), 1),
                "unemployment": num(unemployment.get("Taux de chômage", []), 4),
                "agriculture": num(agriculture.get("Agriculteurs exploitants", []), 4),
                "dwellings": num(housing.get("Ensemble", []), 7),
                "vacant": num(housing.get("Logement vacant", []), 7),
                "second_homes": num(housing.get("Résidence secondaire", []), 7) + num(housing.get("Logement occasionnel", []), 7),
                "main_homes": num(tenure.get("Ensemble", []), 8),
                "owner_homes": num(tenure.get("Propriétaire du logement", []), 8),
                "workers": num(commute.get("Ensemble", []), 1),
                "outside_commute": num(findrow(commute, "Travaillent dans une autre commune"), 1),
                "no_car": num(equipment.get("Pas de voiture", []), 1),
                "boat_access": num(equipment.get("1 bateau et plus", []), 1),
            }
        print(f"    communes: {len(out)}")
        return {
            "vintage": "Fiches géographiques ISPF, recensement de la population de Polynésie française 2022, legal deposit 2024-02-07",
            "year": 2022,
            "communes": out,
        }
