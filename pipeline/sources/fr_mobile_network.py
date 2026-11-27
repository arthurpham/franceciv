"""ARCEP Mon Réseau Mobile operator site deployment."""

import csv
from collections import defaultdict

from ..core.source import Source, SourceInfo

BASE = "https://data.arcep.fr/mobile/sites/2026_T2/"
FILES = {"metropole": "2026_T2_sites_Metropole.csv", "outremer": "2026_T2_sites_Outremer.csv"}


class FrenchMobileNetwork(Source):
    info = SourceInfo(
        id="fr_mobile_network",
        title="Mon Réseau Mobile operator site deployment",
        publisher="ARCEP",
        homepage="https://www.data.gouv.fr/datasets/mon-reseau-mobile",
        license="Licence Ouverte 2.0 (Etalab)",
        description="Quarterly operator-reported mobile-site deployment files for metropolitan and overseas France. "
        "Rows are operator-site records with 2G/3G/4G/5G capability flags. Site presence is a supply/competition proxy, "
        "not a theoretical coverage boundary or measured quality-of-service result.",
        used_for=["4G operator-choice and 5G-availability lenses"],
    )

    def fetch(self, force=False):
        for key, fn in FILES.items():
            self.download(BASE + fn, f"sites_{key}.csv", force=force)

    def process(self):
        rows = defaultdict(lambda: {"ops4g": set(), "has5g": False, "sites": 0})
        total = 0
        for key in FILES:
            with open(self.raw_dir / f"sites_{key}.csv", newline="", encoding="latin1") as f:
                for r in csv.DictReader(f, delimiter=";"):
                    total += 1
                    raw = (r.get("insee_com") or "").strip()
                    if not raw or not raw.replace("A", "").replace("B", "").isdigit():
                        continue
                    code = raw.zfill(5)
                    op = (r.get("nom_op") or "").strip()
                    rec = rows[code]
                    rec["sites"] += 1
                    if r.get("site_4g") == "1" and op:
                        rec["ops4g"].add(op)
                    if r.get("site_5g") == "1":
                        rec["has5g"] = True
        out = {code: {"operators4g": len(r["ops4g"]), "has5g": r["has5g"], "sites": r["sites"]} for code, r in rows.items()}
        print(f"    {total} operator-site rows in {len(out)} communes; 5G communes {sum(r['has5g'] for r in out.values())}")
        if len(out) < 20_000 or total < 100_000:
            raise ValueError("unexpected mobile-site totals")
        return {"vintage": "ARCEP Mon Réseau Mobile sites, 2026 T2", "_files": [f"sites_{k}.csv" for k in FILES], "rows": out, "total_rows": total}
