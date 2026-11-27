"""INSEE Base permanente des équipements detailed equipment registry."""

from collections import defaultdict

import pyarrow.parquet as pq

from ..core.source import Source, SourceInfo

DATA_URL = "https://static.data.gouv.fr/resources/base-permanente-des-equipements-3/20260330-145351/bpe24.parquet"
TYPES_URL = "https://www.insee.fr/fr/metadonnees/source/fichier/BPE25_table_passage.csv"


def normalize_commune(code):
    if code.startswith("751"):
        return "75056"
    if code.startswith("132"):
        return "13055"
    if code.startswith("6938"):
        return "69123"
    return code


class FrenchPublicEquipment(Source):
    info = SourceInfo(
        id="fr_public_equipment",
        title="Base permanente des équipements 2024, detailed equipment file",
        publisher="Insee (stable data.gouv mirror)",
        homepage="https://www.insee.fr/fr/statistiques/8217525?sommaire=8217537",
        license="Licence Ouverte 2.0 (Etalab)",
        description="Detailed registry of publicly accessible equipment and services at 1 January 2024, using the stable "
        "data.gouv mirror of INSEE's parquet extract. Rows are counted with NBEQUIDENT where INSEE groups identical "
        "equipment; arrondissement codes are normalized to Paris, Lyon and Marseille commune totals.",
        used_for=["Everyday-services, food-shop, pharmacy, sports/culture, hospital-service, childcare, eldercare, cinema and rail-station lenses"],
    )

    def fetch(self, force=False):
        self.download(DATA_URL, "bpe24.parquet", force=force, expect_binary=True)
        self.download(TYPES_URL, "BPE25_table_passage.csv", force=force)

    def process(self):
        path = self.raw_dir / "bpe24.parquet"
        cols = ["DEPCOM", "DOM", "SDOM", "TYPEQU", "NBEQUIDENT"]
        rows = defaultdict(lambda: {"food_shops": 0.0, "pharmacies": 0.0, "culture_sports": 0.0, "hospital_services": 0.0, "childcare": 0.0, "eldercare": 0.0, "cinemas": 0.0, "swimming_pools": 0.0, "rail_stations": 0.0, "food": 0, "pharmacy": 0, "gp": 0, "school": 0, "post": 0, "library": 0})
        total = 0
        for batch in pq.ParquetFile(path).iter_batches(batch_size=200_000, columns=cols):
            d = batch.to_pydict()
            for code0, dom, sdom, typ, nbeq in zip(d["DEPCOM"], d["DOM"], d["SDOM"], d["TYPEQU"], d["NBEQUIDENT"]):
                if not code0:
                    continue
                total += 1
                code = normalize_commune(code0)
                w = nbeq or 1
                r = rows[code]
                if sdom == "B2":
                    r["food_shops"] += w; r["food"] = 1
                if typ == "D307":
                    r["pharmacies"] += w; r["pharmacy"] = 1
                if dom == "F":
                    r["culture_sports"] += w
                if typ.startswith("D1") and len(typ) == 4:
                    r["hospital_services"] += w
                if typ in {"D502", "D509"}:
                    r["childcare"] += w
                if typ in {"D401", "D402", "D403"}:
                    r["eldercare"] += w
                if typ == "F303":
                    r["cinemas"] += w
                if typ == "F101":
                    r["swimming_pools"] += w
                if typ in {"E107", "E108", "E109"}:
                    r["rail_stations"] += w
                if typ == "D265": r["gp"] = 1
                if typ == "C108": r["school"] = 1
                if typ in {"A206", "A207"}: r["post"] = 1
                if typ == "F307": r["library"] = 1
        out = {}
        for code, r in rows.items():
            score = sum(r[k] for k in ["food", "pharmacy", "gp", "school", "post", "library"])
            out[code] = {"food_shops": round(r["food_shops"], 2), "pharmacies": round(r["pharmacies"], 2), "culture_sports": round(r["culture_sports"], 2), "hospital_services": round(r["hospital_services"], 2), "childcare": round(r["childcare"], 2), "eldercare": round(r["eldercare"], 2), "cinemas": round(r["cinemas"], 2), "swimming_pools": round(r["swimming_pools"], 2), "rail_stations": round(r["rail_stations"], 2), "essential_score": score}
        print(f"    {total} equipment rows in {len(out)} communes; pharmacies {sum(r['pharmacies'] for r in out.values())}")
        if len(out) < 30_000 or sum(r["pharmacies"] for r in out.values()) < 18_000:
            raise ValueError("unexpected BPE commune totals")
        return {"vintage": "INSEE Base permanente des équipements 2024", "_files": ["bpe24.parquet", "BPE25_table_passage.csv"], "rows": out, "total_rows": total}
