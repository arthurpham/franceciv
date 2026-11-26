"""SNCF passenger-station traffic and reference coordinates."""

import json

from ..core.source import Source, SourceInfo

BASE = "https://data.sncf.com/api/explore/v2.1/catalog/datasets/{ds}/exports/json"


class FrenchRailStations(Source):
    info = SourceInfo(
        id="fr_rail_stations",
        title="SNCF passenger-station traffic",
        publisher="SNCF Gares & Connexions",
        homepage="https://www.data.gouv.fr/datasets/frequentation-en-gares",
        license="SNCF open data terms",
        description="Annual passenger traffic by station and the SNCF passenger-station coordinate reference. The "
        "2025 series uses a revised source and methodology and is not directly comparable with 2015–2024.",
        used_for=["Railway station markers"],
    )

    def fetch(self, force=False):
        self.download(BASE.format(ds="frequentation-gares"), "frequentation-gares.json", force=force)
        self.download(BASE.format(ds="gares-de-voyageurs"), "gares-de-voyageurs.json", force=force)

    def process(self):
        freq = json.loads((self.raw_dir / "frequentation-gares.json").read_text())
        refs = json.loads((self.raw_dir / "gares-de-voyageurs.json").read_text())
        by_uic = {}
        for ref in refs:
            pos = ref.get("position_geographique") or {}
            for uic in str(ref.get("codes_uic") or "").split(","):
                uic = uic.strip()
                if uic and pos.get("lon") is not None:
                    by_uic[uic] = {"lon": pos["lon"], "lat": pos["lat"], "commune": ref.get("codeinsee"), "ref_name": ref.get("nom")}
        stations = []
        for row in freq:
            uic = str(row.get("code_uic_complet") or "")
            ref = by_uic.get(uic)
            passengers = row.get("total_voyageurs_2025")
            if not ref or not passengers:
                continue
            stations.append({
                "uic": uic, "name": row.get("nom_gare") or ref["ref_name"], "commune": ref["commune"],
                "lon": ref["lon"], "lat": ref["lat"], "passengers": round(passengers),
                "segment": row.get("segmentation_drg"), "year": 2025,
            })
        return {"vintage": "SNCF station traffic 2025", "_files": ["frequentation-gares.json", "gares-de-voyageurs.json"], "stations": stations}
