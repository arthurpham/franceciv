"""Physical river-flood exposure from the official TRI/Géorisques WMS."""

import io
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

from ..core.source import Source, SourceInfo

SERVICE = "https://georisques.gouv.fr/services/di_fxx_2020"
LAYERS = {
    "river_overflow": ("ALEA_SYNT_01_04FAI_FXX", "overflow"),
    "coastal_submersion": ("ALEA_SYNT_03_04FAI_FXX", "submersion"),
}  # rare/millennial scenarios

# Same geographic raster registration as the CORINE grid used by the builders.
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
ALPHA_THRESHOLD = 128


def tile_bounds(row, col):
    # X0/Y0 are the first output-cell centers; WMS bounds are raster edges.
    west = X0 - DX / 2
    north = Y0 - DY / 2
    lon0 = west + col * TILE_CELLS * DX
    lon1 = lon0 + TILE_CELLS * DX
    lat1 = north + row * TILE_CELLS * DY
    lat0 = lat1 + TILE_CELLS * DY
    return lon0, lat0, lon1, lat1


def tile_url(key, row, col):
    lon0, lat0, lon1, lat1 = tile_bounds(row, col)
    layer = LAYERS[key][0]
    q = {
        "service": "WMS", "request": "GetMap", "version": "1.3.0",
        "layers": layer, "styles": "inspire_common:DEFAULT", "crs": "EPSG:4326",
        "bbox": f"{lat0},{lon0},{lat1},{lon1}", "width": str(TILE_WIDTH), "height": str(TILE_HEIGHT),
        "format": "image/png", "transparent": "true",
    }
    return SERVICE + "?" + urllib.parse.urlencode(q)


def tile_name(key, row, col):
    return f"{LAYERS[key][1]}_r{row}_c{col}.png"


class FrenchFlood(Source):
    info = SourceInfo(
        id="fr_flood",
        title="TRI physical river-flood exposure",
        publisher="Géorisques / BRGM / DGPR",
        homepage="https://www.georisques.gouv.fr/dossiers/territoires-a-risque-dinondation-tri",
        license="Licence Ouverte 2.0",
        description="Raster tiles from the official 2020 TRI synthesis WMS for rare or millennial river-overflow flooding and marine submersion. "
        "The pipeline downsamples them to the CORINE raster registration as approximate flood-area fractions. TRI coverage is limited to designated flood-risk territories.",
        used_for=["Physical river-flood and coastal-submersion exposure lenses"],
    )

    def fetch(self, force=False):
        jobs = [(key, row, col) for key in LAYERS for row in range(TILES) for col in range(TILES)]
        # Tiny independent WMS tiles; the shared manifest is protected by fetch.MANIFEST_LOCK.
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
                    flooded = np.where(alpha >= ALPHA_THRESHOLD, 255, 0).astype(np.uint8)
                    # BOX averaging preserves the fraction of each coarse cell covered by the high-resolution raster.
                    small = Image.fromarray(flooded).resize((TILE_CELLS, TILE_CELLS), Image.Resampling.BOX)
                    strips.append(np.asarray(small, dtype=np.uint8))
                arr = np.concatenate(strips, axis=1)
                for line in arr:
                    rows.append("".join(str(min(9, round((v / 255) * 9))) if v else "." for v in line))
            layers[key] = rows
        return {
            "vintage": "TRI flood-risk synthesis, 2020 reporting",
            "_files": used,
            "crs": "EPSG:4326", "x0": X0, "dx": DX, "y0": Y0, "dy": DY,
            "cols": COLS, "rows_n": ROWS, "layers": layers,
        }
