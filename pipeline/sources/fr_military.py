"""Historical French defense-base personnel published by the Ministry of the Armed Forces."""

from __future__ import annotations

import json

from ..core.source import Source, SourceInfo

RESOURCE_ID = "c64d1793-2ff4-438c-8403-96c25ecfe29e"
URL = f"https://tabular-api.data.gouv.fr/api/resources/{RESOURCE_ID}/data/?page_size=200"
FILE = "defense-base-personnel-2012.json"


class FrenchMilitary(Source):
    info = SourceInfo(
        id="fr_military",
        title="Defense-base personnel, 2012",
        publisher="Ministère des Armées",
        homepage="https://www.data.gouv.fr/datasets/suivi-des-effectifs-en-organisation-au-sein-des-bases-de-defense-00000000",
        license="Licence Ouverte / Open Licence",
        description="Stationed personnel and formation counts by base de défense in 2012. The original XLS resource is no "
        "longer directly downloadable, so the pipeline uses data.gouv.fr's preserved Tabular API extraction of that resource. "
        "Detailed rows exclude most of Île-de-France; the file provides one aggregate Île-de-France total. This is historical "
        "administrative-open-data, not a current order of battle or a base-boundary inventory.",
        used_for=["Military installations and garrison cities"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=False)

    def process(self):
        payload = json.loads((self.raw_dir / FILE).read_text())
        rows = []
        ile_de_france = None
        published_total = None
        for row in payload["data"]:
            first = next((k for k in row if k.startswith("SYNTHESE DES BdD")), None)
            if not first or row.get(first) in (None, "Base de défense"):
                continue
            name = row[first]
            if name == "Effectif en organisation":
                try:
                    published_total = int(row.get("Unnamed: 3") or 0)
                except ValueError:
                    pass
                continue
            try:
                personnel = int(row.get("Unnamed: 3") or 0)
            except ValueError:
                continue
            item = {
                "name": name,
                "department": str(row.get("Unnamed: 1") or "").strip(),
                "seat": row.get("Unnamed: 2"),
                "personnel": personnel,
                "formations": int(row["Unnamed: 4"]) if str(row.get("Unnamed: 4") or "").isdigit() else None,
            }
            if name == "ILE DE FRANCE":
                ile_de_france = item
                continue
            dep = item["department"]
            if not dep.isdigit() or int(dep) > 95:
                continue  # overseas and foreign rows are outside the metropolitan-France map
            rows.append(item)
        rows.sort(key=lambda r: r["personnel"], reverse=True)
        print(f"    {len(rows)} metropolitan defense bases; Île-de-France aggregate {ile_de_france and ile_de_france['personnel']}")
        return {
            "vintage": "Ministry of the Armed Forces defense-base personnel, 2012",
            "_files": [FILE],
            "year": 2012,
            "resource_id": RESOURCE_ID,
            "rows": rows,
            "ile_de_france": ile_de_france,
            "published_total": published_total,
        }
