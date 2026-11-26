"""Natura 2000 protected areas from API Carto Nature / INPN."""

import json

from ..core.source import Source, SourceInfo

BASE = "https://apicarto.ign.fr/api/nature"
ENDPOINTS = {"habitat": "natura-habitat", "birds": "natura-oiseaux"}
LIMIT = 1000


class FrenchNature(Source):
    info = SourceInfo(
        id="fr_nature",
        title="INPN Natura 2000 protected areas",
        publisher="IGN API Carto Nature / INPN",
        homepage="https://www.data.gouv.fr/dataservices/api-carto-module-nature",
        license="Licence Ouverte 2.0",
        description="GeoJSON geometries of Natura 2000 habitat-directive and birds-directive sites.",
        used_for=["Protected nature lens"],
    )

    def fetch(self, force=False):
        for key, endpoint in ENDPOINTS.items():
            start = 0
            page = 0
            while True:
                url = f"{BASE}/{endpoint}?_limit={LIMIT}&_start={start}"
                self.download(url, f"{key}_{page}.geojson", force=force)
                with open(self.raw_dir / f"{key}_{page}.geojson", encoding="utf-8") as f:
                    d = json.load(f)
                if start + d.get("numberReturned", 0) >= d.get("numberMatched", 0) or not d.get("numberReturned"):
                    break
                start += d["numberReturned"]
                page += 1

    def process(self):
        sites = []
        files = []
        for key in ENDPOINTS:
            page = 0
            while (self.raw_dir / f"{key}_{page}.geojson").exists():
                fn = f"{key}_{page}.geojson"
                files.append(fn)
                with open(self.raw_dir / fn, encoding="utf-8") as f:
                    d = json.load(f)
                for feat in d.get("features", []):
                    if feat.get("geometry"):
                        sites.append({"kind": key, "properties": feat.get("properties", {}), "geometry": feat["geometry"]})
                page += 1
        return {"vintage": "INPN Natura 2000 via API Carto Nature, current export", "_files": files, "sites": sites}
