"""CORINE Land Cover 2018 for metropolitan France, read as tiled WMS rasters."""

from __future__ import annotations

import io
from PIL import Image

from ..core.source import Source, SourceInfo

YEAR = 2018
LAYER = "LANDCOVER.CLC18_FR"
LAT0, LAT1 = 41.2, 51.2
LON0, LON1 = -5.4, 9.9
TILES = 3
PX = 1000
URL = (
    "https://data.geopf.fr/wms-r/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap"
    f"&LAYERS={LAYER}&STYLES=&CRS=EPSG:4326&BBOX={{s}},{{w}},{{n}},{{e}}"
    f"&WIDTH={PX}&HEIGHT={PX}&FORMAT=image/png"
)
# CORINE level-3 colour -> NLCD-like renderer class. Vineyard/orchard detail is retained in `clc_rows`.
COLOR_TO_NLCD = {
    (230,0,77):24,(255,0,0):22,(204,77,242):23,(204,0,0):23,(230,204,204):23,(230,204,230):23,
    (166,0,204):31,(166,77,0):23,(255,77,255):23,(255,166,255):21,(255,230,255):21,
    (255,255,168):82,(255,255,0):82,(230,230,0):82,(230,128,0):82,(242,166,77):82,(230,166,0):82,
    (230,230,77):81,(255,230,166):82,(255,230,77):81,(230,204,77):81,(242,204,166):81,
    (128,255,0):41,(0,166,0):42,(77,255,0):43,(204,242,77):71,(166,255,128):52,(166,230,77):52,
    (166,242,0):52,(230,230,230):31,(204,204,204):31,(204,255,204):71,(0,0,0):52,(166,230,204):12,
    (166,166,255):95,(77,77,255):95,(204,204,255):95,(230,230,255):95,(166,166,230):95,
    (0,204,242):11,(128,242,230):11,(0,255,166):11,(230,242,255):11,(230,242,255):11,
}
COLOR_TO_NLCD[(230,242,255)] = 11
COLOR_TO_NLCD[(230,128,0)] = 82
NLCD_CHAR = {0:'.',11:'w',12:'i',21:'o',22:'l',23:'m',24:'h',31:'b',41:'d',42:'e',43:'x',52:'s',71:'g',81:'p',82:'c',90:'f',95:'v'}
PALETTE = list(COLOR_TO_NLCD)


def nearest(rgb):
    r,g,b=rgb[:3]
    return min(PALETTE,key=lambda p:(r-p[0])**2+(g-p[1])**2+(b-p[2])**2)


class FrenchCorine(Source):
    info = SourceInfo(
        id="fr_corine",
        title=f"CORINE Land Cover {YEAR}, metropolitan France",
        publisher="SDES / Copernicus, served by IGN Géoplateforme",
        homepage="https://www.statistiques.developpement-durable.gouv.fr/corine-land-cover-0",
        license="Licence Ouverte 2.0",
        description="French land cover in 44 detailed classes, read through the IGN WMS at roughly 380 m resolution and translated into the renderer's biome classes.",
        used_for=["Hex land cover", "Forest, farmland, developed and vineyard shares"],
    )

    def fetch(self, force=False):
        dla=(LAT1-LAT0)/TILES; dlo=(LON1-LON0)/TILES
        for iy in range(TILES):
            for ix in range(TILES):
                w=LON0+ix*dlo; e=w+dlo; s=LAT1-(iy+1)*dla; n=s+dla
                self.download(URL.format(s=round(s,6),w=round(w,6),n=round(n,6),e=round(e,6)),f"clc_{iy}_{ix}.png",force=force,expect_binary=True)

    def process(self):
        rows=[]
        crop_details=[]
        dla=(LAT1-LAT0)/TILES; dlo=(LON1-LON0)/TILES
        files=[]
        for iy in range(TILES):
            strips=[]
            for ix in range(TILES):
                fn=f"clc_{iy}_{ix}.png"; files.append(fn)
                im=Image.open(self.raw_dir/fn).convert('RGBA').resize((PX,PX))
                strips.append(im)
            for y in range(PX):
                chars=[]
                detail_chars=[]
                for im in strips:
                    pix=im.load()
                    for x in range(PX):
                        rgba=pix[x,y]
                        near = nearest(rgba)
                        chars.append(NLCD_CHAR[COLOR_TO_NLCD[near]] if rgba[3] >= 128 else ".")
                        detail_chars.append("v" if rgba[3] >= 128 and near == (230,128,0) else "o" if rgba[3] >= 128 and near in {(242,166,77), (230,166,0)} else ".")
                rows.append(''.join(chars))
                crop_details.append(''.join(detail_chars))
        width=TILES*PX
        return {"vintage":f"CORINE Land Cover {YEAR}, WMS raster ~380 m","_files":files,"crs":"EPSG:4326",
                "x0":LON0+dlo/PX/2,"dx":dlo/PX,"y0":LAT1-dla/PX/2,"dy":-dla/PX,"cols":width,"rows_n":len(rows),
                "legend":{ch:code for code,ch in NLCD_CHAR.items()},"classes":{},"rows":rows,"crop_detail_rows":crop_details}
