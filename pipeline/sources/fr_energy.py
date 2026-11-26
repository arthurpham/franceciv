"""French electricity generation and storage installations from the national ODRÉ registry."""

from __future__ import annotations

import json

from ..core.source import Source, SourceInfo

DATASET = "registre-national-installation-production-stockage-electricite-agrege"
URL = (
    "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
    f"{DATASET}/exports/json?select=nominstallation,codeinseecommune,codeinseecommuneimplantation,"
    "codefiliere,filiere,codetechnologie,technologie,combustible,typestockage,puismaxinstallee,"
    "puismaxinstalleedischarge,regime,datemiseenservice_date,nbgroupes,codedepartement"
    "&where=puismaxinstallee%3E%3D500%20or%20puismaxinstalleedischarge%3E%3D500"
)
FILE = "odre-installations-ge500kw.json"


class FrenchEnergyRegistry(Source):
    info = SourceInfo(
        id="fr_energy",
        title="National registry of electricity generation and storage installations",
        publisher="RTE, Enedis and network operators through Open Data Réseaux Énergies (ODRÉ)",
        homepage="https://odre.opendatasoft.com/explore/dataset/registre-national-installation-production-stockage-electricite-agrege/",
        license="Licence Ouverte 2.0",
        description="Installations of at least 500 kW connected to the French electricity networks, with sector, technology, "
        "maximum installed or discharge power, municipality and service status.",
        used_for=["Power-plant and energy-storage resources on the map"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force)

    def process(self):
        rows = json.loads((self.raw_dir / FILE).read_text(encoding="utf-8"))
        print(f"    {len(rows)} registry rows")
        return {"vintage": "ODRÉ national registry, latest published extract", "_files": [FILE], "rows": rows}
