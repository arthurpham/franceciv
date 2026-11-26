import csv

from ..core.insets import PARAMS, real_inverse_bounds
from ..core.source import Source, SourceInfo

# ETOPO1 (1 arc-minute) via NOAA ERDDAP, sampled every 2nd point (~4 km). The window covers the
# whole map rectangle (metropolitan France plus the margins into neighbouring countries and seas).
STRIDE = 2
LAT, LON = (39, 53), (-8, 13)
BOXES = {"metro": ((*LAT, *LON))}
BOXES.update({dep: tuple(round(v, 2) for v in (lambda b: (b[1], b[3], b[0], b[2]))(real_inverse_bounds(spec))) for dep, spec in PARAMS.items()})


def url_for(box):
    lat0, lat1, lon0, lon1 = box
    return (
        "https://coastwatch.pfeg.noaa.gov/erddap/griddap/etopo180.csv"
        f"?altitude%5B({lat0}):{STRIDE}:({lat1})%5D%5B({lon0}):{STRIDE}:({lon1})%5D"
    )


def filename(key, box):
    lat0, lat1, lon0, lon1 = box
    return f"etopo_{key}_lat{lat0}_{lat1}_lon{lon0}_{lon1}_stride{STRIDE}.csv"


class Etopo(Source):
    info = SourceInfo(
        id="etopo",
        title="ETOPO1 global relief model",
        publisher="NOAA National Centers for Environmental Information (via ERDDAP)",
        homepage="https://www.ncei.noaa.gov/products/etopo-global-relief-model",
        license="Public domain (U.S. Government work)",
        description="Land elevation and ocean depth, sampled every ~4 km. Each hex's relief (flat, hills, mountains, "
        "peaks) comes from the mean and roughness (standard deviation) of the land samples inside it.",
        used_for=["Relief (hills, mountains)", "Hill-shading", "Ocean depth"],
    )

    def fetch(self, force=False):
        for key, box in BOXES.items():
            self.download(url_for(box), filename(key, box), force=force)

    def process(self):
        lat, lon, alt = [], [], []
        files = []
        for key, box in BOXES.items():
            fn = filename(key, box)
            files.append(fn)
            with open(self.raw_dir / fn, newline="") as f:
                rows = csv.reader(f)
                next(rows), next(rows)  # header + units
                for la, lo, al in rows:
                    if al == "NaN":
                        continue
                    lat.append(round(float(la), 4))
                    lon.append(round(float(lo), 4))
                    alt.append(int(float(al)))
        return {
            "vintage": "ETOPO1, 1 arc-minute, sampled every ~4 km",
            "_files": files,
            "lat": lat,
            "lon": lon,
            "alt": alt,
        }
