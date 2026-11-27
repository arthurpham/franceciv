"""National consolidated electric-vehicle charging-point registry."""

import csv
import io
from collections import Counter

from ..core.source import Source, SourceInfo

URL = "https://proxy.transport.data.gouv.fr/resource/consolidation-transport-irve-statique"


class FrenchEVCharging(Source):
    info = SourceInfo(
        id="fr_ev_charging",
        title="Base nationale consolidée IRVE, données statiques",
        publisher="Point d'Accès National / transport.data.gouv.fr",
        homepage="https://transport.data.gouv.fr/datasets/base-nationale-des-points-de-recharge-pour-vehicules-electriques-en-france-irve",
        license="Licence Ouverte / Open Licence",
        description="Nightly consolidated and deduplicated static registry of public electric-vehicle charge points. "
        "Rows are individual charge points; the map aggregates valid rows to communes.",
        used_for=["EV charging availability lens"],
    )

    def fetch(self, force=False):
        self.download(URL, "irve-statique.csv", force=force)

    def process(self):
        counts = Counter(); statuses = Counter(); total = 0
        with open(self.raw_dir / "irve-statique.csv", newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                total += 1; statuses[r.get("deduplication_status") or ""] += 1
                code = (r.get("code_insee_commune") or "").strip().zfill(5)
                try:
                    lon = float(r.get("consolidated_longitude") or "nan"); lat = float(r.get("consolidated_latitude") or "nan")
                except ValueError:
                    continue
                if len(code) == 5 and -65 < lon < 60 and -25 < lat < 55:
                    if code.startswith("751"):
                        code = "75056"
                    elif code.startswith("132"):
                        code = "13055"
                    elif code.startswith("6938"):
                        code = "69123"
                    if code != "00000":
                        counts[code] += 1
        print(f"    {sum(counts.values())}/{total} geocoded charge points in {len(counts)} communes; statuses {dict(statuses.most_common(4))}")
        if sum(counts.values()) < 100_000:
            raise ValueError("unexpectedly few consolidated IRVE charge points")
        return {"vintage": "Base nationale consolidée IRVE, nightly static export", "_files": ["irve-statique.csv"], "rows": dict(counts), "total_rows": total}
