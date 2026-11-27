"""RTE electricity-transmission network statistics by department."""

import csv
import io
import unicodedata
from collections import defaultdict

from ..core.source import Source, SourceInfo

ODS = "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets"
LINE_URL = f"{ODS}/longueur-departement-circuit-file-pylone/exports/csv?delimiter=%3B&use_labels=false"
SITE_URL = f"{ODS}/postes-electriques-rte/exports/csv?delimiter=%3B&use_labels=false"


def read_csv(raw):
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig")), delimiter=";"))


def norm_name(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(value.upper().replace("-", " ").replace("'", " ").split())


def voltage_value(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 500.0 if value == "COURANT CONTINU" else 0.0


class FrenchEnergyNetwork(Source):
    info = SourceInfo(
        id="fr_energy_network",
        title="RTE transmission network lengths and electrical sites",
        publisher="RTE through Open Data Réseaux Énergies (ODRÉ)",
        homepage="https://odre.opendatasoft.com/",
        license="Licence Ouverte 2.0",
        description="Annual departmental lengths of RTE transmission circuits and pylon routes, plus the public registry of RTE transformation sites and connection points. "
        "RTE no longer publishes exact public network geometry for security reasons, so this extract uses reproducible departmental statistics rather than precise line or substation coordinates.",
        used_for=["Transmission-network infrastructure lenses"],
    )

    def fetch(self, force=False):
        self.download(LINE_URL, "line_lengths.csv", force=force)
        self.download(SITE_URL, "electrical_sites.csv", force=force)

    def process(self):
        line_rows = read_csv((self.raw_dir / "line_lengths.csv").read_bytes())
        site_rows = read_csv((self.raw_dir / "electrical_sites.csv").read_bytes())
        year = max(int(r["annee"]) for r in line_rows if r.get("annee"))
        lines = defaultdict(lambda: defaultdict(float))
        for r in line_rows:
            if int(r["annee"]) != year:
                continue
            dep = str(r["insee_departement"]).zfill(2)
            circuit = float(r.get("longueur_circuit_km") or 0)
            route = float(r.get("longueur_file_pylone") or 0)
            high = voltage_value(r.get("niveau_tension_kv")) >= 225
            non_overhead = r.get("configuration") in {"Souterrain", "Immerge"}
            row = lines[dep]
            row["circuit_km"] += circuit
            row["route_km"] += route
            if high:
                row["high_circuit_km"] += circuit
                row["high_route_km"] += route
            if non_overhead:
                row["non_overhead_circuit_km"] += circuit

        # ODRÉ gives site department names rather than INSEE codes. The builder resolves
        # them against official county names; this source keeps the normalized spelling.
        sites = defaultdict(lambda: defaultdict(int))
        unmatched = defaultdict(int)
        for r in site_rows:
            if r.get("etat") != "EN EXPLOITATION":
                continue
            name = norm_name(r.get("departement"))
            if not name:
                unmatched["blank"] += 1
                continue
            high = voltage_value((r.get("tension") or "").replace("kV", "").replace("<", "")) >= 225
            if r.get("fonction") == "Poste de transformation":
                sites[name]["transformation"] += 1
                if high:
                    sites[name]["transformation_high"] += 1
            elif r.get("fonction") == "Point de piquage":
                sites[name]["connection_points"] += 1

        if len(lines) < 90 or sum(v["circuit_km"] for v in lines.values()) < 90_000:
            raise ValueError("unexpected RTE line-length coverage")
        if sum(v["transformation"] for v in sites.values()) < 3_500:
            raise ValueError("unexpected RTE transformation-site coverage")
        return {
            "vintage": f"RTE network statistics, {year}; electrical sites current ODRÉ publication",
            "_files": ["line_lengths.csv", "electrical_sites.csv"],
            "year": year,
            "lines": {k: dict(v) for k, v in lines.items()},
            "sites_by_department_name": {k: dict(v) for k, v in sites.items()},
            "unmatched_site_rows": dict(unmatched),
        }
