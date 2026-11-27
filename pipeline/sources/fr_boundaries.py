"""French administrative boundaries and commune reference points.

Uses Etalab's current contour extracts (derived from the official geographic code and
administrative boundaries) plus geo.api.gouv.fr for commune population, area and centre.
"""

from __future__ import annotations

import gzip
import json

from ..core.geo import geojson_rings
from ..core.insets import REGION_TO_DEP, inset_for_dep, transform_point, transform_rings
from ..core.source import Source, SourceInfo

BASE = "https://etalab-datasets.geo.data.gouv.fr/contours-administratifs/latest/geojson"
GEO_API = (
    "https://geo.api.gouv.fr/communes?fields=nom,code,codeDepartement,codeRegion,population,centre,surface"
    "&format=json&geometry=centre"
)
EPCI_API = "https://geo.api.gouv.fr/epcis?fields=nom,code,population&format=json&geometry=centre"

# Metropolitan France, Corsica and the five overseas department-region collectivities.
METRO_REGIONS = {"11", "24", "27", "28", "32", "44", "52", "53", "75", "76", "84", "93", "94", "01", "02", "03", "04", "06", "975", "977", "978", "986", "987", "988"}
REGION_ABBR = {
    "11": "IDF", "24": "CVL", "27": "BFC", "28": "NOR", "32": "HDF", "44": "GES", "52": "PDL",
    "53": "BRE", "75": "NAQ", "76": "OCC", "84": "ARA", "93": "PAC", "94": "COR",
    "01": "GUA", "02": "MTQ", "03": "GUY", "04": "REU", "06": "MAY",
    "975": "SPM", "977": "STB", "978": "SMT", "986": "WAF", "987": "PYF", "988": "NCL",
}
FILES = {
    "regions": "regions-100m.geojson.gz",
    "departments": "departements-100m.geojson.gz",
    "communes": "communes-1000m.geojson.gz",
}


def read_gz_geojson(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)["features"]


class FrenchBoundaries(Source):
    info = SourceInfo(
        id="fr_boundaries",
        title="Contours administratifs et communes de France",
        publisher="Etalab / data.gouv.fr, IGN et Insee",
        homepage="https://www.data.gouv.fr/pages/donnees-geographiques",
        license="Licence Ouverte 2.0",
        description="Current region, department and commune boundaries, with commune population, land area and centre "
        "from geo.api.gouv.fr. Metropolitan France and Corsica use their real positions; overseas collectivities are affine-placed in inset slots west of the mainland.",
        used_for=["Map land and borders", "Department lookup", "Commune membership and city positions"],
    )

    def fetch(self, force=False):
        for name in FILES.values():
            self.download(f"{BASE}/{name}", name, force=force, expect_binary=True)
        self.download(GEO_API, "communes-reference.json", force=force)
        self.download(EPCI_API, "epcis-reference.json", force=force)

    def process(self):
        regions = []
        for f in read_gz_geojson(self.raw_dir / FILES["regions"]):
            p = f["properties"]
            if p["code"] not in METRO_REGIONS:
                continue
            dep = REGION_TO_DEP.get(p["code"])
            regions.append({
                "fips": p["code"],
                "abbr": REGION_ABBR[p["code"]],
                "name": p["nom"],
                "inset": dep,
                "rings": transform_rings(dep, geojson_rings(f["geometry"])) if dep else geojson_rings(f["geometry"]),
            })

        departments = []
        for f in read_gz_geojson(self.raw_dir / FILES["departments"]):
            p = f["properties"]
            if p.get("region") not in METRO_REGIONS:
                continue
            departments.append({
                "geoid": p["code"],
                "name": p["nom"],
                "state_fips": p["region"],
                "inset": inset_for_dep(p["code"]),
                "rings": transform_rings(p["code"], geojson_rings(f["geometry"])),
            })

        shapes = {}
        for f in read_gz_geojson(self.raw_dir / FILES["communes"]):
            p = f["properties"]
            if p.get("region") in METRO_REGIONS:
                dep = p.get("departement")
                shapes[p["code"]] = {
                    "name": p["nom"],
                    "department": dep,
                    "region": p.get("region"),
                    "epci": p.get("epci"),
                    "inset": inset_for_dep(dep),
                    "rings": transform_rings(dep, geojson_rings(f["geometry"])),
                }

        with open(self.raw_dir / "communes-reference.json", encoding="utf-8") as f:
            reference = json.load(f)
        communes = []
        missing_shape = 0
        for r in reference:
            if r.get("codeRegion") not in METRO_REGIONS:
                continue
            shape = shapes.get(r["code"])
            if shape is None:
                missing_shape += 1
                continue
            lonlat = (r.get("centre") or {}).get("coordinates") or [None, None]
            lon, lat = transform_point(shape.get("department"), lonlat[0], lonlat[1])
            communes.append({
                **shape,
                "code": r["code"],
                "population": r.get("population"),
                "surface_ha": r.get("surface"),
                "lon": lon,
                "lat": lat,
            })
        if missing_shape:
            print(f"    ! {missing_shape} geo.api communes without a matching contour")

        with open(self.raw_dir / "epcis-reference.json", encoding="utf-8") as f:
            epcis = {r["code"]: r for r in json.load(f)}
        return {
            "vintage": "contours administratifs latest; géographie 2026",
            "_files": [*FILES.values(), "communes-reference.json", "epcis-reference.json"],
            "epcis": epcis,
            "states": sorted(regions, key=lambda s: s["name"]),
            "counties": sorted(departments, key=lambda c: c["geoid"]),
            "communes": sorted(communes, key=lambda c: c["code"]),
        }
