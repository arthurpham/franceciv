"""The map itself: hex grid, land/water, relief, land cover, states, counties, rivers.

Also saves interim "_world" (grid + projection + per-cell state/county/water/cover)
so the other builders can drop their data onto the same hexes.
"""

from __future__ import annotations

import math
from collections import Counter

from ..core.geo import MapProjection, Shape, ShapeIndex
from ..core.insets import PARAMS, frame_geo, in_inset_area, inverse_point, transform_real_point
from ..core.hexgrid import SQRT3, HexGrid
from ..core.store import load_interim, save_interim, write_web

REQUIRES = ["fr_boundaries", "natural_earth", "etopo", "fr_corine"]
PRODUCES = ["_world", "world.json"]

HEX_RADIUS_KM = 8.0
MARGIN_KM = 100.0

# Cell owner codes (besides state index >= 0)
WATER, FOREIGN = -1, -2

# --- tables (written to world.json so the frontend and Almanac read one definition) ---------

LAND, OCEAN, COAST, LAKE = range(4)
TIDAL_SEA_SHARE = 0.5  # share of ETOPO samples below 0 m that keeps a sea-centred hex as water
COAST_DEPTH_M = -200
WATER_TABLE = [
    {"id": LAND, "name": "Land", "rule": "At least 4 of the hex's 7 sample points (centre + 6) fall on French region or Natural Earth country outlines, unless the centre is sea and the ETOPO1 mean is at or below sea level, or at least half its ETOPO1 samples are (tidal bays stay water)."},
    {"id": OCEAN, "name": "Ocean", "color": "#1b4266", "rule": "Sea deeper than 200 m and not next to land."},
    {"id": COAST, "name": "Coast", "color": "#2d6d97", "rule": "Sea next to a land hex, or shallower than 200 m (ETOPO1 mean)."},
    {"id": LAKE, "name": "Lake", "color": "#3a80b0", "rule": "Water hex (most of its 7 sample points off land) with Natural Earth 1:50m lake points that outnumber sea points, or above sea level."},
]

WATER_NOTE = (
    "French region outlines and Natural Earth 1:50m country and lake outlines don't meet exactly. A sea hex whose "
    "ETOPO1 mean is above sea level (and under half of its samples below it) becomes land when at least 4 of its 6 neighbours are land, or when it touches both "
    "French and foreign land; it takes the neighbours' majority owner. Narrow reservoirs that cover less than half a hex "
    "are land, and their river is drawn through them. Tidal bays stay water when the hex centre is sea and its "
    "ETOPO1 mean is at or below sea level or at least half of its ETOPO1 samples are. A sea hex's "
    "elevation is the mean of its ETOPO1 samples below sea level (its water depth)."
)

FLAT, HILLS, MOUNTAINS, PEAKS = range(4)
LAND_MIN_ALT_M = -100  # ETOPO samples below this inside a land hex are treated as sea floor
RELIEF_TABLE = [
    {"id": FLAT, "name": "Flat", "rule": "Elevation standard deviation inside the hex under 40 m."},
    {"id": HILLS, "name": "Hills", "rule": "Elevation standard deviation ≥ 40 m."},
    {"id": MOUNTAINS, "name": "Mountains", "rule": "Elevation standard deviation ≥ 120 m, or mean elevation ≥ 1,300 m."},
    {"id": PEAKS, "name": "Peaks", "rule": "Mean elevation ≥ 1,900 m (high Alps or Pyrenees)."},
]
RELIEF_NOTE = (
    "From ETOPO1 samples (~4 km apart, a few per hex) with altitude ≥ -100 m, so bays and sea floor don't "
    "count; all samples are used if none qualify. Water hexes are always flat."
)

URBAN_MIN_PCT = 30
# id, key, name, colour, CORINE land-cover codes, rule. Ids are fixed by docs/DATA_CONTRACTS.md.
COVER = [
    (1, "forest_deciduous", "Deciduous forest", "#4f7a35", [41], "Forest (41+42+43) is the largest group and deciduous (41) the largest forest type."),
    (2, "forest_evergreen", "Conifer forest", "#2f5a3a", [42], "Forest is the largest group and evergreen (42) the largest forest type."),
    (3, "forest_mixed", "Mixed forest", "#43703f", [43], "Forest is the largest group and mixed (43) the largest forest type."),
    (4, "scrub", "Scrub & desert", "#c9b07a", [52], "Shrub/scrub (52) is the largest group: deserts, chaparral, sagebrush."),
    (5, "grassland", "Grassland", "#a9b35a", [71, 21], "Grassland/herbaceous (71) plus developed open space (21: lawns, parks) is the largest group."),
    (6, "pasture", "Pasture", "#8fb04e", [81], "Pasture/hay (81) is the largest group."),
    (7, "cropland", "Cropland", "#c2b84e", [82], "Cultivated crops (82) is the largest group."),
    (8, "wetland", "Wetland", "#4f8a6e", [90, 95], "Woody (90) plus emergent herbaceous (95) wetlands is the largest group."),
    (9, "urban", "Urban", "#8a8378", [22, 23, 24], f"Developed low/medium/high intensity (22+23+24) is ≥ {URBAN_MIN_PCT}% of the hex's land, whatever else is there."),
    (10, "barren", "Barren", "#bfae95", [31], "Barren land (31: rock, sand, playa) is the largest group."),
    (11, "ice", "Ice & snow", "#e8eef2", [12], "Perennial ice/snow (12) is the largest group."),
]
COVER_NOTE = (
    "From CORINE Land Cover 2018 read through the IGN WMS at ~380 m pixels, sampled on a 1 km lattice inside each French hex. Open water (11) "
    "and no-data pixels are ignored; shares are of the remaining land points, rounded to whole percent, and the urban "
    "threshold is applied to the rounded developed share. Foreign hexes have cover 0 (none) in this France build."
)
# Groups competing for the dominant cover (urban is decided by its threshold first).
GROUPS = {
    "forest": (41, 42, 43), "scrub": (52,), "grassland": (71, 21), "pasture": (81,), "cropland": (82,),
    "wetland": (90, 95), "barren": (31,), "ice": (12,),
}
FOREST_ID = {41: 1, 42: 2, 43: 3}
GROUP_ID = {"scrub": 4, "grassland": 5, "pasture": 6, "cropland": 7, "wetland": 8, "barren": 10, "ice": 11}
URBAN_ID = 9
PCT = {
    "forest": (41, 42, 43), "crop": (82,), "pasture": (81,), "grass": (71, 21), "shrub": (52,),
    "wetland": (90, 95), "developed": (22, 23, 24),
}
WORLDCOVER_STEP_KM = 1.0


def classify_relief(mean: float, std: float) -> int:
    if mean >= 1900:
        return PEAKS
    if std >= 120 or mean >= 1300:
        return MOUNTAINS
    if std >= 40:
        return HILLS
    return FLAT


def is_valley_floor(samples: list) -> bool:
    """True when the lower 60% of a hex's land samples is flat lowland (within 60 m, under 400 m): the hex is mostly
    valley floor even if a range at its edge makes the whole hex's spread look hilly or mountainous."""
    if len(samples) < 6:
        return False
    v = sorted(samples)
    lo = v[: max(3, int(len(v) * 0.6))]
    return lo[-1] < 400 and lo[-1] - lo[0] < 60


def dominant_cover(counts: Counter, land: int) -> int:
    """Cover id for a hex from its land-cover class counts (land = points that are not water or no-data)."""
    if not land:
        return 0
    if round(100 * sum(counts[c] for c in (22, 23, 24)) / land) >= URBAN_MIN_PCT:  # same rounding as pct.developed
        return URBAN_ID
    best, best_n = None, 0
    for g, codes in GROUPS.items():  # dict order breaks ties
        n = sum(counts[c] for c in codes)
        if n > best_n:
            best, best_n = g, n
    if best is None:
        return 0  # only developed land below the urban threshold
    if best == "forest":
        return FOREST_ID[max((41, 42, 43), key=lambda c: counts[c])]
    return GROUP_ID[best]


def simplify(points: list[tuple[float, float]], min_km: float) -> list[tuple[float, float]]:
    out = [points[0]]
    for p in points[1:-1]:
        if math.dist(p, out[-1]) >= min_km:
            out.append(p)
    out.append(points[-1])
    return out


def clip_segment(p, q, w, h):
    """Liang–Barsky: the part of segment p→q inside [0,w]×[0,h], or None."""
    (x0, y0), (x1, y1) = p, q
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for pk, qk in ((-dx, x0), (dx, w - x0), (-dy, y0), (dy, h - y0)):
        if pk == 0:
            if qk < 0:
                return None
            continue
        t = qk / pk
        if pk < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return None
    return (x0 + t0 * dx, y0 + t0 * dy), (x0 + t1 * dx, y0 + t1 * dy)


def clip_polyline(pts, w, h) -> list[list[tuple[float, float]]]:
    """Split a polyline into the pieces that lie inside the map rectangle."""
    pieces, cur = [], []
    for p, q in zip(pts, pts[1:]):
        seg = clip_segment(p, q, w, h)
        if seg is None:
            if len(cur) >= 2:
                pieces.append(cur)
            cur = []
            continue
        a, b = seg
        if cur and math.dist(cur[-1], a) < 1e-9:
            cur.append(b)
        else:
            if len(cur) >= 2:
                pieces.append(cur)
            cur = [a, b]
        if b != q:  # left the map inside this segment
            pieces.append(cur)
            cur = []
    if len(cur) >= 2:
        pieces.append(cur)
    return pieces


def land_runs(pts, is_land, step: float = 2.0) -> list[list[tuple[float, float]]]:
    """Split a projected polyline (densified every `step` km) into the runs whose points satisfy is_land."""
    runs, cur = [], []
    for k, (p, q) in enumerate(zip(pts, pts[1:])):
        n = max(1, math.ceil(math.dist(p, q) / step))
        for j in range(0 if k == 0 else 1, n + 1):
            t = j / n
            pt = (p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))
            if is_land(pt):
                cur.append(pt)
            else:
                if len(cur) >= 2:
                    runs.append(cur)
                cur = []
    if len(cur) >= 2:
        runs.append(cur)
    return runs


def join_lines(lines: list[list[tuple[float, float]]], tol: float = 0.5) -> list[list[tuple[float, float]]]:
    """Greedily join polylines whose ends meet (within `tol` km), reversing pieces as needed."""
    lines = [list(l) for l in lines]
    joined = True
    while joined:
        joined = False
        for a in range(len(lines)):
            for b in range(len(lines)):
                if a == b or not lines[a] or not lines[b]:
                    continue
                la, lb = lines[a], lines[b]
                for la2, lb2 in ((la, lb), (la, lb[::-1]), (la[::-1], lb), (la[::-1], lb[::-1])):
                    if math.dist(la2[-1], lb2[0]) <= tol:
                        lines[a] = la2 + lb2[1:]
                        lines[b] = []
                        joined = True
                        break
        lines = [l for l in lines if l]
    return lines


def hex_lattice(radius: float, step: float) -> list[tuple[float, float]]:
    """Offsets of a square lattice (spacing `step`) that fall inside a pointy-top hex."""
    half_w = SQRT3 / 2 * radius
    n = int(radius // step) + 1
    out = []
    for iy in range(-n, n + 1):
        for ix in range(-n, n + 1):
            x, y = (ix + 0.5) * step, (iy + 0.5) * step
            if abs(x) <= half_w and abs(y) <= radius - abs(x) / SQRT3:
                out.append((x, y))
    return out


def majority(values: list, centre) -> object:
    """Most common value; ties go to `centre` if it is among the tied, else to the first seen."""
    counts = Counter(values)
    top = max(counts.values())
    tied = [v for v in counts if counts[v] == top]
    return centre if centre in tied else tied[0]


def build() -> None:
    bounds = load_interim("fr_boundaries")
    ne = load_interim("natural_earth")
    etopo = load_interim("etopo")
    worldcover = load_interim("fr_corine")

    states = sorted(bounds["states"], key=lambda s: s["name"])
    counties = sorted(bounds["counties"], key=lambda c: c["geoid"])

    # Projection: fit the combined mainland and pseudo-placed overseas inset geometry with a margin.
    probe = MapProjection(0, 0, 0)
    xs, ys = [], []
    for s in states:
        for ring in s["rings"]:
            for lon, lat in ring:
                x, y = probe._albers(lon, lat)
                xs.append(x)
                ys.append(y)
    proj = MapProjection(min(xs), max(ys), MARGIN_KM)
    width = max(xs) - min(xs) + 2 * MARGIN_KM
    height = max(ys) - min(ys) + 2 * MARGIN_KM
    grid = HexGrid.covering(width, height, HEX_RADIUS_KM)
    print(f"    grid {grid.cols}×{grid.rows} = {grid.size} hexes of {HEX_RADIUS_KM:g} km")

    def shape(rings):
        return Shape([[proj(lon, lat) for lon, lat in r] for r in rings])

    state_idx = ShapeIndex([shape(s["rings"]) for s in states])
    county_idx = ShapeIndex([shape(c["rings"]) for c in counties], cell_km=60)
    foreign_idx = ShapeIndex([shape(c["rings"]) for c in ne["countries"]], cell_km=200)
    lake_idx = ShapeIndex([shape(l["rings"]) for l in ne["lakes"]])

    # --- elevation statistics per hex (land samples and all samples) -----------------------------
    stats_all = [[0, 0.0, 0.0] for _ in range(grid.size)]
    stats_land = [[0, 0.0, 0.0] for _ in range(grid.size)]
    samples_land = [[] for _ in range(grid.size)]  # land altitudes, for the peak height and the valley-floor test
    below_sea = [0] * grid.size  # ETOPO samples below 0 m ...
    below_sum = [0.0] * grid.size  # ... and their altitude sum
    for lat, lon, alt in zip(etopo["lat"], etopo["lon"], etopo["alt"]):
        map_lon, map_lat = transform_real_point(lon, lat)
        i = grid.cell_at(*proj(map_lon, map_lat))
        if i < 0:
            continue
        if alt < 0:
            below_sea[i] += 1
            below_sum[i] += alt
        for st in (stats_all[i], stats_land[i]) if alt >= LAND_MIN_ALT_M else (stats_all[i],):
            st[0] += 1
            st[1] += alt
            st[2] += alt * alt
        if alt >= LAND_MIN_ALT_M:
            samples_land[i].append(alt)

    def sea_share(i):
        return below_sea[i] / stats_all[i][0] if stats_all[i][0] else 0.0

    def mean_std(st):
        n, s1, s2 = st
        if not n:
            return None, None
        m = s1 / n
        return m, math.sqrt(max(0.0, s2 / n - m * m))

    # --- ownership: majority of 7 sample points --------------------------------------------------
    # The centre plus six points 60% of the way to each corner. Each point is lake, a state, foreign
    # land or other water; the majority decides (the centre breaks ties). All seven also give an
    # area-weighted county mix for lenses.
    offsets = [(0.0, 0.0)] + [
        (0.6 * HEX_RADIUS_KM * math.cos(math.radians(60 * k - 30)), 0.6 * HEX_RADIUS_KM * math.sin(math.radians(60 * k - 30)))
        for k in range(6)
    ]
    owner = [WATER] * grid.size
    water = [OCEAN] * grid.size
    for i in range(grid.size):
        cx, cy = grid.center(*grid.col_row(i))
        kinds = []
        for dx, dy in offsets:
            x, y = cx + dx, cy + dy
            if lake_idx.locate(x, y) >= 0:
                kinds.append("lake")
            elif (s := state_idx.locate(x, y)) >= 0:
                kinds.append(s)
            elif not in_inset_area(*proj.inverse(x, y)) and foreign_idx.locate(x, y) >= 0:
                kinds.append(FOREIGN)
            else:
                kinds.append("sea")
        land = [k for k in kinds if not isinstance(k, str)]
        m_all, _ = mean_std(stats_all[i])
        # Narrow tidal bays are often narrower than half a hex; keep them
        # water when the centre is sea and the hex is mostly at or below sea level in ETOPO1.
        tidal = kinds[0] == "sea" and m_all is not None and (m_all <= 0 or sea_share(i) >= TIDAL_SEA_SHARE)
        if len(land) * 2 > len(kinds) and not tidal:
            us = [k for k in land if k >= 0]
            n_foreign = len(land) - len(us)
            if len(us) > n_foreign or (len(us) == n_foreign and kinds[0] != FOREIGN):
                owner[i] = majority(us, kinds[0])
            else:
                owner[i] = FOREIGN
            water[i] = LAND
        else:
            wet = [k for k in kinds if isinstance(k, str)]
            # Points in neither the lake nor the land outlines are usually sea, but next to a lake they are
            # mostly gaps between the two datasets' shorelines, so a lake hex needs only to be above sea level.
            above_sea = m_all is not None and m_all > 0
            lakeish = "lake" in wet and (above_sea or majority(wet, kinds[0] if kinds[0] in wet else "lake") == "lake")
            water[i] = LAKE if lakeish else OCEAN

    # Sliver fix: French administrative and Natural Earth (1:50m) outlines don't meet exactly, leaving water hexes
    # on land along land borders and coasts. A non-lake water hex whose ETOPO mean is above sea
    # level becomes land if at least 4 of its neighbours are land, or if it touches both French and foreign land.
    # It takes its land neighbours' majority owner.
    slivers = []
    for i in range(grid.size):
        if water[i] != OCEAN:
            continue
        m, _ = mean_std(stats_all[i])
        land_nb = [owner[j] for j in grid.neighbours(i) if water[j] == LAND]
        border = FOREIGN in land_nb and any(o >= 0 for o in land_nb)
        if m is not None and m > 0 and sea_share(i) < TIDAL_SEA_SHARE and (len(land_nb) >= 4 or border):
            slivers.append((i, Counter(land_nb).most_common(1)[0][0]))
    for i, o in slivers:
        owner[i], water[i] = o, LAND
    print(f"    {len(slivers)} sliver water hexes turned into land: {[i for i, _ in slivers]}")

    # Sparse Pacific archipelagos cannot be represented faithfully by majority area at an 8 km
    # national hex resolution: individual islands are far smaller than a hex even when the inset
    # frame itself is enlarged. Keep one representative land hex per commune centroid so Wallis-et-Futuna
    # and French Polynesia remain visible and clickable; the inset frame still shows their scattered geography.
    archipelago_cell_county = {}
    state_by_fips = {s["fips"]: si for si, s in enumerate(states)}
    county_pos = {c["geoid"]: ci for ci, c in enumerate(counties)}
    represented = 0
    for c in bounds["communes"]:
        dep = c.get("department")
        if dep not in {"986", "987"} or c.get("lon") is None:
            continue
        i = grid.cell_at(*proj(c["lon"], c["lat"]))
        ci = county_pos.get(dep)
        if i >= 0 and ci is not None and water[i] != LAND:
            owner[i], water[i] = state_by_fips[dep], LAND
            archipelago_cell_county[i] = ci
            represented += 1
    if represented:
        print(f"    {represented} sparse-archipelago commune hexes represented cartographically")

    # Overseas territories are cartographic insets in a continuous projected plane. Real foreign
    # coastlines can project into the same screen space; clear a padded box around each territory
    # so every inset sits in clean ocean, like a conventional inset map.
    inset_boxes = {}
    state_for_inset = {st.get("inset"): si for si, st in enumerate(states) if st.get("inset")}
    inset_foreign_removed = 0
    for dep, state_i in state_for_inset.items():
        owned = [i for i, o in enumerate(owner) if o == state_i]
        if not owned:
            continue
        pts = [grid.center(*grid.col_row(i)) for i in owned]
        pad = HEX_RADIUS_KM * 1.2
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        box = (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)
        inset_boxes[dep] = box
        x0, y0, x1, y1 = box
        for i, o in enumerate(owner):
            if o != FOREIGN:
                continue
            cx, cy = grid.center(*grid.col_row(i))
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                owner[i], water[i] = WATER, OCEAN
                inset_foreign_removed += 1
    print(f"    {inset_foreign_removed} foreign hexes cleared from overseas inset frames")

    # --- counties for French cells -------------------------------------------------------------------
    county = [-1] * grid.size
    county_samples: list[list[int]] = [[] for _ in range(grid.size)]
    for i in range(grid.size):
        if owner[i] >= 0:
            cx, cy = grid.center(*grid.col_row(i))
            county_samples[i] = [county_idx.locate(cx + dx, cy + dy) for dx, dy in offsets]
    # Hexes whose seven points all miss the county polygons (e.g. reclaimed slivers) borrow the most
    # common county of their same-state neighbours for the centre sample.
    borrowed = 0
    for i in range(grid.size):
        smp = county_samples[i]
        if i in archipelago_cell_county:
            smp[0] = archipelago_cell_county[i]
        if smp and max(smp) < 0:
            nb = [k for j in grid.neighbours(i) if owner[j] == owner[i] for k in county_samples[j] if k >= 0]
            if nb:
                smp[0] = Counter(nb).most_common(1)[0][0]
                borrowed += 1
    # The hex's county must lie in its owner state (majority ownership can differ from the centre point):
    # the centre if it does, else the most common in-state sample, else any sample. county_samples keep
    # every point, so lenses still area-weight across state lines.
    county_state = [c["state_fips"] for c in counties]
    off_state = 0
    for i, smp in enumerate(county_samples):
        valid = [k for k in smp if k >= 0]
        if not valid:
            continue
        same = [k for k in valid if county_state[k] == states[owner[i]]["fips"]]
        pool = same or valid
        county[i] = smp[0] if smp[0] in pool else Counter(pool).most_common(1)[0][0]
        off_state += not same
    # Compact departments can fall between the coarse hex lattice even though they are large and
    # important statistical units (Paris is smaller than one 8 km hex). Give any otherwise unrepresented
    # county the hex containing its most populous commune; this is a cartographic representation rule,
    # not a claim that the whole hex belongs to that county.
    represented_counties = {c for c in county if c >= 0}
    county_pos = {c["geoid"]: ci for ci, c in enumerate(counties)}
    small_counties = 0
    for c in counties:
        ci = county_pos[c["geoid"]]
        if ci in represented_counties:
            continue
        members = [co for co in bounds["communes"] if co.get("department") == c["geoid"] and co.get("lon") is not None]
        if not members:
            continue
        seat = max(members, key=lambda co: co.get("population") or 0)
        i = grid.cell_at(*proj(seat["lon"], seat["lat"]))
        if i < 0:
            continue
        owner[i], water[i], county[i] = state_by_fips[c["state_fips"]], LAND, ci
        samples = county_samples[i]
        if len(samples) < len(offsets):
            samples.extend([-1] * (len(offsets) - len(samples)))
        samples[0] = ci
        small_counties += 1
    print(f"    {borrowed} French hexes borrowed a neighbour's county; {off_state} have no county in their own state")
    if small_counties:
        print(f"    {small_counties} compact counties represented by their most populous commune hex")

    # --- elevation, water depth classes and relief -------------------------------------------------
    elev = [0] * grid.size
    relief = [FLAT] * grid.size
    elev_max = [0] * grid.size  # highest land sample (m): snow on high ranges whose mean is held down by valleys
    valley_floor = 0
    no_elev = 0
    for i in range(grid.size):
        if water[i] == LAND:
            m, sd = mean_std(stats_land[i])
            if m is None:
                m, sd = mean_std(stats_all[i])
                m = None if m is None else max(m, 0.0)
            if m is None:
                no_elev += 1
                continue  # elev 0, flat
            elev[i] = round(m)
            relief[i] = classify_relief(max(m, 0.0), sd)
            if relief[i] in (HILLS, MOUNTAINS) and is_valley_floor(samples_land[i]):
                relief[i] -= 1  # mostly flat lowland with a range at one edge (the Central Valley's rim)
                valley_floor += 1
            if samples_land[i]:
                elev_max[i] = max(0, round(max(samples_land[i])))
        else:
            m, _ = mean_std(stats_all[i])
            if m is None:
                no_elev += 1
                elev[i] = -4000  # outside the elevation window: assume deep ocean
            elif water[i] != LAKE and below_sea[i]:
                elev[i] = round(below_sum[i] / below_sea[i])  # sea: mean depth of the samples under water
            else:
                elev[i] = min(round(m), 0)
            if water[i] == OCEAN:
                near_land = any(water[j] == LAND for j in grid.neighbours(i))
                water[i] = COAST if near_land or elev[i] > COAST_DEPTH_M else OCEAN
    print(f"    {no_elev} hexes without elevation samples; {valley_floor} valley-floor hexes eased one relief class")

    # --- land cover from CORINE land-cover --------------------------------------------------------------------
    rows, legend = worldcover["rows"], worldcover["legend"]
    x0, dx, y0, dy = worldcover["x0"], worldcover["dx"], worldcover["y0"], worldcover["dy"]
    ncols, nrows = worldcover["cols"], len(rows)
    lattice = hex_lattice(HEX_RADIUS_KM, WORLDCOVER_STEP_KM)
    cover = [0] * grid.size
    pct = {k: [0] * grid.size for k in PCT}
    no_cover = 0
    for i in range(grid.size):
        if owner[i] < 0:
            continue
        cx, cy = grid.center(*grid.col_row(i))
        counts: Counter = Counter()
        for ox, oy in lattice:
            lon, lat = inverse_point(*proj.inverse(cx + ox, cy + oy))
            c, r = round((lon - x0) / dx), round((lat - y0) / dy)
            if 0 <= c < ncols and 0 <= r < nrows:
                counts[rows[r][c]] += 1
        counts = Counter({legend[ch]: n for ch, n in counts.items()})
        land = sum(n for code, n in counts.items() if code not in (0, 11))
        cover[i] = dominant_cover(counts, land)
        if not land:
            no_cover += 1
            continue
        for k, codes in PCT.items():
            pct[k][i] = round(100 * sum(counts[c] for c in codes) / land)
    print(f"    {len(lattice)} CORINE raster points per hex; {no_cover} French hexes without land-cover samples")

    # --- rivers ----------------------------------------------------------------------------------
    # Lake centerlines are kept only where they cross land hexes (lakes or reservoirs narrower than half a hex),
    # so rivers don't stop in the middle of land; over water hexes they go.
    def on_land(pt):
        c = grid.cell_at(*pt)
        return c >= 0 and water[c] == LAND

    by_river: dict[tuple, list] = {}
    for r in ne["rivers"]:
        if r["rank"] > 8:
            continue
        line = [proj(lon, lat) for lon, lat in r["line"]]
        if (r.get("featurecla") or "").startswith("Lake Centerline"):
            parts = [run for p in clip_polyline(line, width, height) for run in land_runs(p, on_land)]
        else:
            parts = clip_polyline(line, width, height)
        by_river.setdefault((r["name"], r["rank"]), []).extend(parts)
    rivers = []
    for (name, rank), parts in by_river.items():
        for piece in join_lines(parts):
            if sum(math.dist(a, b) for a, b in zip(piece, piece[1:])) < 1.0:
                continue  # a corner clipped down to nothing
            pts = simplify(piece, 4.0)
            if len(pts) >= 2:
                rivers.append({"name": name, "rank": rank, "pts": [round(v, 1) for p in pts for v in p]})

    cover_table = [{"id": 0, "key": "none", "name": "None", "rule": "Water, foreign land, or no CORINE land-cover land pixels."}] + [
        {"id": cid, "key": key, "name": name, "color": color, "worldcover": codes, "rule": rule}
        for cid, key, name, color, codes, rule in COVER
    ]
    tables = {
        "water": WATER_TABLE,
        "relief": RELIEF_TABLE,
        "cover": cover_table,
        "notes": {"water": WATER_NOTE, "relief": RELIEF_NOTE, "cover": COVER_NOTE},
    }
    states_out = [{"fips": s["fips"], "abbr": s["abbr"], "name": s["name"], **({"inset": s["inset"]} if s.get("inset") else {})} for s in states]
    insets = []
    state_index = {s.get("inset"): i for i, s in enumerate(states) if s.get("inset")}
    for dep, spec in PARAMS.items():
        if dep in inset_boxes:
            x0, y0, x1, y1 = inset_boxes[dep]
        else:
            pts = [proj(lon, lat) for lon, lat in frame_geo(dep)]
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        insets.append({"dep": dep, "name": spec["name"], "frame": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)]})
    # Share of each hex covered by French department samples. The seven samples approximate area;
    # sea and foreign samples both count as outside the French statistical territory.
    france_share = [
        round(sum(1 for k in county_samples[i] if k >= 0) / len(county_samples[i]), 4) if owner[i] >= 0 and county_samples[i] else 0
        for i in range(grid.size)
    ]
    write_web(
        "world.json",
        {
            "version": 2,
            "grid": grid.to_dict(),
            "width": round(width, 1),
            "height": round(height, 1),
            "margin": MARGIN_KM,
            "insets": insets,
            "owner": owner,
            "county": county,
            "france_share": france_share,
            "elev": elev,
            "elev_max": elev_max,
            "water": water,
            "relief": relief,
            "cover": cover,
            "pct": pct,
            "tables": tables,
            "states": states_out,
            "counties": [{"geoid": c["geoid"], "name": c["name"]} for c in counties],
            "rivers": rivers,
        },
    )
    save_interim(
        "_world",
        {
            "grid": grid.to_dict(),
            "projection": proj.to_dict(),
            "owner": owner,
            "county": county,
            "county_samples": county_samples,
            "states": [s["fips"] for s in states],
            "counties": [c["geoid"] for c in counties],
            "water": water,
            "cover": cover,
            "pct": pct,
        },
    )
