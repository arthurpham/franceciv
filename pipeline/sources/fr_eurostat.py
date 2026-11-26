"""Eurostat regional GDP, gross value added and employment for France (NUTS 3)."""

from __future__ import annotations

import json

from ..core.source import Source, SourceInfo

YEAR = 2023
API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
DATASETS = {
    "gdp": "nama_10r_3gdp",
    "gva": "nama_10r_3gva",
    "employment": "nama_10r_3empers",
}


def fetch_dataset(source, key, force=False):
    ds = DATASETS[key]
    url = f"{API}/{ds}?format=JSON&lang=en&time={YEAR}"
    return source.download(url, f"{ds}_{YEAR}.json", force=force)


def jsonstat_rows(path):
    d = json.load(open(path, encoding="utf-8"))
    ids, sizes = d["id"], d["size"]
    categories = []
    for dim in ids:
        idx = d["dimension"][dim]["category"]["index"]
        categories.append(sorted(idx, key=idx.get))
    for flat, value in d.get("value", {}).items():
        rem, pos = int(flat), []
        for size in reversed(sizes):
            pos.append(rem % size)
            rem //= size
        pos.reverse()
        row = {dim: categories[k][p] for k, (dim, p) in enumerate(zip(ids, pos))}
        row["value"] = value
        yield row


class FrenchEurostat(Source):
    info = SourceInfo(
        id="fr_eurostat",
        title=f"Eurostat regional accounts, {YEAR}",
        publisher="Eurostat",
        homepage="https://ec.europa.eu/eurostat/web/regions/database",
        license="Eurostat free reuse policy",
        description="GDP, gross value added and employment by NUTS 3 region and high-level NACE industry. "
        "NUTS 3 units correspond to French departments, with Eurostat rather than INSEE codes.",
        used_for=["Gold yield (GDP)", "GDP by industry", "Employment by industry", "Regional economy panels"],
    )

    def fetch(self, force=False):
        for key in DATASETS:
            fetch_dataset(self, key, force=force)

    def process(self):
        out = {"vintage": f"Eurostat regional accounts, {YEAR}", "_files": [f"{d}_{YEAR}.json" for d in DATASETS.values()]}
        for key, ds in DATASETS.items():
            rows = list(jsonstat_rows(self.raw_dir / f"{ds}_{YEAR}.json"))
            labels = json.load(open(self.raw_dir / f"{ds}_{YEAR}.json", encoding="utf-8"))["dimension"]["geo"]["category"]["label"]
            out[key] = rows
            out[key + "_labels"] = labels
        return out
