"""INERIS/Ecolab annual background air-pollution concentrations by commune."""

import csv

from ..core.source import Source, SourceInfo

COMMUNE_URL = "https://static.data.gouv.fr/resources/concentration-de-polluants-dans-lair/20261110-093738/concentration-de-polluants-dans-l-air-commune.csv"
FIELDS_URL = "https://static.data.gouv.fr/resources/concentration-de-polluants-dans-lair/20261110-093805/description-des-champs.csv"
POLLUTANTS = {"NO2": "no2", "PM10": "pm10", "PM2.5": "pm25"}


class FrenchAirQuality(Source):
    info = SourceInfo(
        id="fr_air_quality",
        title="Annual background air-pollution concentrations",
        publisher="INERIS / Ecolab / ecologie.data.gouv.fr",
        homepage="https://www.data.gouv.fr/datasets/concentration-de-polluants-dans-lair",
        license="Licence Ouverte / Open Licence",
        description="Commune-level annual mean background concentrations combining air-quality measurements with CHIMERE model simulations. Values characterize background pollution, not localized peaks near roads or industrial sites; the upstream indicator is marked as under review and covers metropolitan France including Corsica, not overseas territories.",
        used_for=["Nitrogen-dioxide and particulate air-quality lenses"],
    )

    def fetch(self, force=False):
        self.download(COMMUNE_URL, "commune_concentrations.csv", force=force)
        self.download(FIELDS_URL, "field_descriptions.csv", force=force)

    def process(self):
        latest = {}
        latest_date = ""
        dates = set()
        rows = 0
        with open(self.raw_dir / "commune_concentrations.csv", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                pollutant = POLLUTANTS.get(row.get("polluant"))
                code = row.get("geocode_commune")
                if not pollutant or not code:
                    continue
                date = row.get("date_mesure") or ""
                dates.add(date)
                rows += 1
                try:
                    value = float(row.get("valeur") or "")
                except ValueError:
                    continue
                key = (code, pollutant)
                if key not in latest or date >= latest[key][0]:
                    latest[key] = (date, value)
        latest_date = max(item[0] for item in latest.values())
        communes = {}
        for (code, pollutant), (date, value) in latest.items():
            if date == latest_date:
                communes.setdefault(code, {})[pollutant] = round(value, 3)
        if len(communes) < 30_000 or len(dates) < 10:
            raise ValueError(f"unexpected air-quality coverage: {len(communes)} communes, {len(dates)} years")
        return {
            "vintage": f"INERIS annual background air concentrations, {latest_date[:4]}",
            "_files": ["commune_concentrations.csv", "field_descriptions.csv"],
            "year": int(latest_date[:4]),
            "years": sorted({x[:4] for x in dates if x}),
            "rows": rows,
            "communes": communes,
        }
