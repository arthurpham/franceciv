"""GASPAR natural-disaster recognitions by commune."""

from __future__ import annotations

import csv
import io
import zipfile
from collections import Counter, defaultdict

from ..core.source import Source, SourceInfo

URL = "https://files.georisques.fr/GASPAR/gaspar.zip"
FILE = "gaspar.zip"
COG_BASE = "https://www.insee.fr/fr/statistiques/fichier/8740222"
COG_COMMUNES = "v_commune_2026.csv"
COG_MOVEMENTS = "v_mvt_commune_2026.csv"
GROUPS = {
    "flood": {"ICB", "IRN", "CMV"},
    "drought": {"SEC"},
    "storm": {"TMP", "GRL"},
    "ground": {"MVT", "GLT", "EFA", "PDN", "AVA"},
}


def read_cog_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def commune_resolver(current_rows, movement_rows):
    """Map historical/delegated codes to current whole communes, conservatively.

    A code borne by a current whole commune is terminal even if it appeared in older
    merger events: codes can survive or be reused, and following those links statically
    misattributes post-split records. Ambiguous splits are likewise left unmapped.
    """
    current_communes = {r["COM"] for r in current_rows if r["TYPECOM"] == "COM"}
    parent = {
        r["COM"]: r["COMPARENT"]
        for r in current_rows
        if r["TYPECOM"] in {"COMD", "COMA", "ARM"} and r["COMPARENT"] and r["COMPARENT"] != r["COM"]
    }
    candidates = defaultdict(set)
    for r in movement_rows:
        if r["DATE_EFF"] < "2000-01-01":
            continue
        if r["TYPECOM_AP"] == "COM" and r["COM_AV"] and r["COM_AP"] and r["COM_AV"] not in current_communes:
            candidates[(r["COM_AV"], r["DATE_EFF"], r["MOD"])].add(r["COM_AP"])
    transitions = {}
    ambiguous = set()
    for (old, _date, _mod), new_codes in sorted(candidates.items(), key=lambda item: item[0][1]):
        if len(new_codes) == 1 and old not in ambiguous:
            new = next(iter(new_codes))
            if new != old:
                transitions[old] = new
        else:
            # A split commune cannot be attributed wholesale to one successor.
            ambiguous.add(old)
            transitions.pop(old, None)

    cache = {}
    def resolve(code):
        if code in cache:
            return cache[code]
        original, seen = code, set()
        while code not in seen:
            seen.add(code)
            if code in current_communes and code not in parent:
                break
            nxt = parent.get(code) or transitions.get(code)
            if not nxt or nxt == code:
                break
            code = nxt
        cache[original] = code
        return code

    return resolve


class FrenchHazards(Source):
    info = SourceInfo(
        id="fr_hazards",
        title="GASPAR natural-disaster recognitions",
        publisher="Ministère de la Transition écologique / Géorisques",
        homepage="https://www.data.gouv.fr/datasets/base-nationale-de-gestion-assistee-des-procedures-administratives-relatives-aux-risques-gaspar",
        license="Licence Ouverte / Open Licence",
        description="National GASPAR export of catastrophe-naturelle recognitions. Each row is one recognition for "
        "one commune, event and hazard; it is an administrative insurance recognition, not a direct measure of damage. "
        "INSEE COG commune movements and delegated-commune parents map records through post-2000 municipal mergers.",
        used_for=["Natural-disaster frequency and hazard-type lenses"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=True)
        self.download(f"{COG_BASE}/{COG_COMMUNES}", COG_COMMUNES, force=force)
        self.download(f"{COG_BASE}/{COG_MOVEMENTS}", COG_MOVEMENTS, force=force)

    def process(self):
        zf = zipfile.ZipFile(self.raw_dir / FILE)
        name = sorted(n for n in zf.namelist() if n.startswith("catnat_gaspar"))[-1]
        rows = defaultdict(Counter)
        labels = {}
        resolve_commune = commune_resolver(read_cog_csv(self.raw_dir / COG_COMMUNES), read_cog_csv(self.raw_dir / COG_MOVEMENTS))
        mapped_codes = 0
        first_year, last_year = 9999, 0
        with zf.open(name) as f:
            for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"), delimiter=";"):
                year = int((r.get("date_debut") or "0000")[:4] or 0)
                if year < 2000:
                    continue
                raw_code = r["code_commune"]
                code = resolve_commune(raw_code)
                mapped_codes += code != raw_code
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
        print(f"    {len(grouped)} communes with recognitions since 2000; {mapped_codes} rows mapped through commune mergers")
        return {"vintage": f"GASPAR export {name.rsplit('_',1)[1][:10]}; recognitions 2000–{last_year}", "_files": [FILE, COG_COMMUNES, COG_MOVEMENTS],
                "years": [2000, last_year], "communes": grouped, "labels": labels}
