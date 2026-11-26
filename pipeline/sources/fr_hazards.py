"""GASPAR natural-disaster recognitions by commune."""

from __future__ import annotations

import csv
import io
import zipfile
from collections import Counter, defaultdict

from ..core.source import Source, SourceInfo

URL = "https://files.georisques.fr/GASPAR/gaspar.zip"
FILE = "gaspar.zip"
GROUPS = {
    "flood": {"ICB", "IRN", "CMV"},
    "drought": {"SEC"},
    "storm": {"TMP", "GRL"},
    "ground": {"MVT", "GLT", "EFA", "PDN", "AVA"},
}


class FrenchHazards(Source):
    info = SourceInfo(
        id="fr_hazards",
        title="GASPAR natural-disaster recognitions",
        publisher="Ministère de la Transition écologique / Géorisques",
        homepage="https://www.data.gouv.fr/datasets/base-nationale-de-gestion-assistee-des-procedures-administratives-relatives-aux-risques-gaspar",
        license="Licence Ouverte / Open Licence",
        description="National GASPAR export of catastrophe-naturelle recognitions. Each row is one recognition for "
        "one commune, event and hazard; it is an administrative insurance recognition, not a direct measure of damage.",
        used_for=["Natural-disaster frequency and hazard-type lenses"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=True)

    def process(self):
        zf = zipfile.ZipFile(self.raw_dir / FILE)
        name = sorted(n for n in zf.namelist() if n.startswith("catnat_gaspar"))[-1]
        rows = defaultdict(Counter)
        labels = {}
        first_year, last_year = 9999, 0
        with zf.open(name) as f:
            for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"), delimiter=";"):
                year = int((r.get("date_debut") or "0000")[:4] or 0)
                if year < 2000:
                    continue
                code = r["code_commune"]
                risk = r["num_risque_jo"]
                rows[code]["events"] += 1
                rows[code][risk] += 1
                labels[risk] = r["lib_risque_jo"]
                first_year, last_year = min(first_year, year), max(last_year, year)
        grouped = {}
        for commune, counts in rows.items():
            out = {"events": counts["events"]}
            for key, codes in GROUPS.items():
                out[key] = sum(counts[c] for c in codes)
            other = counts["events"] - sum(out[k] for k in GROUPS)
            out["other"] = max(0, other)
            shares = {k: out[k] for k in ["flood", "drought", "storm", "ground", "other"]}
            out["dominant"] = max(shares, key=shares.get) if shares else None
            grouped[commune] = out
        print(f"    {len(grouped)} communes with recognitions since 2000")
        return {"vintage": f"GASPAR export {name.rsplit('_',1)[1][:10]}; recognitions 2000–{last_year}", "_files": [FILE],
                "years": [2000, last_year], "communes": grouped, "labels": labels}
