"""SDES 2019 region-to-region freight flows by road, rail and inland waterway."""

from __future__ import annotations

import math

import openpyxl

from ..core.source import Source, SourceInfo

BASE = "https://www.ecologie.gouv.fr/sites/default/files/documents/"
FILES = {
    "road": "TRM_2019.xlsx",
    "rail": "Ferro_2019_diff.xlsx",
    "water": "VNF_2019.xlsx",
}
# 2016 NUTS-2 regions aggregated to the current metropolitan regions used on the map.
CURRENT = {
    "FR10": "IDF", "FRB0": "CVL",
    "FRC1": "BFC", "FRC2": "BFC",
    "FRD1": "NOR", "FRD2": "NOR",
    "FRE1": "HDF", "FRE2": "HDF",
    "FRF1": "GES", "FRF2": "GES", "FRF3": "GES",
    "FRG0": "PDL", "FRH0": "BRE",
    "FRI1": "NAQ", "FRI2": "NAQ", "FRI3": "NAQ",
    "FRJ1": "OCC", "FRJ2": "OCC",
    "FRK1": "ARA", "FRK2": "ARA",
    "FRL0": "PAC", "FRM0": "COR",
}


def haversine(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


class FrenchFreight(Source):
    info = SourceInfo(
        id="fr_freight",
        title="National goods-flow data, 2019",
        publisher="SDES / ministère de la Transition écologique",
        homepage="https://www.ecologie.gouv.fr/politiques-publiques/donnees-nationales-flux-marchandises",
        license="Licence Ouverte / Open Licence 2.0",
        description="2019 non-directional region-to-region goods flows by road, rail and inland waterway. "
        "The source publishes tonne-kilometres; some rail pairs are suppressed for statistical secrecy.",
        used_for=["Freight trade routes and modal split"],
    )

    def fetch(self, force=False):
        for fn in FILES.values():
            self.download(BASE + fn, fn, force=force, expect_binary=True)

    def rows_from(self, mode, fn):
        wb = openpyxl.load_workbook(self.raw_dir / fn, read_only=True, data_only=True)
        ws = wb.active
        ws.reset_dimensions()  # these ministry files declare dimension A1 although they have many columns
        rows = ws.iter_rows(values_only=True)
        header = next(rows)
        ix = {name: i for i, name in enumerate(header)}
        value_col = "MTKM" if mode == "rail" else "TKM"
        out, suppressed_rows = [], []
        for r in rows:
            old_a, old_b = r[ix["ORIG_NUTS2016"]], r[ix["DEST_NUTS2016"]]
            a, b = CURRENT.get(old_a), CURRENT.get(old_b)
            if not a or not b or a == b:
                continue
            value = r[ix[value_col]]
            if not isinstance(value, (int, float)):
                suppressed_rows.append({"mode": mode, "old_a": old_a, "old_b": old_b, "a": a, "b": b})
                continue
            mtkm = value if mode == "rail" else value / 1e6
            dist = haversine(r[ix["ORIG_NUTS2016_longitude"]], r[ix["ORIG_NUTS2016_latitude"]], r[ix["DEST_NUTS2016_longitude"]], r[ix["DEST_NUTS2016_latitude"]])
            out.append({
                "mode": mode, "old_a": old_a, "old_b": old_b, "a": a, "b": b,
                "a_name": r[ix["ORIG_NUTS2016_LIBELLE"]], "b_name": r[ix["DEST_NUTS2016_LIBELLE"]],
                "mtkm": mtkm, "dist_km": dist, "tons_est": mtkm * 1e6 / max(80.0, dist),
            })
        return out, suppressed_rows

    def process(self):
        rows = []
        suppressed_rows = []
        suppressed = {}
        for mode, fn in FILES.items():
            part, miss = self.rows_from(mode, fn)
            rows += part
            suppressed_rows += miss
            suppressed[mode] = len(miss)
        print(f"    {len(rows)} usable old-region flow rows; suppressed rail rows {suppressed.get('rail', 0)}")
        return {"vintage": "SDES national goods-flow data, 2019", "_files": list(FILES.values()), "rows": rows,
                "suppressed": suppressed, "suppressed_rows": suppressed_rows}
