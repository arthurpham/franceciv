"""Géorisques risk-prevention perimeter rasters sampled from the official WMS."""

import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

from ..core.source import Source, SourceInfo
from .fr_flood import COLS, ROWS, TILE_CELLS, TILE_HEIGHT, TILE_WIDTH, TILES, X0, DX, Y0, DY, tile_bounds

SERVICE = "https://georisques.gouv.fr/services"
LAYERS = {
    "forest_fire": ("SUP_FEU", "fire"),
    "avalanche": ("SUP_AVALANCHE", "avalanche"),
    "ground_movement": ("SUP_MVT_TERRAIN", "movement"),
    "industrial": ("SUP_INDUS", "industrial"),
}
ALPHA_THRESHOLD = 50


def tile_url(key, row, col):
    lon0, lat0, lon1, lat1 = tile_bounds(row, col)
    q = {
        "service": "WMS", "request": "GetMap", "version": "1.3.0",
        "layers": LAYERS[key][0], "styles": "default", "crs": "EPSG:4326",
        "bbox": f"{lat0},{lon0},{lat1},{lon1}", "width": str(TILE_WIDTH), "height": str(TILE_HEIGHT),
        "format": "image/png", "transparent": "true",
    }
    return SERVICE + "?" + urllib.parse.urlencode(q)


def tile_name(key, row, col):
    return f"{LAYERS[key][1]}_r{row}_c{col}.png"


class FrenchRiskPerimeters(Source):
    info = SourceInfo(
        id="fr_risk_perimeters",
        title="Géorisques risk-prevention perimeters",
        publisher="Géorisques / DGPR",
        homepage="https://www.georisques.gouv.fr/",
        license="Licence Ouverte 2.0",
        description="WMS raster samples of official French risk-prevention servitude perimeters for forest fire, avalanche, ground movement and industrial risk. "
        "The pipeline downsamples filled polygon coverage to the CORINE raster registration. These are administrative prevention perimeters, "
        "not probabilistic hazard intensity, damage or loss models.",
        used_for=["Forest-fire, avalanche, ground-movement and industrial-risk prevention-perimeter lenses"],
    )

    def fetch(self, force=False):
        jobs = [(key, row, col) for key in LAYERS for row in range(TILES) for col in range(TILES)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda job: self.download(tile_url(*job), tile_name(*job), force=force, expect_binary=True), jobs))

    def process(self):
        layers = {}
        used = []
        for key in LAYERS:
            rows = []
            for row in range(TILES):
                strips = []
                for col in range(TILES):
                    fn = tile_name(key, row, col)
                    path = self.raw_dir / fn
                    if not path.exists():
                        raise FileNotFoundError(path)
                    used.append(fn)
                    im = Image.open(path).convert("RGBA")
                    alpha = np.asarray(im.getchannel("A"), dtype=np.uint8)
                    covered = np.where(alpha >= ALPHA_THRESHOLD, 255, 0).astype(np.uint8)
                    small = Image.fromarray(covered).resize((TILE_CELLS, TILE_CELLS), Image.Resampling.BOX)
                    strips.append(np.asarray(small, dtype=np.uint8))
                arr = np.concatenate(strips, axis=1)
                for line in arr:
                    rows.append("".join(str(min(9, round((v / 255) * 9))) if v else "." for v in line))
            layers[key] = rows
        return {
            "vintage": "Géorisques risk-prevention perimeters, current WMS publication",
            "_files": used,
            "crs": "EPSG:4326", "x0": X0, "dx": DX, "y0": Y0, "dy": DY,
            "cols": COLS, "rows_n": ROWS, "layers": layers,
        }
