"""INSEE Mayotte 2017 detailed census commune tables."""

import zipfile

import xlrd

from ..core.source import Source, SourceInfo

BASE = "https://www.insee.fr/fr/statistiques/fichier"
FILES = {
    "housing": ("4199326", "rp-mayotte-2017-communes-log.xls"),
    "main_homes": ("4199326", "rp-mayotte-2017-communes-princ.xls"),
    "population": ("4199233", "td_Mayotte_Population_2017.zip"),
    "activity": ("4199262", "td-mayotte-pop-active-2017.zip"),
    "education": ("4199391", "td-mayotte-formation-2017.zip"),
}


def num(v):
    return v if isinstance(v, (int, float)) else 0


def simple_rows(path, sheet):
    rows = xlrd.open_workbook(str(path)).sheet_by_name(sheet)
    out = {}
    for i in range(5, rows.nrows):
        row = rows.row_values(i)
        if isinstance(row[0], float) and 97600 <= row[0] < 97700:
            out[str(int(row[0]))] = row
    return out


def detailed_rows(zf, filename):
    with zf.open(filename) as f:
        rows = xlrd.open_workbook(file_contents=f.read()).sheet_by_name("COM")
    header = rows.row_values(10)
    out = {}
    for i in range(11, rows.nrows):
        row = rows.row_values(i)
        try:
            code = str(int(float(row[0])))
        except (TypeError, ValueError):
            continue
        if code.startswith("976"):
            out[code] = dict(zip(header, row))
    return out


def sum_suffix(row, suffix):
    return sum(num(v) for k, v in row.items() if str(k).endswith(suffix))


def sum_diploma(row, codes):
    total = 0
    for key, value in row.items():
        parts = str(key).split("_")
        if len(parts) >= 4 and parts[1] == "DIPL" and parts[2].replace("MAY", "") in codes:
            total += num(value)
    return total


class MayotteCensus(Source):
    info = SourceInfo(
        id="fr_mayotte",
        title="Mayotte detailed census commune tables 2017",
        publisher="INSEE",
        homepage="https://www.insee.fr/fr/information/2411261",
        license="Licence Ouverte 2.0",
        description="Commune-level population, activity, education, housing and household-equipment tables from the 2017 Mayotte census.",
        used_for=["Mayotte commune-level demographic, housing and infrastructure lenses"],
    )

    def fetch(self, force=False):
        for key, (pid, filename) in FILES.items():
            self.download(f"{BASE}/{pid}/{filename}", filename, force=force, expect_binary=True)

    def process(self):
        log = {s: simple_rows(self.raw_dir / FILES["housing"][1], s) for s in ["LOG1", "LOG2"]}
        princ = {s: simple_rows(self.raw_dir / FILES["main_homes"][1], s) for s in ["PRINC1", "PRINC2", "PRINC6", "PRINC9", "PRINC10", "PRINC20"]}
        with zipfile.ZipFile(self.raw_dir / FILES["population"][1]) as z:
            age = detailed_rows(z, "BTX_TD_POP1A_2017.xls")
        with zipfile.ZipFile(self.raw_dir / FILES["activity"][1]) as z:
            activity = detailed_rows(z, "BTX_TD_ACT1_2017.xls")
        with zipfile.ZipFile(self.raw_dir / FILES["education"][1]) as z:
            education = detailed_rows(z, "BTX_TD_FOR2_2017.xls")
        out = {}
        for code, a in age.items():
            act, edu = activity.get(code, {}), education.get(code, {})
            population = sum(num(v) for k, v in a.items() if str(k).startswith("SEXE"))
            seniors = sum(num(v) for k, v in a.items() if str(k).endswith(("AGEPYR1065", "AGEPYR1080")))
            children = sum(num(v) for k, v in a.items() if any(str(k).endswith(f"AGEPYR10{x}") for x in ["00", "03", "06", "11"]))
            employed = sum_suffix(act, "TACTR_211")
            unemployed = sum_suffix(act, "TACTR_212")
            adult_rows = [num(v) for k, v in edu.items() if str(k).startswith("AGEQ65")]
            adults15 = sum(adult_rows)
            higher = sum(num(v) for k, v in edu.items() if any(f"DIPL_MAY{c}_" in str(k) for c in ["16", "17", "18", "19"]))
            l1, l2 = log["LOG1"].get(code), log["LOG2"].get(code)
            p1, p2, p6, p9, p10, p20 = (princ[s].get(code) for s in ["PRINC1", "PRINC2", "PRINC6", "PRINC9", "PRINC10", "PRINC20"])
            out[code] = {
                "population": population, "seniors": seniors, "children": children,
                "employed": employed, "unemployed": unemployed,
                "adults15": adults15, "higher_education": higher,
                "dwellings": num(l1[10]) if l1 else 0, "vacant": num(l1[8]) if l1 else 0, "second_homes": num(l1[4]) + num(l1[6]) if l1 else 0,
                "fragile_homes": (num(l2[2]) + num(l2[4])) if l2 else 0,
                "main_homes": num(p1[10]) if p1 else 0, "owner_homes": (num(p1[2]) + num(p1[4])) if p1 else 0,
                "earth_floor": num(p2[2]) if p2 else 0, "no_car": num(p6[2]) if p6 else 0,
                "no_indoor_wc": num(p9[4]) if p9 else 0, "no_electricity": num(p10[6]) if p10 else 0,
                "internet": num(p20[2]) if p20 else 0,
            }
        print(f"    communes: {len(out)}")
        return {
            "vintage": "INSEE recensement de Mayotte 2017, detailed commune tables published 2019-08-05",
            "_files": [x[1] for x in FILES.values()],
            "year": 2017,
            "communes": out,
        }
