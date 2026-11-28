"""INSEE bassins de vie 2022 and zones d'emploi 2020 communal composition."""

import io
import re
import zipfile

import openpyxl
import openpyxl.reader.excel as excel_reader

from ..core.source import Source, SourceInfo

BASE = "https://www.insee.fr/fr/statistiques/fichier"
BV_URL = f"{BASE}/6676988/BV2022_au_01-01-2025.zip"
ZE_URL = f"{BASE}/4652957/ZE2020_au_01-01-2025.zip"
excel_reader.find_images = lambda archive, path: ([], [])


def workbook_from_xlsx(data):
    # INSEE workbooks contain invalid stylesheet colours and broken drawing references.
    # Values are simple strings/numbers, so strip style references before parsing.
    src = io.BytesIO(data)
    out = io.BytesIO()
    with zipfile.ZipFile(src) as zi, zipfile.ZipFile(out, "w") as zo:
        for item in zi.infolist():
            if item.filename == "xl/styles.xml":
                continue
            payload = zi.read(item.filename)
            if item.filename.startswith("xl/worksheets/"):
                payload = re.sub(rb' s="\d+"', b"", payload)
                payload = re.sub(rb' style="\d+"', b"", payload)
            zo.writestr(item, payload)
    out.seek(0)
    return openpyxl.load_workbook(out, data_only=True)


def rows(ws):
    data = list(ws.iter_rows(values_only=True))
    header = [str(v) for v in data[5]]
    for row in data[6:]:
        yield dict(zip(header, row))


class FrenchFunctionalGeographies(Source):
    info = SourceInfo(
        id="fr_functional_geographies",
        title="Bassins de vie 2022 and zones d'emploi 2020, 2025 communal composition",
        publisher="INSEE",
        homepage="https://www.insee.fr/fr/information/6676988",
        license="Licence Ouverte 2.0",
        description="Official communal composition and labels for bassins de vie 2022 and zones d'emploi 2020 at 1 January 2025. Bassins de vie are everyday-service catchments; zones d'emploi are labour-market areas.",
        used_for=["Bassin-de-vie and zone-d'emploi search/cards", "Commune-to-functional-geography attribution"],
    )

    def fetch(self, force=False):
        self.download(BV_URL, "bv.zip", force=force, expect_binary=True)
        self.download(ZE_URL, "ze.zip", force=force, expect_binary=True)

    def process(self):
        out = {"bassins": {}, "zones": {}, "communes": {}}
        for filename, code_key, label_key, target in [
            ("bv.zip", "BV2022", "LIBBV2022", "bassins"),
            ("ze.zip", "ZE2020", "LIBZE2020", "zones"),
        ]:
            with zipfile.ZipFile(self.raw_dir / filename) as z:
                wb = workbook_from_xlsx(z.read(z.namelist()[0]))
            list_sheet = wb.worksheets[0]
            comp_sheet = wb.worksheets[1]
            for row in rows(list_sheet):
                code = str(row.get(code_key) or "")
                if code:
                    extra = {"type": row.get("TYPE_BV2022")} if target == "bassins" else {}
                    out[target][code] = {"name": row.get(label_key), "commune_count_source": row.get("NB_COM"), **extra}
            for row in rows(comp_sheet):
                commune = str(row.get("CODGEO") or "")
                code = str(row.get(code_key) or "")
                if commune and code:
                    out["communes"].setdefault(commune, {})[target[:-1] if target == "bassins" else "zone"] = code
        return {
            "vintage": "INSEE bassins de vie 2022 and zones d'emploi 2020, communal composition at 2025-01-01",
            "_files": ["bv.zip", "ze.zip"],
            **out,
        }
