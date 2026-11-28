"""INSEE 2023 detailed census tables for Saint-Pierre-et-Miquelon, Saint-Barthélemy and Saint-Martin."""

import re
import zipfile

import openpyxl

from ..core.source import Source, SourceInfo

BASE = "https://www.insee.fr/fr/statistiques/fichier"
FILES = {
    "population": ("9006388", "TD_POPULATION_AGESEX_PRINC_COM_2023_xlsx.zip", "TD_POP1_com_2023.xlsx"),
    "activity": ("9003016", "TD_ACTIVITE_AGED_PRINC_COM_2023_xlsx.zip", "TD_ACT1_com_2023.xlsx"),
    "education": ("9006746", "TD_DIPLOMES_PRINC_COM_2023_xlsx.zip", "TD_FOR2_com_2023.xlsx"),
    "housing": ("9003029", "TD_LOGEMENT_CARACT_PRINC_COM_2023_xlsx.zip", "TD_LOG1_com_2023.xlsx"),
    "tenure": ("9003029", "TD_LOGEMENT_CARACT_PRINC_COM_2023_xlsx.zip", "TD_PRINC2_com_2023.xlsx"),
}


def num(v):
    return v if isinstance(v, (int, float)) else 0


def rows(zf, filename):
    with zf.open(filename) as f:
        ws = openpyxl.load_workbook(f, data_only=True)["COM"]
    data = list(ws.iter_rows(values_only=True))
    header = [str(x or "") for x in data[0]]
    return header, {str(row[0]): row for row in data[1:] if row and row[0]}


def sum_match(header, row, pred):
    return sum(num(v) for h, v in zip(header, row) if h and pred(h))


class NorthernCollectivitiesCensus(Source):
    info = SourceInfo(
        id="fr_northern_com",
        title="Northern overseas collectivities detailed census tables 2023",
        publisher="INSEE",
        homepage="https://www.insee.fr/fr/information/2409270",
        license="Licence Ouverte 2.0",
        description="Commune-level population, activity, education, housing and tenure tables for Saint-Pierre-et-Miquelon, Saint-Barthélemy and Saint-Martin.",
        used_for=["Northern overseas collectivity commune-level demographic, employment and housing lenses"],
    )

    def fetch(self, force=False):
        for pid, filename, _ in FILES.values():
            self.download(f"{BASE}/{pid}/{filename}", filename, force=force, expect_binary=True)

    def process(self):
        out = {}
        with zipfile.ZipFile(self.raw_dir / FILES["population"][1]) as z:
            ph, pop = rows(z, FILES["population"][2])
        with zipfile.ZipFile(self.raw_dir / FILES["activity"][1]) as z:
            ah, act = rows(z, FILES["activity"][2])
        with zipfile.ZipFile(self.raw_dir / FILES["education"][1]) as z:
            eh, edu = rows(z, FILES["education"][2])
        with zipfile.ZipFile(self.raw_dir / FILES["housing"][1]) as z:
            hh, housing = rows(z, FILES["housing"][2])
            th, tenure = rows(z, FILES["tenure"][2])
        for code, prow in pop.items():
            def age(h):
                m = re.search(r"\n(\d+) an", h)
                return int(m.group(1)) if m else None
            population = sum_match(ph, prow, lambda h: "\n" in h and age(h) is not None)
            children = sum_match(ph, prow, lambda h: age(h) is not None and age(h) <= 17)
            seniors = sum_match(ph, prow, lambda h: age(h) is not None and age(h) >= 65)
            arow, erow = act.get(code, []), edu.get(code, [])
            hrow, trow = housing.get(code, []), tenure.get(code, [])
            out[code] = {
                "population": population, "children": children, "seniors": seniors,
                "employed": sum_match(ah, arow, lambda h: h.endswith("Actif occupé")),
                "unemployed": sum_match(ah, arow, lambda h: h.endswith("Chômeur")),
                "adults15": sum_match(eh, erow, lambda h: "\n" in h),
                "higher_education": sum_match(eh, erow, lambda h: "Enseignement supérieur" in h),
                "dwellings": sum_match(hh, hrow, lambda h: "\n" in h),
                "vacant": sum_match(hh, hrow, lambda h: h.startswith("Logements vacants")),
                "second_homes": sum_match(hh, hrow, lambda h: h.startswith(("Résidences secondaires", "Logements occasionnels"))),
                "main_homes": sum_match(th, trow, lambda h: "\n" in h),
                "owner_homes": sum_match(th, trow, lambda h: "\nPropriétaire\n" in h),
                "social_homes": sum_match(th, trow, lambda h: "parc social" in h),
            }
        print(f"    communes: {len(out)}")
        return {
            "vintage": "INSEE recensement 2023, detailed commune tables for Saint-Pierre-et-Miquelon, Saint-Barthélemy and Saint-Martin, geography 2026-01-01",
            "_files": sorted({x[1] for x in FILES.values()}),
            "year": 2023,
            "communes": out,
        }
