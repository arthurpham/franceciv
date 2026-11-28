"""Cartofriches brownfield-site inventory."""

import csv
import re

from ..core.source import Source, SourceInfo

URL = "https://static.data.gouv.fr/resources/sites-references-dans-cartofriches/20261007-122232/friches-standard.csv"
POINT = re.compile(r"POINT\s*\(([-0-9.]+)\s+([-0-9.]+)\)")


class FrenchBrownfields(Source):
    info = SourceInfo(
        id="fr_brownfields",
        title="Sites referenced in Cartofriches",
        publisher="Cerema / Datafoncier",
        homepage="https://www.data.gouv.fr/datasets/sites-references-dans-cartofriches",
        license="Licence Ouverte / Open Licence",
        description="Standardized national Cartofriches export of identified brownfield sites. Rows are heterogeneous local inventories with different survey dates and completeness; absence of a site is not proof that no brownfield exists. Point coordinates are inventory locations, not legal parcel boundaries.",
        used_for=["Brownfield-site density and land-area lenses"],
    )

    def fetch(self, force=False):
        self.download(URL, "friches-standard.csv", force=force)

    def process(self):
        rows = []
        skipped = 0
        statuses = {}
        with open(self.raw_dir / "friches-standard.csv", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f, delimiter=";"):
                match = POINT.match(row.get("geompoint") or "")
                if not match:
                    skipped += 1
                    continue
                try:
                    surface = float(row.get("unite_fonciere_surface") or 0)
                except ValueError:
                    surface = 0
                status = (row.get("site_statut") or "").strip().lower() or "unknown"
                statuses[status] = statuses.get(status, 0) + 1
                rows.append({
                    "id": row.get("site_id"), "name": row.get("site_nom") or "Unnamed site",
                    "commune": row.get("comm_insee"), "type": row.get("site_type") or None,
                    "status": status, "surface_m2": surface,
                    "lon": float(match.group(1)), "lat": float(match.group(2)),
                    "updated": row.get("site_actu_date") or row.get("site_identif_date") or None,
                })
        if len(rows) < 25_000 or skipped > len(rows) * 0.05:
            raise ValueError(f"unexpected Cartofriches coverage: {len(rows)} geocoded rows, {skipped} skipped")
        dates = sorted(r["updated"] for r in rows if r["updated"] and re.match(r"20\d\d", r["updated"]))
        return {
            "vintage": "Cartofriches standardized export, October 2026",
            "_files": ["friches-standard.csv"],
            "rows": rows,
            "statuses": statuses,
            "ungeocoded_rows": skipped,
        }
