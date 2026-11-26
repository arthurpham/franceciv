"""INSEE monthly hotel occupancy by department."""

import csv
import io
import zipfile
from collections import defaultdict

from ..core.source import Source, SourceInfo

URL = "https://api.insee.fr/melodi/file/DS_TOUR_FREQ/DS_TOUR_FREQ_CSV_FR"
YEAR = "2024"


class FrenchTourism(Source):
    info = SourceInfo(
        id="fr_tourism",
        title="Frequentation of tourist accommodation",
        publisher="INSEE, Melodi",
        homepage="https://www.data.gouv.fr/datasets/frequentation-des-hebergements-touristiques",
        license="Licence Ouverte 2.0",
        description="Monthly hotel nights spent by department from the INSEE Melodi tourist-accommodation occupancy dataset.",
        used_for=["Hotel tourism intensity lens"],
    )

    def fetch(self, force=False):
        self.download(URL, "tour_freq_csv_fr.zip", force=force, expect_binary=True)

    def process(self):
        nights = defaultdict(float)
        months = defaultdict(set)
        with zipfile.ZipFile(self.raw_dir / "tour_freq_csv_fr.zip") as z:
            with z.open("DS_TOUR_FREQ_data.csv") as f:
                rows = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"), delimiter=";")
                for r in rows:
                    if not r["TIME_PERIOD"].startswith(YEAR + "-") or r["FREQ"] != "M" or r["GEO_OBJECT"] != "DEP":
                        continue
                    if r["TOUR_MEASURE"] != "NIGHT_SPENT" or r["ACTIVITY"] != "I551":
                        continue
                    if not (r["TOUR_RESID"] == "_T" and r["HOTEL_STA"] == "_T" and r["UNIT_LOC_RANKING"] == "_T"):
                        continue
                    if not (r["EQUIP"] == r["DEG_URBA"] == r["COASTAL_AREA"] == r["COASTAL_FACADE"] == r["MOUNTAIN_AREA"] == r["MOUNTAIN_MASSIF"] == "_Z"):
                        continue
                    if not r["OBS_VALUE"]:
                        continue
                    # UNIT_MULT=3: observations are thousands of nights.
                    nights[r["GEO"]] += float(r["OBS_VALUE"]) * (10 ** int(r.get("UNIT_MULT") or 0))
                    months[r["GEO"]].add(r["TIME_PERIOD"])
        return {
            "vintage": f"INSEE tourist accommodation occupancy, {YEAR}",
            "_files": ["tour_freq_csv_fr.zip"],
            "departments": [
                {"code": dep, "hotel_nights": round(v), "months": len(months[dep])}
                for dep, v in sorted(nights.items())
            ],
        }
