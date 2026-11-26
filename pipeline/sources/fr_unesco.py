"""UNESCO World Heritage List entries located in metropolitan France."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from ..core.source import Source, SourceInfo

URL = "https://whc.unesco.org/en/list/xml/"
FILE = "whc-list.xml"
BBOX = (-5.5, 41.2, 9.9, 51.3)


class FrenchUnesco(Source):
    info = SourceInfo(
        id="fr_unesco",
        title="UNESCO World Heritage List",
        publisher="UNESCO World Heritage Centre",
        homepage="https://whc.unesco.org/en/list/",
        license="UNESCO open use policy (attribution required)",
        description="Official XML export of the World Heritage List, filtered to entries with at least one French "
        "component point in metropolitan France or Corsica. Serial properties keep one representative French point.",
        used_for=["World Heritage wonders on the map"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, headers={"User-Agent": "Mozilla/5.0 franceciv"}, expect_binary=False)

    def process(self):
        root = ET.parse(self.raw_dir / FILE).getroot()
        rows = []
        for row in root.findall("row"):
            if "fr" not in (row.findtext("iso_code") or "").split(","):
                continue
            pois = []
            for poi in row.findall("./geolocations/poi"):
                try:
                    lat, lon = float(poi.findtext("latitude")), float(poi.findtext("longitude"))
                except (TypeError, ValueError):
                    continue
                if poi.findtext("iso2") == "fr" and BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]:
                    pois.append({"lon": lon, "lat": lat})
            if not pois:
                continue
            rows.append({
                "id": row.findtext("id_number"), "unique_number": row.findtext("unique_number"),
                "name": row.findtext("site"), "category": row.findtext("category"),
                "criteria": row.findtext("criteria_txt"), "year": int(row.findtext("date_inscribed") or 0) or None,
                "url": row.findtext("http_url"), "transnational": row.findtext("transnational") == "1",
                "points": pois,
            })
        print(f"    {len(rows)} metropolitan French World Heritage entries")
        return {"vintage": "UNESCO World Heritage List, current XML export", "_files": [FILE], "rows": rows}
