"""INSEE 2023 census and territory-comparator statistics used by the French map.

The Melodi endpoint publishes one zipped CSV per census table. Rows are long-form
SDMX-style observations; this source keeps the geographic levels the pipeline uses
and stores each observation under a compact dimension key for builders to interpret.
"""

from __future__ import annotations

import csv
import hashlib
import io
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from ..core.fetch import _download_with, _request
from ..core.source import Source, SourceInfo

YEAR = "2023"
MELODI = "https://api.insee.fr/melodi/file/{ds}/{ds}_" + YEAR + "_CSV_FR"
LEVELS = ("EPCI", "AAV2020", "DEP", "REG", "FRANCE")
LICENSE = "Licence Ouverte 2.0"
PUBLISHER = "Insee"

DATASETS = {
    "employment": {
        "ds": "DS_RP_TD_EMPLOI_LT_EMPFORMACTIVITY_COMP",
        "title": "Workplace employment by economic activity (census 2023)",
        "used": ["City Food/Production/Science/Culture yields", "Employment-weighted GDP allocation"],
    },
    "workforce": {
        "ds": "DS_RP_EMPLOI_LR_COMP",
        "title": "Resident labour force by socio-professional category (census 2023)",
        "used": ["City View citizen workforce mix"],
    },
    "activity": {
        "ds": "DS_RP_EMPLOI_LR_PRINC",
        "title": "Labour force and unemployment (census 2023)",
        "used": ["Unemployment rates"],
    },
    "education": {
        "ds": "DS_RP_DIPLOMES_PRINC",
        "title": "Highest diploma (census 2023)",
        "used": ["Higher-education lens and city statistics"],
    },
    "population_age": {
        "ds": "DS_RP_POPULATION_PRINC",
        "title": "Population by age (census 2023)",
        "used": ["Median-age and senior lenses"],
    },
    "commuting": {
        "ds": "DS_RP_NAVETTES_PRINC",
        "title": "Home-to-work transport mode (census 2023)",
        "used": ["Car and public-transport lenses"],
    },
    "immigration": {
        "ds": "DS_RP_TD_IMMI_AGESEXEMPSTA_PRINC",
        "title": "Population by immigration status (census 2023)",
        "used": ["Immigration lens and city statistics"],
    },
}
COMPARATOR_URL = "https://www.insee.fr/fr/statistiques/fichier/2521169/comparateur_csv.zip"
COMPARATOR_FILE = "comparateur_csv.zip"
COMPARATOR_MEASURES = {
    "POP": "POP", "SUP": "SUP", "MED_SL": "MED_SL", "PR_MD60": "PR_MD60",
    "DWELLINGS": "LOG", "DWELLINGS_OCS_DW_MAIN": "RP", "DWELLINGS_OCS_DW_MAIN_TSH_100": "RP_PROP",
    "DWELLINGS_OCS_DW_SEC_DW_OCC": "RSEC", "DWELLINGS_OCS_DW_VAC": "LVAC",
    "LVB": "NAIS", "DTH": "DECES", "POP_AGE_Y15T64": "POP15_64", "UNIT_LOC": "ETAB",
}
SKIP_DIMS = {"GEO", "GEO_OBJECT", "FREQ", "OBS_STATUS", "TIME_PERIOD", "OBS_VALUE", "RP_MEASURE", "DS", "TAB_MEASURE",
             "UNIT_MEASURE", "UNIT_MULT", "CONF_STATUS", "GEO_REF"}


def resumable_download(source, url, rel_path, force=False):
    """Download a large Melodi zip with HTTP range resumes inside one cache attempt.

    api.insee.fr trickles large generated zips slowly enough that a fresh 10-minute
    download can be cut off. Unlike the normal helper, partial bytes are kept while
    retrying inside the attempt; the cache is still written only after a complete body.
    """
    def attempt(tmp: Path):
        if tmp.exists() and force:
            tmp.unlink()
        for _ in range(80):
            have = tmp.stat().st_size if tmp.exists() else 0
            headers = {"Range": f"bytes={have}-"} if have else {}
            try:
                req = _request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=45) as resp:
                    if have and resp.status != 206:
                        tmp.unlink(missing_ok=True)
                        have = 0
                    mode = "ab" if have else "wb"
                    with open(tmp, mode) as out:
                        while chunk := resp.read(1 << 20):
                            out.write(chunk)
                cr = resp.headers.get("Content-Range")
                total = int(cr.rsplit("/", 1)[1]) if cr and "/" in cr and cr.rsplit("/", 1)[1].isdigit() else None
                if total is not None and tmp.stat().st_size != total:
                    continue
                break
            except (urllib.error.URLError, TimeoutError, ConnectionError, EOFError):
                continue
        else:
            raise ConnectionError(f"could not complete resumable download: {url}")
        if not zipfile.is_zipfile(tmp):
            raise ConnectionError(f"incomplete or invalid zip downloaded from {url}")
        data = tmp.read_bytes()
        return hashlib.sha256(data).hexdigest(), len(data)

    return _download_with(source.id, url, rel_path, attempt, force=force,
                          extra={"derived": "HTTP range-resumable download of a generated zip"})


def csv_rows(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv") and "metadata" not in n.lower())
        with z.open(name) as f:
            yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"), delimiter=";")


def dim_key(row):
    parts = []
    for k, v in row.items():
        if k in SKIP_DIMS or v in (None, "", "_T"):
            continue
        parts.append(f"{k}={v}")
    return "|".join(parts) or "_T"


def compact_melodi(path, levels=LEVELS, key_mode="dims"):
    out = {lv: {} for lv in levels}
    for r in csv_rows(path):
        lv = r.get("GEO_OBJECT")
        if lv not in out or r.get("TIME_PERIOD") != YEAR or r.get("OBS_VALUE") in (None, "", "NA"):
            continue
        if key_mode == "employment":
            if r.get("SEX") != "_T" or r.get("EMPFORM") != "_T":
                continue
            key = r.get("EMP_ACTIVITY")
        else:
            key = dim_key(r)
        try:
            value = round(float(r["OBS_VALUE"]), 2)
        except ValueError:
            continue
        out[lv].setdefault(r["GEO"], {})[key] = value
    return {lv: g for lv, g in out.items() if g}


def compact_comparator(path):
    out = {lv: {} for lv in LEVELS + ("COM",)}
    geo_ref = None
    for r in csv_rows(path):
        lv = r.get("GEO_OBJECT")
        if lv not in out or r.get("OBS_VALUE") in (None, "", "NA"):
            continue
        key = COMPARATOR_MEASURES.get(r.get("TAB_MEASURE"))
        if key is None:
            continue
        geo_ref = geo_ref or r.get("GEO_REF")
        try:
            value = float(r["OBS_VALUE"])
        except ValueError:
            continue
        value = int(value) if value.is_integer() else round(value, 2)
        out[lv].setdefault(r["GEO"], {})[f"{key}_{r['TIME_PERIOD']}"] = value
    return geo_ref, {lv: g for lv, g in out.items() if g}


class FrenchInseeStats(Source):
    info = SourceInfo(
        id="fr_insee_stats",
        title="INSEE census and territory-comparator statistics",
        publisher=PUBLISHER,
        homepage="https://catalogue-donnees.insee.fr/",
        license=LICENSE,
        description="Recensement de la population 2023 tables from the Melodi catalogue, plus the comparateur de "
        "territoires population, income, poverty and housing series. Geographic levels include communes, EPCI, AAV, "
        "departments, regions and France depending on the table.",
        used_for=["City employment yields", "Citizen workforce mix", "Unemployment", "Education", "Age", "Commuting", "Immigration",
                  "Population growth", "Income, poverty and housing lenses"],
    )

    def fetch(self, force=False):
        for spec in DATASETS.values():
            ds = spec["ds"]
            resumable_download(self, MELODI.format(ds=ds), f"{ds}.zip", force=force)
        self.download(COMPARATOR_URL, COMPARATOR_FILE, force=force, expect_binary=True)

    def process(self):
        datasets = {}
        files = []
        for key, spec in DATASETS.items():
            fn = f"{spec['ds']}.zip"
            if not (self.raw_dir / fn).exists():
                print(f"    ! {key}: raw file unavailable; continuing without it")
                datasets[key] = {}
                continue
            files.append(fn)
            mode = "employment" if key == "employment" else "dims"
            datasets[key] = compact_melodi(self.raw_dir / fn, levels=LEVELS + (("COM",) if key == "employment" else ()), key_mode=mode)
            print(f"    {key}: " + ", ".join(f"{lv} {len(g)}" for lv, g in datasets[key].items()))
        geo_ref, comp = compact_comparator(self.raw_dir / COMPARATOR_FILE)
        files.append(COMPARATOR_FILE)
        print("    comparateur: " + ", ".join(f"{lv} {len(g)}" for lv, g in comp.items()))
        return {
            "vintage": f"INSEE census {YEAR} and comparateur de territoires, geography {geo_ref}",
            "_files": files,
            "year": int(YEAR),
            "datasets": datasets,
            "comparateur": comp,
        }
