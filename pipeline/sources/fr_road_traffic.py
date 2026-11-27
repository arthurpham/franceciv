"""Official national-road traffic counts and geometry."""

import csv
import struct
import zipfile
from io import BytesIO

from rasterio.warp import transform as warp_transform
from shapely.geometry import LineString

from ..core.source import Source, SourceInfo

BASE = "https://static.data.gouv.fr/resources/trafic-moyen-journalier-annuel-sur-le-reseau-routier-national/20250818"
CSV_URL = BASE + "-100154/tmja-rrnc-2024.csv"
SHP_URL = BASE + "-100425/tmja-rrnc-2024-shp.zip"


def num(s):
    try:
        return float(str(s).replace(",", "."))
    except (TypeError, ValueError):
        return None


def parse_shp(data):
    pos = 100
    shapes = []
    while pos < len(data):
        _rec, clen = struct.unpack(">2i", data[pos:pos + 8])
        stype = struct.unpack("<i", data[pos + 8:pos + 12])[0]
        if stype == 3:
            nparts, npts = struct.unpack("<2i", data[pos + 44:pos + 52])
            parts = struct.unpack("<" + "i" * nparts, data[pos + 52:pos + 52 + 4 * nparts])
            off = pos + 52 + 4 * nparts
            pts = [struct.unpack("<2d", data[off + i * 16:off + i * 16 + 16]) for i in range(npts)]
            pieces = []
            for j, start in enumerate(parts):
                end = parts[j + 1] if j + 1 < len(parts) else npts
                pieces.append(pts[start:end])
            shapes.append(max(pieces, key=len))
        pos += 8 + clen * 2
    return shapes


class FrenchRoadTraffic(Source):
    info = SourceInfo(
        id="fr_road_traffic",
        title="Trafic moyen journalier annuel sur le réseau routier national 2024",
        publisher="Ministère de la Transition écologique / Cerema (data.gouv mirror)",
        homepage="https://www.data.gouv.fr/fr/datasets/trafic-moyen-journalier-annuel-sur-le-reseau-routier-national/",
        license="Licence Ouverte 2.0 (Etalab)",
        description="Official 2024 annual-average-daily-traffic sections on the French national road network, with Lambert-93 polyline geometry. Coverage is the national road network only; departmental and municipal roads are excluded, and some sections use earlier measurement years.",
        used_for=["Official national-road geometry", "road-traffic volume lens", "heavy-vehicle traffic-share lens"],
    )

    def fetch(self, force=False):
        self.download(CSV_URL, "tmja-rrnc-2024.csv", force=force)
        self.download(SHP_URL, "tmja-rrnc-2024-shp.zip", force=force, expect_binary=True)

    def process(self):
        rows = list(csv.DictReader(open(self.raw_dir / "tmja-rrnc-2024.csv", encoding="utf-8"), delimiter=";"))
        zf = zipfile.ZipFile(BytesIO((self.raw_dir / "tmja-rrnc-2024-shp.zip").read_bytes()))
        shp_name = next(n for n in zf.namelist() if n.endswith(".shp"))
        shapes = parse_shp(zf.read(shp_name))
        if len(rows) != len(shapes):
            raise ValueError(f"TMJA row/geometry mismatch: {len(rows)} rows, {len(shapes)} shapes")
        out = []
        for row, pts in zip(rows, shapes):
            xs, ys = zip(*pts)
            lons, lats = warp_transform("EPSG:2154", "EPSG:4326", list(xs), list(ys))
            line = list(zip(lons, lats))
            if len(line) > 3:
                line = list(LineString(line).simplify(0.001, preserve_topology=True).coords)
            tmja = num(row.get("TMJA"))
            heavy = num(row.get("ratio_PL"))
            if tmja is None or len(line) < 2:
                continue
            out.append({
                "route": row.get("route"), "tmja": round(tmja), "heavy_share": round(heavy / 100, 4) if heavy is not None and heavy <= 100 else None,
                "measurement_year": int(row.get("anneeMesureTrafic") or 2024), "count_type": row.get("typeComptageTrafic_lib"),
                "length_m": round(num(row.get("longueur")) or 0), "line": [[round(x, 5), round(y, 5)] for x, y in line],
            })
        print(f"    {len(out)} national-road traffic sections; {sum(r['length_m'] for r in out) / 1000:.0f} km")
        if len(out) < 1000 or sum(r["length_m"] for r in out) < 7_000_000:
            raise ValueError("unexpected TMJA coverage")
        return {"vintage": "TMJA national road network 2024 reference year; section measurement years vary", "_files": ["tmja-rrnc-2024.csv", "tmja-rrnc-2024-shp.zip"], "rows": out}
