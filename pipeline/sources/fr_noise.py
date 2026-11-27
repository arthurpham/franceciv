"""CEREMA strategic noise maps for major non-conceded transport infrastructure."""

import io
import json
import math
import posixpath
import re
import zipfile
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

import shapefile
from pyproj import Transformer
from shapely.geometry import shape as shapely_shape

from ..core.source import Source, SourceInfo

DATASET_API = "https://www.data.gouv.fr/api/1/datasets/cartes-de-bruit-strategiques-des-reseaux-routiers-et-ferroviaires-non-concedes-directive-europeenne-2002-49-ce/"
YEAR = 2022
GRID_M = 250
R_EARTH_M = 6378137.0
DEP_RE = re.compile(r"Département ([^ .]+)\.zip", re.IGNORECASE)
KINDS = {"road": (0, "_R_A_LD_S_"), "rail": (1, "_F_A_LD_S_")}


def normalize_dep(value):
    value = value.upper()
    if value in {"02A", "02B"}:
        return value[-2:]
    if value.isdigit():
        return value if value.startswith("97") else str(int(value)).zfill(2)
    return value


def lonlat_from_mercator(x, y):
    lon = math.degrees(x / R_EARTH_M)
    lat = math.degrees(2 * math.atan(math.exp(y / R_EARTH_M)) - math.pi / 2)
    return lon, lat


def shape_base(zf, token):
    matches = [
        name[:-4] for name in zf.namelist()
        if name.upper().endswith(".SHP") and token in posixpath.basename(name).upper()
    ]
    return matches[0] if matches else None


def read_shape_entries(zf, base, kind_index, aggregate, stats):
    reader = shapefile.Reader(
        shp=io.BytesIO(zf.read(base + ".shp")),
        shx=io.BytesIO(zf.read(base + ".shx")),
        dbf=io.BytesIO(zf.read(base + ".dbf")),
    )
    prj = zf.read(base + ".prj").decode("utf-8", "replace")
    transformer = Transformer.from_crs(prj, "EPSG:4326", always_xy=True)
    for item in reader.iterShapeRecords():
        try:
            level = int(str(item.record["LEGENDE"]).strip())
            geom = shapely_shape(item.shape.__geo_interface__)
        except Exception:
            stats["skipped"] += 1
            continue
        if geom.is_empty or not geom.area:
            stats["skipped"] += 1
            continue
        centroid = geom.centroid
        lon, lat = transformer.transform(centroid.x, centroid.y)
        # Department shapefiles use local metre projections (Lambert-93 in metropolitan
        # France and local UTM projections overseas), whose area distortion is small.
        area_m2 = geom.area
        key = (kind_index, math.floor(centroid.x / GRID_M), math.floor(centroid.y / GRID_M))
        aggregate[key]["total"] += area_m2
        if level >= 65:
            aggregate[key]["high"] += area_m2
        stats["polygons"] += 1
        stats["area_m2"] += area_m2
    return transformer


def process_department(job):
    dep, path = job
    aggregate = defaultdict(lambda: defaultdict(float))
    stats = {"polygons": 0, "area_m2": 0.0, "binned_area_m2": 0.0, "skipped": 0}
    missing = []
    with zipfile.ZipFile(path) as zf:
        for kind, (kind_index, token) in KINDS.items():
            base = shape_base(zf, token)
            if base is None:
                missing.append(kind)
                continue
            transformer = read_shape_entries(zf, base, kind_index, aggregate, stats)
    entries = []
    for (kind, gx, gy), row in sorted(aggregate.items()):
        lon, lat = transformer.transform((gx + 0.5) * GRID_M, (gy + 0.5) * GRID_M)
        # Noise polygons from parallel/intersecting infrastructure may overlap. At the
        # 250 m aggregation scale, cap overlap rather than counting the same land twice.
        total = min(row["total"], float(GRID_M * GRID_M))
        high = min(row["high"], total)
        stats["binned_area_m2"] += total
        entries.append([kind, round(total, 1), round(high, 1), round(lon, 5), round(lat, 5)])
    return dep, entries, stats, missing


class FrenchNoise(Source):
    info = SourceInfo(
        id="fr_noise",
        title="Strategic noise maps for major transport infrastructure",
        publisher="CEREMA / Ministry for the Ecological Transition",
        homepage="https://www.data.gouv.fr/datasets/cartes-de-bruit-strategiques-des-reseaux-routiers-et-ferroviaires-non-concedes-directive-europeenne-2002-49-ce",
        license="Licence Ouverte 2.0",
        description="2022 strategic noise-map polygons (type A, Lden) for qualifying non-conceded roads and railways. Polygon areas are aggregated into 250 m local-projection bins by centroid, with overlapping infrastructure contributions capped at bin area. The dataset does not include Paris, Hauts-de-Seine, Seine-Saint-Denis or Val-de-Marne and does not represent urban-agglomeration, airport, industrial or concessionaire-network noise.",
        used_for=["Major-road and major-rail noise-exposure lenses"],
    )

    def fetch(self, force=False):
        metadata_path = self.download(DATASET_API, "dataset.json", force=force)
        metadata = json.load(open(metadata_path, encoding="utf-8"))
        jobs = []
        for resource in metadata.get("resources", []):
            match = DEP_RE.search(resource.get("title") or "")
            if match and resource.get("url"):
                dep = normalize_dep(match.group(1))
                jobs.append((resource["url"], f"cbs_{dep}.zip"))
        if len(jobs) < 90:
            raise ValueError(f"unexpected CEREMA noise resource coverage: {len(jobs)} departments")
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda job: self.download(job[0], job[1], force=force, expect_binary=True), jobs))

    def process(self):
        metadata = json.load(open(self.raw_dir / "dataset.json", encoding="utf-8"))
        deps = []
        for resource in metadata.get("resources", []):
            match = DEP_RE.search(resource.get("title") or "")
            if match:
                deps.append(normalize_dep(match.group(1)))
        jobs = [(dep, str(self.raw_dir / f"cbs_{dep}.zip")) for dep in sorted(set(deps))]
        cells = {}
        totals = {"polygons": 0, "area_m2": 0.0, "binned_area_m2": 0.0, "skipped": 0}
        missing_parts = {}
        with ProcessPoolExecutor(max_workers=4) as pool:
            for dep, entries, stats, missing in pool.map(process_department, jobs, chunksize=1):
                cells[dep] = entries
                for key in totals:
                    totals[key] += stats[key]
                if missing:
                    missing_parts[dep] = missing
        if len(cells) < 90 or totals["polygons"] < 200_000 or totals["area_m2"] < 1_000_000_000:
            raise ValueError(f"unexpected strategic-noise coverage: {len(cells)} departments, {totals}")
        return {
            "vintage": f"CEREMA strategic noise maps, {YEAR}",
            "_files": ["dataset.json"] + [f"cbs_{dep}.zip" for dep in sorted(cells)],
            "year": YEAR,
            "grid_m": GRID_M,
            "crs": "EPSG:4326 bin centroids; kind 0=road, 1=rail; entries are [kind, Lden≥55 area m², Lden≥65 area m², longitude, latitude]",
            "departments": sorted(cells),
            "missing_departments": ["75", "92", "93", "94"],
            "missing_parts": missing_parts,
            "polygon_count": totals["polygons"],
            "area_km2": round(totals["binned_area_m2"] / 1e6, 2),
            "source_polygon_area_km2": round(totals["area_m2"] / 1e6, 2),
            "skipped_polygons": totals["skipped"],
            "cells": cells,
        }
