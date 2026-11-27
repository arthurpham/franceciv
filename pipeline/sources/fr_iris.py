"""INSEE/IGN IRIS statistical geography and 2022 census population."""

import csv
import io
import json
import math
import zipfile

from shapely.geometry import shape

from ..core.insets import transform_point
from ..core.source import Source, SourceInfo

POP_URL = "https://www.insee.fr/fr/statistiques/fichier/8647014/base-ic-evol-struct-pop-2022_csv.zip"
WFS = "https://data.geopf.fr/wfs/ows"
TYPENAME = "STATISTICALUNITS.IRIS:contours_iris"
COUNT = 5000


def page_url(start):
    return (
        f"{WFS}?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES={TYPENAME.replace(':', '%3A')}"
        f"&COUNT={COUNT}&STARTINDEX={start}&OUTPUTFORMAT=application%2Fjson"
    )


def dep_from_code(code):
    return code[:3] if str(code).startswith("97") else str(code)[:2]


def num(value):
    if value in (None, ""):
        return None
    return float(value)


class FrenchIris(Source):
    info = SourceInfo(
        id="fr_iris",
        title="Contours IRIS and 2022 census population",
        publisher="INSEE / IGN Géoplateforme",
        homepage="https://www.insee.fr/fr/statistiques/8647014",
        license="Licence Ouverte 2.0",
        description="INSEE 2022 infra-communal census population by IRIS, joined to the IGN/INSEE Contours IRIS WFS. "
        "Communes not divided into IRIS are represented as whole-commune pseudo-IRIS so the statistical partition covers France; "
        "the population extract excludes Mayotte. Polygon centroids and areas are simplified analytical representations.",
        used_for=["Neighborhood-scale population density and demographic lenses", "IRIS search and neighborhood cards"],
    )

    def fetch(self, force=False):
        self.download(POP_URL, "base-ic-evol-struct-pop-2022_csv.zip", force=force, expect_binary=True)
        first = self.download(page_url(0), "iris_page_0.json", force=force)
        with open(first, encoding="utf-8") as f:
            matched = json.load(f).get("numberMatched", 0)
        for start in range(COUNT, int(matched), COUNT):
            self.download(page_url(start), f"iris_page_{start}.json", force=force)

    def process(self):
        stats = {}
        with zipfile.ZipFile(self.raw_dir / "base-ic-evol-struct-pop-2022_csv.zip") as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".csv") and not n.startswith("meta_"))
            with z.open(name) as f:
                text = io.TextIOWrapper(f, encoding="utf-8-sig")
                for r in csv.DictReader(text, delimiter=";"):
                    pop = num(r.get("P22_POP"))
                    if pop is None:
                        continue
                    stats[r["IRIS"]] = {
                        "population": pop,
                        "youth_share": (num(r.get("P22_POP0019")) or 0) / pop if pop else None,
                        "senior_share": (num(r.get("P22_POP65P")) or 0) / pop if pop else None,
                        "immigration_share": (num(r.get("P22_POP_IMM")) or 0) / pop if pop else None,
                        "foreign_share": (num(r.get("P22_POP_ETR")) or 0) / pop if pop else None,
                        "working_age_share": (num(r.get("P22_POP2064")) or 0) / pop if pop else None,
                        "com": r.get("COM"),
                        "stat_type": r.get("TYP_IRIS"),
                    }

        pages = sorted(self.raw_dir.glob("iris_page_*.json"), key=lambda p: int(p.stem.rsplit("_", 1)[1]))
        rows = []
        missing_stats = 0
        for path in pages:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for feat in data.get("features", []):
                prop = feat.get("properties", {})
                geom_data = feat.get("geometry")
                code = prop.get("code_iris")
                if not code or not geom_data:
                    continue
                geom = shape(geom_data)
                if geom.is_empty:
                    continue
                c = geom.centroid
                dep = dep_from_code(prop.get("code_insee") or code.zfill(9)[:5])
                lon, lat = transform_point(dep, c.x, c.y)
                km_lat = 111.32
                km_lon = 111.32 * math.cos(math.radians(c.y))
                area_km2 = geom.area * km_lat * km_lon
                st = stats.get(code)
                if st is None:
                    missing_stats += 1
                    st = {}
                population = st.get("population")
                rows.append({
                    "code": code,
                    "iris_part": prop.get("iris"),
                    "name": prop.get("nom_iris") or prop.get("nom_commune") or code,
                    "commune": prop.get("nom_commune") or "",
                    "commune_code": prop.get("code_insee"),
                    "department": dep,
                    "type": prop.get("type_iris"),
                    "lon": round(lon, 6),
                    "lat": round(lat, 6),
                    "area_km2": round(area_km2, 5),
                    "true_iris": prop.get("iris") != "0000",
                    **st,
                })
        if len(rows) < 45_000 or len(stats) < 45_000:
            raise ValueError(f"unexpected IRIS totals: {len(rows)} geometries, {len(stats)} statistical rows")
        print(f"    {len(rows)} IRIS/pseudo-IRIS geometries; {len(stats)} statistical rows; {missing_stats} geometries without 2022 statistics")
        return {
            "vintage": "INSEE census population 2022; Contours IRIS current export",
            "_files": ["base-ic-evol-struct-pop-2022_csv.zip", *[p.name for p in pages]],
            "rows": rows,
            "statistical_rows": len(stats),
            "geometries_without_stats": missing_stats,
        }
