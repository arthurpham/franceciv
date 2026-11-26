"""Detailed French river overlay derived from IGN BD CARTO."""

from ..core.geo import MapProjection
from ..core.store import load_interim, write_web

REQUIRES = ["_world", "fr_hydrography"]
PRODUCES = ["hydrography.json"]


def pairs(flat):
    return list(zip(flat[::2], flat[1::2]))


def simplify(points, tolerance=0.22):
    """Ramer-Douglas-Peucker in map kilometres."""
    if len(points) <= 2:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = points[a]
        bx, by = points[b]
        dx, dy = bx - ax, by - ay
        den = dx * dx + dy * dy
        worst, wi = -1.0, -1
        for i in range(a + 1, b):
            px, py = points[i]
            if den:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / den))
                qx, qy = ax + t * dx, ay + t * dy
            else:
                qx, qy = ax, ay
            d = ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5
            if d > worst:
                worst, wi = d, i
        if worst > tolerance and wi >= 0:
            keep[wi] = True
            stack.extend([(a, wi), (wi, b)])
    return [p for p, k in zip(points, keep) if k]


def build():
    world = load_interim("_world")
    hydro = load_interim("fr_hydrography")
    proj = MapProjection(**world["projection"])
    rivers = []
    for seg in hydro["segments"]:
        pts = [proj(x, y) for x, y in pairs(seg["pts"])]
        pts = [(round(x, 1), round(y, 1)) for x, y in simplify(pts)]
        if len(pts) < 2:
            continue
        length = sum(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 for (x0, y0), (x1, y1) in zip(pts, pts[1:]))
        if length < 1.2:
            continue
        rivers.append({"name": seg["name"], "rank": seg["rank"], "pts": [v for p in pts for v in p]})
    write_web("hydrography.json", {
        "version": 1,
        "vintage": "IGN BD CARTO V5 WFS",
        "sources": ["fr_hydrography"],
        "rivers": rivers,
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "hydrography.json").read_text())
    assert len(doc["rivers"]) > 1000
    assert all(len(r["pts"]) >= 4 for r in doc["rivers"])
    return [("PASS", f"hydrography.json: {len(doc['rivers'])} detailed river segments")]
