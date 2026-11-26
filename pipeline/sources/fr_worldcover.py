"""ESA WorldCover 2021 land cover over metropolitan France.

The published Cloud Optimized GeoTIFFs are 10 m data. Fetching keeps only a nearest-neighbour
~670 m class grid for the map window, which is the resolution actually used by the hex builder;
the manifest still records the exact source tile URLs. ESA classes are translated onto the
NLCD-like class ids the original renderer understands.
"""

from __future__ import annotations

import hashlib

import numpy as np
import rasterio
from rasterio.enums import Resampling

from ..core.fetch import _download_with
from ..core.source import Source, SourceInfo

VERSION = "v200"
YEAR = 2021
ROOT = f"https://esa-worldcover.s3.eu-central-1.amazonaws.com/{VERSION}/{YEAR}/map"
LONS = [-6, -3, 0, 3, 6, 9]
LATS = [39, 42, 45, 48, 51]  # lower-left corners, northward
TILE_PIXELS = 450  # 3° / 450 = 1/150° per pixel
STEP = 3.0 / TILE_PIXELS

# ESA WorldCover class -> the NLCD-like class id used by the original map art.
ESA_TO_NLCD = {
    0: 0,    # no data
    10: 41,  # tree cover → broadleaf forest (mixed forest detail is not available)
    20: 52,  # shrubland
    30: 71,  # grassland
    40: 82,  # cropland
    50: 23,  # built-up
    60: 31,  # bare/sparse vegetation
    70: 12,  # snow and ice
    80: 11,  # open water
    90: 95,  # herbaceous wetland
    95: 90,  # mangroves (not relevant in France)
    100: 71, # moss and lichen
}
# NLCD-like code → one character, matching nlcd.py's compact raster encoding.
LEGEND = {
    0: ".", 11: "w", 12: "i", 21: "o", 22: "l", 23: "m", 24: "h", 31: "b",
    41: "d", 42: "e", 43: "x", 52: "s", 71: "g", 81: "p", 82: "c", 90: "f", 95: "v",
}
CLASSES = {
    11: "Open water", 12: "Perennial ice/snow", 23: "Built-up", 31: "Bare/sparse vegetation",
    41: "Tree cover", 52: "Shrubland", 71: "Grassland, moss or lichen", 82: "Cropland",
    90: "Woody wetland/mangrove", 95: "Herbaceous wetland",
}


def tile_name(lat: int, lon: int) -> str:
    la = f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}"
    lo = f"{'E' if lon >= 0 else 'W'}{abs(lon):03d}"
    return f"{la}{lo}"


def tile_url(lat: int, lon: int) -> str:
    return f"{ROOT}/ESA_WorldCover_10m_{YEAR}_{VERSION}_{tile_name(lat, lon)}_Map.tif"


def write_coarse_tile(url: str, tmp) -> tuple[str, int]:
    """Write one nearest-neighbour downsampled tile as text rows; return sha256 and byte count."""
    with rasterio.open(url) as ds:
        arr = ds.read(1, out_shape=(TILE_PIXELS, TILE_PIXELS), resampling=Resampling.nearest)
    lookup = np.zeros(256, dtype=np.uint8)
    for esa, nlcd in ESA_TO_NLCD.items():
        lookup[esa] = nlcd
    arr = lookup[arr]
    text = "\n".join("".join(LEGEND[int(v)] for v in row) for row in arr) + "\n"
    data = text.encode("ascii")
    tmp.write_bytes(data)
    return hashlib.sha256(data).hexdigest(), len(data)


class FrenchWorldCover(Source):
    info = SourceInfo(
        id="fr_worldcover",
        title=f"ESA WorldCover 10 m {YEAR}",
        publisher="European Space Agency / ESA WorldCover consortium",
        homepage="https://worldcover2021.esa.int/",
        license="CC BY 4.0",
        description="Global 10 m land-cover tiles covering metropolitan France. The pipeline uses a nearest-neighbour "
        "reduced-resolution copy (about 670 m pixels) and translates the 11 ESA classes into the renderer's biome groups.",
        used_for=["Hex land cover (biomes)", "Forest / cropland / developed shares"],
    )

    def fetch(self, force=False):
        for lat in LATS:
            for lon in LONS:
                name = tile_name(lat, lon)
                _download_with(
                    self.id,
                    tile_url(lat, lon),
                    f"{name}.txt",
                    lambda tmp, url=tile_url(lat, lon): write_coarse_tile(url, tmp),
                    force=force,
                    note=f" (nearest-neighbour {TILE_PIXELS}×{TILE_PIXELS} subset)",
                    extra={"derived": f"nearest-neighbour reduced resolution, {TILE_PIXELS}×{TILE_PIXELS} pixels"},
                )

    def process(self):
        files = []
        tiles = {}
        for lat in LATS:
            for lon in LONS:
                name = tile_name(lat, lon)
                files.append(f"{name}.txt")
                rows = (self.raw_dir / f"{name}.txt").read_text("ascii").splitlines()
                if len(rows) != TILE_PIXELS or len({len(r) for r in rows}) != 1 or len(rows[0]) != TILE_PIXELS:
                    raise ValueError(f"unexpected coarse WorldCover tile shape in {name}")
                tiles[(lat, lon)] = rows

        width = len(LONS) * TILE_PIXELS
        rows_out = []
        # Rows are north-to-south. LATS are lower corners ascending, so compose them in reverse.
        for lat in sorted(LATS, reverse=True):
            for row_in_tile in range(TILE_PIXELS):
                rows_out.append("".join(tiles[(lat, lon)][row_in_tile] for lon in sorted(LONS)))
        return {
            "vintage": f"ESA WorldCover {YEAR} {VERSION}, reduced to ~670 m",
            "_files": files,
            "crs": "EPSG:4326",
            # Pixel centre of column 0 / row 0 and pixel size in degrees; dy is negative.
            "x0": min(LONS) + STEP / 2,
            "dx": STEP,
            "y0": max(LATS) + 3 - STEP / 2,
            "dy": -STEP,
            "cols": width,
            "rows_n": len(rows_out),
            "legend": {ch: code for code, ch in LEGEND.items()},
            "classes": CLASSES,
            "rows": rows_out,
        }
