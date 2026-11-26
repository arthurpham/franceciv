"""DREES localized potential accessibility (APL) to health professionals."""

from openpyxl import load_workbook

from ..core.source import Source, SourceInfo

BASE = "https://data.drees.solidarites-sante.gouv.fr/api/v2/catalog/datasets/530_l-accessibilite-potentielle-localisee-apl/attachments/"
PROFESSIONS = {
    "gp": ("indicateur_d_apl_aux_medecins_generalistes_xlsx", "apl_medecins_generalistes.xlsx", "consultations per resident per year"),
    "nurse": ("indicateur_d_apl_aux_infirmiers_xlsx", "apl_infirmiers.xlsx", "full-time equivalents per 100k residents"),
    "dentist": ("indicateur_d_apl_aux_chirurgiens_dentistes_xlsx", "apl_dentistes.xlsx", "full-time equivalents per 100k residents"),
    "midwife": ("indicateur_d_apl_aux_sages_femmes_xlsx", "apl_sages_femmes.xlsx", "full-time equivalents per 100k residents"),
}


class FrenchHealthcare(Source):
    info = SourceInfo(
        id="fr_healthcare",
        title="Localized potential accessibility to health professionals",
        publisher="DREES",
        homepage="https://www.data.gouv.fr/datasets/accessibilite-potentielle-localisee-apl-aux-professionnels-de-sante",
        license="Licence Ouverte 2.0 (Etalab)",
        description="Commune-level APL indicators for general practitioners, nurses, dentists and midwives. APL "
        "accounts for nearby supply and the age structure of demand; it is an accessibility indicator, not a count of practitioners.",
        used_for=["Healthcare-access lenses"],
    )

    def fetch(self, force=False):
        for attachment, filename, _ in PROFESSIONS.values():
            self.download(BASE + attachment, filename, force=force, expect_binary=True)

    def process(self):
        professions = {}
        used = []
        for pid, (_, filename, unit) in PROFESSIONS.items():
            wb = load_workbook(self.raw_dir / filename, read_only=True, data_only=True)
            sheet = "APL 2024" if "APL 2024" in wb.sheetnames else wb.sheetnames[-1]
            ws = wb[sheet]
            rows = {}
            for row in ws.iter_rows(min_row=11, values_only=True):
                code, value = row[0], row[2]
                if code is None or value is None:
                    continue
                try:
                    rows[str(code)] = round(float(value), 4)
                except (TypeError, ValueError):
                    continue
            professions[pid] = {"unit": unit, "year": int(sheet.split()[-1]), "values": rows}
            used.append(filename)
            wb.close()
        return {"vintage": "DREES APL 2024", "_files": used, "professions": professions}
