"""SISPEA drinking-water and wastewater service performance indicators."""

import io
from collections import defaultdict

import py7zr
import xlrd

from ..core.source import Source, SourceInfo

AEP_URL = "https://data.ofb.fr/catalogue/srv/api/records/7d6a3010-cf19-42c3-8a38-9823074185ce/attachments/SISPEA_extraction_2024_AEP.7z"
AC_URL = "https://data.ofb.fr/catalogue/srv/api/records/5feec4e9-03a6-409a-a522-d51346d5f4c9/attachments/SISPEA_extraction_2024_AC.7z"


def parse_dep(value):
    value = str(value).strip()
    if value in {"02A", "02B"}:
        return value[-2:]
    if value.isdigit():
        return value if value.startswith("97") else value[-2:].zfill(2)
    return value


def number(value):
    try:
        return float(value) if value not in {"", None} else None
    except (TypeError, ValueError):
        return None


def extract_7z(path, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    with py7zr.SevenZipFile(path) as archive:
        name = archive.getnames()[0]
        archive.extractall(out_dir)
    return out_dir / name


def service_rows(path, indicators, population_code):
    book = xlrd.open_workbook(str(path))
    sheet = book.sheet_by_name("Entités de gestion")
    headers = sheet.row_values(0)
    col = {h: i for i, h in enumerate(headers)}
    out = defaultdict(lambda: {"weights": defaultdict(float), "sums": defaultdict(float), "services": 0})
    for rix in range(1, sheet.nrows):
        row = sheet.row_values(rix)
        dep = parse_dep(row[0])
        if not dep:
            continue
        entity_pop = number(row[col["Pop de l'entité de gestion sans double compte"]]) or 0
        served_pop = number(row[col[population_code]]) or entity_pop
        out[dep]["services"] += 1
        for code in indicators:
            value = number(row[col[code]]) if code in col else None
            if value is not None and served_pop:
                out[dep]["weights"][code] += served_pop
                out[dep]["sums"][code] += value * served_pop
    result = {}
    for dep, row in out.items():
        result[dep] = {"services": row["services"]}
        for code in indicators:
            weight = row["weights"].get(code, 0)
            result[dep][code] = round(row["sums"][code] / weight, 4) if weight else None
            result[dep][code + "_population"] = round(weight, 1) if weight else 0
    return result


class FrenchWaterServices(Source):
    info = SourceInfo(
        id="fr_water_services",
        title="SISPEA drinking-water and wastewater service performance",
        publisher="Office français de la biodiversité / services.eaufrance.fr",
        homepage="https://www.services.eaufrance.fr/",
        license="Licence Ouverte 2.0",
        description="Annual 2024 SISPEA service-price and performance indicators for drinking-water and collective-wastewater services. Multi-commune service territories are aggregated by the department of the managing body's headquarters, so departmental values are service-weighted approximations rather than exact territorial averages.",
        used_for=["Water and wastewater service lenses"],
    )

    def fetch(self, force=False):
        self.download(AEP_URL, "sispea_2024_aep.7z", force=force, expect_binary=True)
        self.download(AC_URL, "sispea_2024_ac.7z", force=force, expect_binary=True)

    def process(self):
        aep_xls = extract_7z(self.raw_dir / "sispea_2024_aep.7z", self.raw_dir / "aep")
        ac_xls = extract_7z(self.raw_dir / "sispea_2024_ac.7z", self.raw_dir / "ac")
        drinking = service_rows(aep_xls, ["D102.0", "P101.1", "P102.1", "P104.3"], "D101.0")
        wastewater = service_rows(ac_xls, ["D204.0", "P201.1", "P254.3"], "D201.0")
        if len(drinking) < 95 or len(wastewater) < 95:
            raise ValueError("unexpected SISPEA departmental coverage")
        return {
            "vintage": "SISPEA service performance, 2024",
            "_files": ["sispea_2024_aep.7z", "sispea_2024_ac.7z"],
            "year": 2024,
            "drinking": drinking,
            "wastewater": wastewater,
        }
