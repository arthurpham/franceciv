"""French transport infrastructure inputs: Natural Earth networks plus Eurostat hub traffic."""

from __future__ import annotations

import csv
import io
import json

from ..core.geo import bbox_intersects, geojson_lines, load_geojson
from ..core.source import Source, SourceInfo
from .fr_eurostat import API, jsonstat_rows

TAG = "v5.1.2"
NE_BASE = f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{TAG}/geojson"
BBOX = (-6.0, 41.0, 10.2, 51.4)
YEAR = 2023
NE_FILES = {
    "roads": "ne_10m_roads",
    "rail": "ne_10m_railroads",
    "ports": "ne_10m_ports",
}
OURAIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"


class FrenchTransport(Source):
    info = SourceInfo(
        id="fr_transport",
        title="French transport networks and hub traffic",
        publisher="Natural Earth, Eurostat and OurAirports",
        homepage="https://www.naturalearthdata.com/",
        license="Public domain / Eurostat free reuse policy",
        description=(
            "Natural Earth 1:10m road, railroad and port geometries; Eurostat avia_paoa airport passengers "
            f"and mar_go_aa port tonnage ({YEAR}); OurAirports coordinates and names. Natural Earth network geometry is "
            "schematic map art rather than a complete infrastructure inventory."
        ),
        used_for=["Road and rail tile improvements", "Airport sites", "Port sites"],
    )

    def fetch(self, force=False):
        for kind, name in NE_FILES.items():
            self.download(f"{NE_BASE}/{name}.geojson", f"{name}.geojson", force=force)
        self.download(OURAIRPORTS_URL, "ourairports.csv", force=force)
        for year in (YEAR, YEAR - 1):
            self.download(f"{API}/avia_paoa?format=JSON&lang=en&time={year}&unit=PAS", f"avia_paoa_{year}.json", force=force)
        self.download(f"{API}/mar_go_aa?format=JSON&lang=en&time={YEAR}", f"mar_go_aa_{YEAR}.json", force=force)

    def process(self):
        files = [f"{n}.geojson" for n in NE_FILES.values()] + ["ourairports.csv", f"avia_paoa_{YEAR}.json", f"avia_paoa_{YEAR-1}.json", f"mar_go_aa_{YEAR}.json"]
        roads, rail, ne_ports = [], [], []
        for f in load_geojson(self.raw_dir / f"{NE_FILES['roads']}.geojson"):
            for line in geojson_lines(f["geometry"]):
                if bbox_intersects(line, BBOX):
                    roads.append({"properties": f["properties"], "line": line})
        for f in load_geojson(self.raw_dir / f"{NE_FILES['rail']}.geojson"):
            for line in geojson_lines(f["geometry"]):
                if bbox_intersects(line, BBOX):
                    rail.append({"properties": f["properties"], "line": line})
        for f in load_geojson(self.raw_dir / f"{NE_FILES['ports']}.geojson"):
            x, y = f["geometry"]["coordinates"][:2]
            if BBOX[0] <= x <= BBOX[2] and BBOX[1] <= y <= BBOX[3]:
                ne_ports.append({"name": f["properties"].get("name"), "lon": x, "lat": y, "scale": f["properties"].get("scalerank")})

        airports = []
        with open(self.raw_dir / "ourairports.csv", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    lon, lat = float(r["longitude_deg"]), float(r["latitude_deg"])
                except (TypeError, ValueError):
                    continue
                if not (BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3] and r.get("iso_country") == "FR"):
                    continue
                airports.append({
                    "ident": r.get("ident"), "iata": r.get("iata_code") or None, "name": r.get("name"),
                    "municipality": r.get("municipality"), "type": r.get("type"), "scheduled": r.get("scheduled_service") == "yes",
                    "lon": lon, "lat": lat,
                })

        air = {}
        for year in (YEAR, YEAR - 1):
            rows = jsonstat_rows(self.raw_dir / f"avia_paoa_{year}.json")
            for r in rows:
                if r.get("freq") == "A" and r.get("tra_meas") == "PAS_BRD" and r.get("schedule") == "TOTAL" and r.get("tra_cov") == "TOTAL" and r.get("rep_airp", "").startswith("FR_L"):
                    air.setdefault(r["rep_airp"][3:], {})[year] = r["value"]
        labels_air = json.load(open(self.raw_dir / f"avia_paoa_{YEAR}.json", encoding="utf-8"))["dimension"]["rep_airp"]["category"]["label"]

        ports = {}
        rows = jsonstat_rows(self.raw_dir / f"mar_go_aa_{YEAR}.json")
        for r in rows:
            if r.get("direct") == "TOTAL" and r.get("rep_mar", "").startswith("FR_") and len(r["rep_mar"]) > 4:
                ports[r["rep_mar"]] = {"tons": r["value"] * 1000, "year": YEAR}
        labels_port = json.load(open(self.raw_dir / f"mar_go_aa_{YEAR}.json", encoding="utf-8"))["dimension"]["rep_mar"]["category"]["label"]

        print(f"    roads {len(roads)}, rail {len(rail)}, airports {len(airports)}, Eurostat airports {len(air)}, ports {len(ports)}")
        return {
            "vintage": f"Natural Earth {TAG}; Eurostat transport {YEAR}; OurAirports current extract",
            "_files": files,
            "roads": roads, "rail": rail, "ne_ports": ne_ports, "airports": airports,
            "air_passengers": air, "airport_labels": labels_air,
            "port_tons": ports, "port_labels": labels_port,
        }
