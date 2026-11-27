"""Géorisques/BRGM natural-risk zoning rasters sampled from the official WMS."""

import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

from ..core.source import Source, SourceInfo

SERVICE = "https://georisques.gouv.fr/services"
STYLE = "inspire_common:DEFAULT"

# Same geographic raster registration as the CORINE/flood grids used by the builders.
X0 = -5.39745
DX = 0.0051
Y0 = 51.19833333333334
DY = -0.0033333333333333335
COLS = 3000
ROWS = 3000
TILES = 10
TILE_CELLS = COLS // TILES
TILE_WIDTH = 1600
TILE_HEIGHT = 1200
ALPHA_THRESHOLD = 100

LAYERS = {
    "clay": {
        "layer": "ALEARG",
        "title": "Retrait-gonflement des argiles",
        # faible, moyenne, forte — sampled from the official WMS legend.
        "palette": [(253, 253, 151), (253, 163, 0), (253, 0, 0)],
        "max_class": 3,
    },
    "seismic": {
        "layer": "risq_zonage_sismique",
        "title": "Zonage sismique",
        # zones 1..5 — très faible to forte.
        "palette": [(213, 213, 213), (253, 208, 49), (253, 126, 0), (222, 42, 22), (130, 4, 4)],
        "max_class": 5,
    },
    "radon": {
        "layer": "RADON",
        "title": "Potentiel radon",
        # faible, modéré, fort — commune potential classes.
        "palette": [(195, 239, 183), (225, 193, 101), (219, 113, 85)],
        "max_class": 3,
    },
}


def tile_bounds(row, col):
    west = X0 - DX / 2
    north = Y0 - DY / 2
    lon0 = west + col * TILE_CELLS * DX
    lon1 = lon0 + TILE_CELLS * DX
    lat1 = north + row * TILE_CELLS * DY
    lat0 = lat1 + TILE_CELLS * DY
    return lon0, lat0, lon1, lat1


def tile_url(key, row, col):
    lon0, lat0, lon1, lat1 = tile_bounds(row, col)
    spec = LAYERS[key]
    q = {
        "service": "WMS", "request": "GetMap", "version": "1.3.0",
        "layers": spec["layer"], "styles": STYLE, "crs": "EPSG:4326",
        "bbox": f"{lat0},{lon0},{lat1},{lon1}", "width": str(TILE_WIDTH), "height": str(TILE_HEIGHT),
        "format": "image/png", "transparent": "true",
    }
    return SERVICE + "?" + urllib.parse.urlencode(q)


def tile_name(key, row, col):
    return f"{key}_r{row}_c{col}.png"


def classify_tile(path, spec):
    im = Image.open(path).convert("RGBA")
    arr = np.asarray(im, dtype=np.uint8)
    alpha = arr[:, :, 3]
    rgb = arr[:, :, :3]
    # Exact legend fills only. This deliberately ignores thin anti-aliased commune boundaries
    # instead of nearest-classifying dark boundary pixels into a hazard class.
    cls = np.zeros(alpha.shape, dtype=np.uint8)
    for idx, color in enumerate(spec["palette"], start=1):
        match = np.all(rgb == np.asarray(color, dtype=np.uint8), axis=2) & (alpha >= ALPHA_THRESHOLD)
        cls[match] = idx
    max_class = spec["max_class"]
    weight = (cls * (255 // max_class)).astype(np.uint8)
    valid = np.where(cls > 0, 255, 0).astype(np.uint8)
    # BOX-average weight and valid-fill fraction separately, then take the conditional mean.
    # Thin boundary strokes hidden by the WMS style therefore neither count as hazard nor
    # punch artificial zero holes through polygon interiors.
    small_weight = np.asarray(Image.fromarray(weight).resize((TILE_CELLS, TILE_CELLS), Image.Resampling.BOX), dtype=np.float32)
    small_valid = np.asarray(Image.fromarray(valid).resize((TILE_CELLS, TILE_CELLS), Image.Resampling.BOX), dtype=np.float32)
    out = np.zeros_like(small_weight, dtype=np.float32)
    np.divide(small_weight * 255, small_valid, out=out, where=small_valid > 0)
    return out.astype(np.uint8)


class FrenchRiskZones(Source):
    info = SourceInfo(
        id="fr_risk_zones",
        title="Géorisques natural-risk zoning rasters",
        publisher="BRGM / Géorisques / DGPR",
        homepage="https://www.georisques.gouv.fr/",
        license="Licence Ouverte 2.0",
        description="WMS raster samples of official French clay shrink-swell exposure, seismic zoning and commune radon potential. "
        "The pipeline classifies pixels against the published legend colours and downsamples them to the CORINE raster registration. "
        "Clay and seismic layers are spatial hazard zones; radon is a commune-level potential class.",
        used_for=["Clay shrink-swell, seismic and radon risk lenses"],
    )

    def fetch(self, force=False):
        jobs = [(key, row, col) for key in LAYERS for row in range(TILES) for col in range(TILES)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda job: self.download(tile_url(*job), tile_name(*job), force=force, expect_binary=True), jobs))

    def process(self):
        layers = {}
        files = []
        for key, spec in LAYERS.items():
            rows = []
            for row in range(TILES):
                strips = []
                for col in range(TILES):
                    fn = tile_name(key, row, col)
                    path = self.raw_dir / fn
                    if not path.exists():
                        raise FileNotFoundError(path)
                    files.append(fn)
                    strips.append(classify_tile(path, spec))
                arr = np.concatenate(strips, axis=1)
                for line in arr:
                    rows.append("".join(str(min(9, round((v / 255) * 9))) if v else "." for v in line))
            layers[key] = {"rows": rows, "max_class": spec["max_class"], "title": spec["title"]}
        return {
            "vintage": "Géorisques/BRGM risk zoning, current WMS publication",
            "_files": files,
            "crs": "EPSG:4326", "x0": X0, "dx": DX, "y0": Y0, "dy": DY,
            "cols": COLS, "rows_n": ROWS, "layers": layers,
        }
