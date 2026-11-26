"""Official SNCF Réseau national railway line geometries."""

import csv
import io
import json
import sys

from ..core.source import Source, SourceInfo

URL = "https://ressources.data.sncf.com/api/explore/v2.1/catalog/datasets/formes-des-lignes-du-rfn/exports/csv?use_labels=true"


class FrenchRailNetwork(Source):
    info = SourceInfo(
        id="fr_rail_network",
        title="Fichier de formes des lignes du Réseau Ferré National",
        publisher="SNCF Réseau",
        homepage="https://www.data.gouv.fr/datasets/fichier-de-formes-des-lignes-du-reseau-ferre-national",
        license="Licence Ouverte / Open Licence",
        description="Official geometries of national railway line sections. The pipeline keeps only sections marked Exploitée, "
        "classifying ordinary lines as main lines and connections/main/port tracks as secondary lines for map display.",
        used_for=["Official railway tile geometry"],
    )

    def fetch(self, force=False):
        self.download(URL, "formes-des-lignes-du-rfn.csv", force=force)

    def process(self):
        csv.field_size_limit(sys.maxsize)
        raw = (self.raw_dir / "formes-des-lignes-du-rfn.csv").read_text(encoding="utf-8-sig")
        rows = []
        skipped = 0
        for r in csv.DictReader(io.StringIO(raw), delimiter=";"):
            if r.get("MNEMO") != "EXPLOITE":
                continue
            try:
                geom = json.loads(r["Geo Shape"])
                coords = geom["coordinates"]
                if geom.get("type") == "LineString":
                    parts = [coords]
                elif geom.get("type") == "MultiLineString":
                    parts = coords
                else:
                    continue
                for part in parts:
                    if len(part) >= 2:
                        rows.append({
                            "properties": {
                                "official": True,
                                "code": r.get("CODE_LIGNE"),
                                "track_type": r.get("mnemo_type"),
                                "status": r.get("LIBELLE"),
                            },
                            "line": [(round(float(x), 6), round(float(y), 6)) for x, y, *_ in part],
                        })
            except (KeyError, ValueError, TypeError, json.JSONDecodeError):
                skipped += 1
        print(f"    {len(rows)} active official railway parts, {skipped} skipped")
        if len(rows) < 700:
            raise ValueError("unexpectedly few active SNCF railway geometries")
        return {
            "vintage": "SNCF Réseau national railway line shapes, current open-data export",
            "_files": ["formes-des-lignes-du-rfn.csv"],
            "rows": rows,
        }
