"""Météo-France SIM2 monthly climate reanalysis over metropolitan France."""

from __future__ import annotations

import csv
import gzip
from collections import defaultdict

from rasterio.warp import transform

from ..core.source import Source, SourceInfo

YEARS = range(1961, 2026)
URL = "https://meteofrance.s3.sbg.io.cloud.ovh.net/data/REF_CC/SIM_MENS/MENS_SIM2_{year}.csv.gz"
FILE = "MENS_SIM2_{year}.csv.gz"


def filename(year):
    return FILE.format(year=year)


class FrenchClimate(Source):
    info = SourceInfo(
        id="fr_climate",
        title="Météo-France SIM2 monthly climate reanalysis",
        publisher="Météo-France",
        homepage="https://www.data.gouv.fr/datasets/donnees-changement-climatique-sim-mensuelle",
        license="Licence Ouverte 2.0 (Etalab)",
        description="Monthly Safran-Isba reanalysis on an approximately 8 km grid since 1961. The pipeline compares "
        "1961–1990 with 1996–2025 and uses 1991–2020 climate normals for temperature and precipitation.",
        used_for=["Temperature lens", "Warming lens", "Rainfall lens", "Rainfall-change data"],
    )

    def fetch(self, force=False):
        for year in YEARS:
            self.download(URL.format(year=year), filename(year), force=force, expect_binary=True)

    def process(self):
        # Per Lambert-grid point: sums/counts for temperature and annual precipitation in the three periods.
        # indexes: baseline/normal/recent T, baseline/normal/recent rain, baseline/normal/recent water deficit
        acc = defaultdict(lambda: [[0.0, 0] for _ in range(9)])
        used = []
        for year in YEARS:
            name = filename(year)
            path = self.raw_dir / name
            annual = defaultdict(lambda: [0.0, 0.0, 0, 0.0])
            with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f, delimiter=";"):
                    try:
                        key = (int(row["LAMBX"]), int(row["LAMBY"]))
                        temp = float(row["T"])
                        rain = float(row["PRETOTM"])
                        etp = float(row["ETP"])
                    except (KeyError, ValueError):
                        continue
                    a = annual[key]
                    a[0] += temp
                    a[1] += rain
                    a[2] += 1
                    a[3] += etp
            for key, (tsum, rsum, months, esum) in annual.items():
                if months != 12:
                    continue
                tavg, rain = tsum / months, rsum
                deficit = esum - rain
                a = acc[key]
                if 1961 <= year <= 1990:
                    a[0][0] += tavg; a[0][1] += 1
                    a[3][0] += rain; a[3][1] += 1
                    a[6][0] += deficit; a[6][1] += 1
                if 1991 <= year <= 2020:
                    a[1][0] += tavg; a[1][1] += 1
                    a[4][0] += rain; a[4][1] += 1
                    a[7][0] += deficit; a[7][1] += 1
                if 1996 <= year <= 2025:
                    a[2][0] += tavg; a[2][1] += 1
                    a[5][0] += rain; a[5][1] += 1
                    a[8][0] += deficit; a[8][1] += 1
            used.append(name)
            print(f"    {year}: {len(annual)} grid points")

        keys = sorted(acc)
        if not keys:
            raise ValueError("no SIM2 rows parsed")
        xs = [x * 100 for x, _ in keys]
        ys = [y * 100 for _, y in keys]
        lons, lats = transform("EPSG:27572", "EPSG:4326", xs, ys)
        lon_out, lat_out, temperature, warming, rainfall, rain_change, water_deficit = [], [], [], [], [], [], []
        for key, lon, lat in zip(keys, lons, lats):
            # Keep the French meteorological grid and a small border margin; this drops sea/foreign fallback points.
            if not (-5.8 <= lon <= 10.3 and 41.0 <= lat <= 51.5):
                continue
            a = acc[key]
            if min(a[i][1] for i in range(9)) < 30:
                continue
            base_t = a[0][0] / a[0][1]
            norm_t = a[1][0] / a[1][1]
            recent_t = a[2][0] / a[2][1]
            base_r = a[3][0] / a[3][1]
            norm_r = a[4][0] / a[4][1]
            recent_r = a[5][0] / a[5][1]
            norm_deficit = a[7][0] / a[7][1]
            lon_out.append(round(lon, 5))
            lat_out.append(round(lat, 5))
            temperature.append(round(norm_t, 2))
            warming.append(round(recent_t - base_t, 2))
            rainfall.append(round(norm_r, 1))
            rain_change.append(round(recent_r / base_r - 1, 4) if base_r else None)
            water_deficit.append(round(norm_deficit, 1))
        return {
            "vintage": "Météo-France SIM2 monthly reanalysis, 1961–2025",
            "_files": used,
            "periods": {"baseline": [1961, 1990], "normal": [1991, 2020], "recent": [1996, 2025]},
            "lon": lon_out,
            "lat": lat_out,
            "temperature": temperature,
            "warming": warming,
            "rainfall": rainfall,
            "rain_change": rain_change,
            "water_deficit": water_deficit,
        }
