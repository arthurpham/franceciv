"""Agreste 2020 agricultural-census commune indicators mirrored by ANCT."""

from openpyxl import load_workbook

from ..core.source import Source, SourceInfo

BASE = "https://www.observatoire-des-territoires.gouv.fr/outils/cartographie-interactive/api/v1/functions/GC_API_download.php"
GEOGRAPHY = "com2026"
INDICATORS = {
    "farms": ("exp2020", "exp2020.xlsx"),
    "agricultural_area": ("sau2020", "sau2020.xlsx"),
}


def url(indicator):
    return f"{BASE}?type=stat&nivgeo={GEOGRAPHY}&dataset=agri&indic={indicator}"


class FrenchAgreste(Source):
    info = SourceInfo(
        id="fr_agreste",
        title="Agreste agricultural census 2020, commune indicators",
        publisher="Agreste / Ministère de l'Agriculture, mirrored by the Observatoire des territoires (ANCT)",
        homepage="https://www.data.gouv.fr/datasets/agreste-donnees-communales-du-recensement-agricole-cartographie-2020-et-tableaux-interactifs-historiques",
        license="Licence Ouverte / Open Licence",
        description="Commune-level 2020 agricultural-census indicators downloaded through the ANCT/Observatoire des territoires "
        f"Géoclip export API using the current {GEOGRAPHY} communal geography. The pipeline uses the number of farms and "
        "utilised agricultural area. Blank cells mean no farm or statistical suppression and are not treated as measured zeros.",
        used_for=["Farm density and average farm-size lenses"],
    )

    def fetch(self, force=False):
        for key, (indicator, filename) in INDICATORS.items():
            self.download(url(indicator), filename, force=force, expect_binary=True)

    def process(self):
        files = []
        datasets = {}
        for key, (indicator, filename) in INDICATORS.items():
            files.append(filename)
            wb = load_workbook(self.raw_dir / filename, read_only=True, data_only=True)
            ws = wb["Data"]
            rows = {}
            for row in ws.iter_rows(min_row=6, max_col=4, values_only=True):
                if len(row) < 4 or row[0] is None:
                    continue
                code = str(row[0]).strip().zfill(5)
                year = row[2]
                value = row[3]
                if value is not None and int(year or 0) != 2020:
                    continue
                rows[code] = {"name": row[1], "value": round(float(value), 4) if value is not None else None}
            wb.close()
            datasets[key] = rows
        common = sorted(set(datasets["farms"]) & set(datasets["agricultural_area"]))
        merged = {
            code: {
                "name": datasets["farms"][code]["name"],
                "farms": datasets["farms"][code]["value"],
                "agricultural_area_ha": datasets["agricultural_area"][code]["value"],
            }
            for code in common
        }
        farm_total = sum(r["farms"] or 0 for r in merged.values())
        sau_total = sum(r["agricultural_area_ha"] or 0 for r in merged.values())
        suppressed = sum(r["farms"] is None for r in merged.values())
        print(f"    {len(merged)} communes, {round(farm_total)} farms, {round(sau_total)} ha UAA, {suppressed} blank/suppressed")
        if not 35000 > len(merged) > 34000 or not 380_000 < farm_total < 450_000 or not 24_000_000 < sau_total < 30_000_000:
            raise ValueError("unexpected Agreste commune totals")
        return {
            "vintage": "Agreste agricultural census 2020, ANCT communal geography 2026",
            "_files": files,
            "geography": GEOGRAPHY,
            "year": 2020,
            "suppressed_communes": suppressed,
            "rows": merged,
        }
