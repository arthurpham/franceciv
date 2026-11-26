"""IGN BD CARTO named watercourse segments."""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from collections import defaultdict

from ..core import fetch
from ..core.source import Source, SourceInfo

COUNT = 5000
FILTER = (
    "(classe_de_largeur IN ('Entre 15 et 50 m', 'Plus de 50 m', 'Entre 50 et 250 m', "
    "'Entre 250 et 1250 m', 'Plus de 1250 m') OR (classe_de_largeur='Sans objet' AND nature='Retenue')) "
    "AND code_du_pays='FR' AND cpx_toponyme_de_cours_d_eau IS NOT NULL"
)


def page_url(start, count=COUNT):
    q = {
        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
        "TYPENAMES": "BDCARTO_V5:troncon_hydrographique", "OUTPUTFORMAT": "application/json",
        "SORTBY": "cleabs", "COUNT": str(count), "SRSNAME": "EPSG:4326",
        "PROPERTYNAME": "cleabs,cpx_toponyme_de_cours_d_eau,classe_de_largeur,nature,geometrie",
        "CQL_FILTER": FILTER, "STARTINDEX": str(start),
    }
    return "https://data.geopf.fr/wfs/ows?" + urllib.parse.urlencode(q)


def filename(i):
    return f"troncons_{i:02d}.json"


def line_length(coords):
    # adequate for ranking: longitude scaled at roughly metropolitan France latitude
    total = 0.0
    for (x0, y0), (x1, y1) in zip(coords, coords[1:]):
        total += math.hypot((x1 - x0) * 75, (y1 - y0) * 111)
    return total


class FrenchHydrography(Source):
    info = SourceInfo(
        id="fr_hydrography",
        title="IGN BD CARTO named watercourses",
        publisher="IGN (Géoplateforme)",
        homepage="https://geoservices.ign.fr/bdcarto",
        license="Licence Ouverte 2.0 (Etalab)",
        description="Named metropolitan watercourse segments at least 15 m wide, plus reservoir axes. The pipeline "
        "keeps the longest named rivers and simplifies their geometry for the map scale.",
        used_for=["Detailed French rivers"],
    )

    def page_count(self):
        if fetch.OFFLINE:
            return len(sorted(self.raw_dir.glob("troncons_*.json")))
        q = urllib.parse.parse_qsl(urllib.parse.urlsplit(page_url(0, 1)).query)
        try:
            with urllib.request.urlopen(page_url(0, 1), timeout=60) as r:
                matched = json.load(r).get("numberMatched") or 0
            return math.ceil(matched / COUNT)
        except Exception:
            cached = len(sorted(self.raw_dir.glob("troncons_*.json")))
            if cached:
                return cached
            raise

    def fetch(self, force=False):
        for i in range(self.page_count()):
            self.download(page_url(i * COUNT), filename(i), force=force, expect_binary=True)

    def process(self):
        lengths = defaultdict(float)
        features = []
        used = []
        for path in sorted(self.raw_dir.glob("troncons_*.json")):
            doc = json.loads(path.read_text())
            used.append(path.name)
            for feat in doc.get("features", []):
                prop = feat.get("properties") or {}
                name = prop.get("cpx_toponyme_de_cours_d_eau")
                geom = feat.get("geometry") or {}
                if not name or geom.get("type") not in {"LineString", "MultiLineString"}:
                    continue
                lines = [geom["coordinates"]] if geom["type"] == "LineString" else geom["coordinates"]
                width = prop.get("classe_de_largeur") or ""
                rank = {"Plus de 1250 m": 2, "Entre 250 et 1250 m": 3, "Entre 50 et 250 m": 5, "Plus de 50 m": 5}.get(width, 7)
                for coords in lines:
                    if len(coords) < 2:
                        continue
                    ln = line_length(coords)
                    lengths[name] += ln
                    features.append({"name": name, "rank": rank, "length": ln, "coords": coords})
        keep_names = {n for n, _ in sorted(lengths.items(), key=lambda kv: kv[1], reverse=True)[:180]}
        rivers = []
        for f in features:
            if f["name"] not in keep_names or f["length"] < 0.25:
                continue
            rivers.append({
                "name": f["name"], "rank": f["rank"],
                "pts": [round(v, 4) for p in f["coords"] for v in p],
            })
        return {
            "vintage": "IGN BD CARTO V5 WFS",
            "_files": used,
            "segments": rivers,
            "river_count": len(keep_names),
        }
