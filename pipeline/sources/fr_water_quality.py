"""Hub'eau drinking-water compliance samples by commune."""

import json
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from ..core.source import Source, SourceInfo

API = "https://hubeau.eaufrance.fr/api/v1/qualite_eau_potable/resultats_dis"
YEAR = "2025"
DEPARTMENTS = [*(f"{i:02d}" for i in range(1, 20)), "2A", "2B", *(f"{i:02d}" for i in range(21, 96)), "971", "972", "973", "974", "976"]
FIELDS = "code_commune,code_prelevement,conclusion_conformite_prelevement,conformite_limites_bact_prelevement,conformite_limites_pc_prelevement"


def url_for(dep):
    query = urllib.parse.urlencode({
        "code_departement": dep,
        "date_min_prelevement": f"{YEAR}-01-01",
        "date_max_prelevement": f"{YEAR}-12-31",
        # Escherichia coli is measured in routine bacteriological samples; the row also
        # carries the regulatory conclusion for the whole multi-parameter sample.
        "code_parametre": "1449",
        "fields": FIELDS,
        "size": "20000",
    })
    return f"{API}?{query}"


class FrenchWaterQuality(Source):
    info = SourceInfo(
        id="fr_water_quality",
        title="Drinking-water regulatory compliance samples",
        publisher="Hub'eau / Eaufrance",
        homepage="https://hubeau.eaufrance.fr/page/api-qualite-eau-potable",
        license="Licence Ouverte 2.0",
        description="2025 drinking-water control samples. The pipeline uses Escherichia coli rows as one row per routine bacteriological sample and reads the repeated whole-sample regulatory conclusion, including mandatory-limit and quality-reference compliance fields.",
        used_for=["Drinking-water quality lenses"],
    )

    def fetch(self, force=False):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda dep: self.download(url_for(dep), f"samples_{dep}.json", force=force), DEPARTMENTS))

    def process(self):
        communes = {}
        files = []
        total = 0
        for dep in DEPARTMENTS:
            name = f"samples_{dep}.json"
            files.append(name)
            data = json.load(open(self.raw_dir / name, encoding="utf-8"))
            rows = data.get("data", [])
            if len(rows) < data.get("count", 0):
                raise ValueError(f"truncated Hub'eau department export: {dep}")
            seen = set()
            for row in rows:
                key = (row.get("code_commune"), row.get("code_prelevement"))
                if not row.get("code_commune") or key in seen:
                    continue
                seen.add(key)
                total += 1
                out = communes.setdefault(row["code_commune"], {"samples": 0, "limit_ok": 0, "limit_valid": 0, "full_ok": 0})
                out["samples"] += 1
                bact = row.get("conformite_limites_bact_prelevement")
                phys = row.get("conformite_limites_pc_prelevement")
                if bact in {"C", "N"} and phys in {"C", "N"}:
                    out["limit_valid"] += 1
                    if bact == "C" and phys == "C":
                        out["limit_ok"] += 1
                if row.get("conclusion_conformite_prelevement") == "Eau d'alimentation conforme aux exigences de qualité en vigueur pour l'ensemble des paramètres mesurés.":
                    out["full_ok"] += 1
        if len(communes) < 25_000 or total < 200_000:
            raise ValueError(f"unexpected drinking-water sample coverage: {len(communes)} communes, {total} samples")
        return {
            "vintage": f"Hub'eau drinking-water control samples, {YEAR}",
            "_files": files,
            "year": int(YEAR),
            "communes": communes,
            "samples": total,
        }
