"""Ministry of Culture Mérimée protected heritage buildings."""

import csv
from collections import defaultdict

from .fr_hazards import COG_BASE, COG_COMMUNES, COG_MOVEMENTS, commune_resolver, read_cog_csv
from ..core.source import Source, SourceInfo

URL = "https://ministere-culture.s3.sbg.io.cloud.ovh.net/POP/merimee.csv"


class FrenchHeritage(Source):
    info = SourceInfo(
        id="fr_heritage",
        title="Immeubles protégés au titre des Monuments historiques",
        publisher="Ministère de la Culture",
        homepage="https://www.data.gouv.fr/datasets/immeubles-proteges-au-titre-des-monuments-historiques-2",
        license="Licence Ouverte 2.0",
        description="National Mérimée list of buildings protected as Monuments historiques. Rows are attributed to current "
        "communes through INSEE municipal-merger mappings where necessary; protection text distinguishes classified (classé) "
        "from registered (inscrit) protection.",
        used_for=["Protected-heritage access and classified-share lenses"],
    )

    def fetch(self, force=False):
        self.download(URL, "merimee.csv", force=force, expect_binary=True)
        self.download(f"{COG_BASE}/{COG_COMMUNES}", COG_COMMUNES, force=force)
        self.download(f"{COG_BASE}/{COG_MOVEMENTS}", COG_MOVEMENTS, force=force)

    def process(self):
        resolve = commune_resolver(read_cog_csv(self.raw_dir / COG_COMMUNES), read_cog_csv(self.raw_dir / COG_MOVEMENTS))
        rows = defaultdict(lambda: {"total": 0, "classified": 0})
        total = mapped = empty = 0
        with open(self.raw_dir / "merimee.csv", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f, delimiter="|"):
                total += 1
                raw = (r.get("COG_Insee_lors_de_la_protection") or "").strip().zfill(5)
                if not raw:
                    empty += 1
                    continue
                code = resolve(raw)
                mapped += code != raw
                rec = rows[code]
                rec["total"] += 1
                if "classement" in (r.get("Precision_de_la_protection") or "").lower():
                    rec["classified"] += 1
        out = {c: r for c, r in rows.items()}
        classified = sum(r["classified"] for r in out.values())
        print(f"    {total} protected-building rows in {len(out)} communes; {classified} classified; {mapped} merger-mapped; {empty} blank")
        if total < 35_000 or len(out) < 10_000 or classified < 10_000:
            raise ValueError("unexpected Mérimée heritage totals")
        return {"vintage": "Mérimée protected buildings, current ministry export", "_files": ["merimee.csv", COG_COMMUNES, COG_MOVEMENTS], "rows": out, "total_rows": total}
