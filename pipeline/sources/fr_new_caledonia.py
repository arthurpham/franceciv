"""INSEE/ISEE New Caledonia census commune tables."""

import unicodedata
import xlrd

from ..core.source import Source, SourceInfo

URL = "https://isee.nc/sites/default/files/2025-10/rp2019-pop-logement-menages-communes.xls"
FILE = "rp2019-pop-logement-menages-communes.xls"


def norm(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "")).lower() if c.isalnum())


ALIASES = {"boulouparis": "bouloupari", "iledespinsl": "liledespins", "montdorele": "lemontdore"}
STOP = {"provinceilesloyaute", "nordouest", "nordest", "provincenord", "grandnoumea", "sudrural", "provincesud", "nouvellecaledonie"}


def rows(book, sheet):
    sh = book.sheet_by_name(sheet)
    out = {}
    for i in range(sh.nrows):
        raw = sh.cell_value(i, 0)
        key = norm(raw)
        if key in STOP:
            break
        if not key or key in {"en2019"} or not isinstance(sh.cell_value(i, 1), float):
            continue
        out[ALIASES.get(key, key)] = sh.row_values(i)
    return out


class NewCaledoniaCensus(Source):
    info = SourceInfo(
        id="fr_new_caledonia",
        title="New Caledonia census commune tables",
        publisher="INSEE / ISEE-NC",
        homepage="https://isee.nc/recensement",
        license="Open data / official statistics",
        description="Population, activity, housing and household-equipment tables by commune from the 2019 New Caledonia census.",
        used_for=["New Caledonia commune-level demographic, housing and infrastructure lenses"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=True)

    def process(self):
        book = xlrd.open_workbook(str(self.raw_dir / FILE))
        age = rows(book, "P01")
        education = rows(book, "P17")
        activity = rows(book, "P23")
        sector = rows(book, "P27")
        housing = rows(book, "L1")
        tenure = rows(book, "R2")
        water = rows(book, "R7")
        equipment = rows(book, "M2")
        out = {}
        for key, p in age.items():
            e, a, sec = education.get(key), activity.get(key), sector.get(key)
            h, t, w, q = housing.get(key), tenure.get(key), water.get(key), equipment.get(key)
            out[key] = {
                "population": p[30], "seniors": sum(p[27:30]),
                "adults15": e[27] if e else None, "higher_education": (e[25] + e[26]) if e else None,
                "employed": a[13] if a else None, "unemployed": a[14] if a else None,
                "agriculture": sec[1] if sec else None, "sector_jobs": sec[6] if sec else None,
                "dwellings": h[5] if h else None, "second_homes": (h[2] + h[3]) if h else None, "vacant": h[4] if h else None,
                "main_homes": t[6] if t else None, "owner_homes": t[1] if t else None,
                "water_homes": w[4] if w else None, "no_running_water": w[3] if w else None,
                "households": q[9] if q else None, "internet_households": q[7] if q else None,
            }
        print(f"    communes: {len(out)}")
        return {
            "vintage": "Recensement de la population Nouvelle-Calédonie 2019, updated 2021-06-23",
            "_files": [FILE],
            "year": 2019,
            "communes": out,
        }
