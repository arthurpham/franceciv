"""Affine geographic placements for overseas inset territories.

The mainland projection is continuous. Overseas territories are therefore first moved into
unused pseudo-geographic slots west of metropolitan France; the normal Albers projection then
treats them as part of one map. `inverse` maps a pseudo point back to the territory's real
coordinates for raster sources such as elevation and land cover.
"""

INSETS = {
    "971": {
        "name": "Guadeloupe", "true": (-61.95, 15.75, -60.85, 16.60), "target": (-15.8, 43.2, -12.7, 45.6),
    },
    "972": {
        "name": "Martinique", "true": (-61.25, 14.35, -60.75, 14.95), "target": (-12.5, 43.2, -9.4, 45.6),
    },
    "973": {
        "name": "Guyane", "true": (-54.70, 1.95, -51.45, 5.90), "target": (-15.8, 48.8, -9.4, 51.0),
    },
    "974": {
        "name": "La Réunion", "true": (55.15, -21.45, 55.95, -20.75), "target": (-9.2, 43.2, -6.3, 45.6),
    },
    "976": {
        "name": "Mayotte", "true": (44.90, -13.10, 45.35, -12.55), "target": (-9.2, 39.7, -6.3, 41.1),
    },
    "975": {
        "name": "Saint-Pierre-et-Miquelon", "true": (-56.45, 46.72, -56.10, 47.14), "target": (-15.8, 41.6, -12.7, 43.0),
    },
    "977": {
        "name": "Saint-Barthélemy", "true": (-62.93, 17.85, -62.77, 17.95), "target": (-12.5, 41.6, -9.4, 43.0),
    },
    "978": {
        "name": "Saint-Martin", "true": (-63.17, 18.01, -62.95, 18.17), "target": (-9.2, 41.6, -6.3, 43.0),
    },
    "986": {
        "name": "Wallis-et-Futuna", "true": (-178.30, -14.45, -176.05, -13.10), "target": (-10.4, 39.7, -8.9, 41.1),
    },
    "987": {
        "name": "Polynésie française", "true": (-154.10, -27.80, -134.80, -7.80), "target": (-15.8, 45.8, -6.3, 48.6),
    },
    "988": {
        "name": "Nouvelle-Calédonie", "true": (163.40, -22.80, 168.30, -19.40), "target": (-9.2, 48.8, -6.3, 51.0),
    },
}
REGION_TO_DEP = {"01": "971", "02": "972", "03": "973", "04": "974", "06": "976", "975": "975", "977": "977", "978": "978", "986": "986", "987": "987", "988": "988"}


def _params():
    out = {}
    for dep, spec in INSETS.items():
        x0, y0, x1, y1 = spec["true"]
        tx0, ty0, tx1, ty1 = spec["target"]
        k = min((tx1 - tx0) / (x1 - x0), (ty1 - ty0) / (y1 - y0))
        ox = tx0 + ((tx1 - tx0) - k * (x1 - x0)) / 2 - k * x0
        oy = ty0 + ((ty1 - ty0) - k * (y1 - y0)) / 2 - k * y0
        out[dep] = {**spec, "scale": k, "offset": (ox, oy)}
    return out


PARAMS = _params()


def inset_for_dep(dep):
    return dep if dep in PARAMS else None


def transform_point(dep, lon, lat):
    spec = PARAMS.get(dep)
    if spec is None or lon is None or lat is None:
        return lon, lat
    ox, oy = spec["offset"]
    return spec["scale"] * lon + ox, spec["scale"] * lat + oy


def transform_rings(dep, rings):
    if dep not in PARAMS:
        return rings
    return [[transform_point(dep, lon, lat) for lon, lat in ring] for ring in rings]


def inverse_point(lon, lat):
    """Real lon/lat for a possibly pseudo-placed point; identity outside inset rectangles."""
    for spec in PARAMS.values():
        tx0, ty0, tx1, ty1 = spec["target"]
        if tx0 <= lon <= tx1 and ty0 <= lat <= ty1:
            ox, oy = spec["offset"]
            return (lon - ox) / spec["scale"], (lat - oy) / spec["scale"]
    return lon, lat


def real_inverse_bounds(spec):
    """Real-coordinate rectangle whose affine image exactly fills the pseudo target."""
    ox, oy = spec["offset"]
    tx0, ty0, tx1, ty1 = spec["target"]
    k = spec["scale"]
    return ((tx0 - ox) / k, (ty0 - oy) / k, (tx1 - ox) / k, (ty1 - oy) / k)


def transform_real_point(lon, lat):
    """Pseudo-placed lon/lat for a real source point, or identity for metropolitan points."""
    for dep, spec in PARAMS.items():
        x0, y0, x1, y1 = real_inverse_bounds(spec)
        if x0 <= lon <= x1 and y0 <= lat <= y1:
            return transform_point(dep, lon, lat)
    return lon, lat


def in_inset_area(lon, lat):
    return any(spec["target"][0] <= lon <= spec["target"][2] and spec["target"][1] <= lat <= spec["target"][3] for spec in PARAMS.values())


def frame_geo(dep):
    """Pseudo-geographic target frame as a closed ring."""
    x0, y0, x1, y1 = PARAMS[dep]["target"]
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
