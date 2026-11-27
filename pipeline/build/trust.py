"""trust.json — machine-readable freshness, coverage and reproducibility report.

This builder intentionally runs after the source catalog. It does not decide whether a
layer is good enough to publish; it makes the coverage and refresh state explicit so
`pipeline check`, reviewers and the Almanac can distinguish missing data from zero.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from ..core.paths import WEB_DATA
from ..core.store import write_web

REQUIRES: list[str] = []
PRODUCES = ["trust.json"]
RUN_LAST = True

# Refresh cadence is about re-running the pipeline against upstream publication rhythms,
# not a claim that every upstream file changes exactly on this schedule. Irregular census,
# boundary and physical geography inputs use the conservative default or a longer cycle.
DEFAULT_REFRESH_DAYS = 540
REFRESH_DAYS = {
    "fr_ev_charging": 45,
    "fr_mobile_network": 120,
    "fr_transit_frequency": 120,
    "fr_transit_stops": 120,
    "fr_energy_network": 180,
    "fr_electricity": 180,
    "fr_water_quality": 180,
    "fr_housing_history": 240,
    "fr_land_consumption": 365,
    "fr_air_quality": 365,
    "fr_insee_stats": 400,
    "fr_boundaries": 400,
    "fr_aav": 400,
    "fr_functional_geographies": 400,
    "fr_iris": 400,
    "fr_climate": 400,
    "fr_elections": 730,
    "fr_corine": 1095,
    "natural_earth": 1095,
    "etopo": 1825,
}
STATUS = {"fresh", "attention", "due", "unknown"}


def _json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _source_rows(sources, now):
    rows = []
    for s in sources:
        files = [f for f in s.get("files", []) if isinstance(f, dict)]
        times = [t for t in (_parse_time(f.get("retrieved")) for f in files) if t]
        latest = max(times) if times else None
        age = max(0, (now - latest).days) if latest else None
        cadence = REFRESH_DAYS.get(s.get("id"), DEFAULT_REFRESH_DAYS)
        if latest is None:
            status = "unknown"
        elif age > cadence:
            status = "due"
        elif age >= cadence * 0.8:
            status = "attention"
        else:
            status = "fresh"
        fingerprint = hashlib.sha256("\n".join(f"{f.get('file')}:{f.get('sha256')}" for f in sorted(files, key=lambda x: x.get("file", ""))).encode()).hexdigest() if files else None
        rows.append({
            "id": s.get("id"), "title": s.get("title"), "publisher": s.get("publisher"), "vintage": s.get("vintage"),
            "files": len(files), "retrieved": latest.isoformat(timespec="seconds") if latest else None,
            "age_days": age, "refresh_cadence_days": cadence, "status": status, "input_sha256": fingerprint,
        })
    return rows


def _time_values(lens):
    time = lens.get("time")
    if not isinstance(time, dict) or not isinstance(time.get("series"), dict):
        return lens.get("values")
    years = time.get("years") or []
    year = time.get("default") or (years[-1] if years else None)
    return time["series"].get(str(year)) or lens.get("values")


def _layer_rows(world):
    owner = world.get("owner") or []
    states = world.get("states") or []
    french = [i for i, o in enumerate(owner) if o >= 0]
    metro = [i for i in french if not (0 <= owner[i] < len(states) and states[owner[i]].get("inset"))]
    overseas = [i for i in french if i not in set(metro)]
    rows, duplicates = [], []
    seen = {}
    for path in sorted(WEB_DATA.glob("*.json")):
        doc = _json(path)
        if not isinstance(doc, dict) or not isinstance(doc.get("lenses"), list):
            continue
        for lens in doc["lenses"]:
            if not isinstance(lens, dict) or not lens.get("id"):
                continue
            lid = lens["id"]
            if lid in seen:
                duplicates.append(lid)
                continue
            seen[lid] = path.name
            vals = _time_values(lens)
            if not isinstance(vals, list) or len(vals) != len(owner):
                rows.append({"id": lid, "name": lens.get("name"), "file": path.name, "source": lens.get("source"), "shape": "invalid"})
                continue
            def share(indices):
                return round(sum(vals[i] is not None for i in indices) / len(indices), 4) if indices else None
            cov = share(french)
            rows.append({
                "id": lid, "name": lens.get("name"), "file": path.name, "group": lens.get("group"), "source": lens.get("source"),
                "shape": "ok", "non_null_cells": sum(v is not None for v in vals), "coverage": cov,
                "metropolitan_coverage": share(metro), "overseas_coverage": share(overseas),
                "time_years": len(lens.get("time", {}).get("years", [])) if isinstance(lens.get("time"), dict) else 0,
            })
    return rows, sorted(set(duplicates))


def build() -> None:
    now = datetime.now(timezone.utc)
    sources = _json(WEB_DATA / "sources.json") or []
    world = _json(WEB_DATA / "world.json") or {}
    source_rows = _source_rows(sources, now)
    layers, duplicates = _layer_rows(world)
    valid_layers = [l for l in layers if l.get("shape") == "ok"]
    fingerprint = hashlib.sha256("\n".join(f"{s['id']}:{s.get('input_sha256')}" for s in sorted(source_rows, key=lambda x: x["id"] or "")).encode()).hexdigest()
    counts = {k: sum(s["status"] == k for s in source_rows) for k in sorted(STATUS)}
    write_web("trust.json", {
        "version": 1,
        "generated": now.isoformat(timespec="seconds"),
        "summary": {
            "sources": len(source_rows), **counts,
            "lenses": len(layers), "valid_lens_shapes": len(valid_layers), "duplicate_lens_ids": duplicates,
            "mean_coverage": round(sum(l["coverage"] for l in valid_layers) / len(valid_layers), 4) if valid_layers else None,
            "coverage_under_half": sum((l.get("coverage") or 0) < 0.5 for l in valid_layers),
        },
        "sources": source_rows,
        "layers": layers,
        "reproducibility": {
            "contract": "docs/DATA_CONTRACTS.md v2",
            "rebuild": "PYTHONPATH=. uv run python -m pipeline all --offline",
            "validate": "PYTHONPATH=. uv run pytest -q && PYTHONPATH=. uv run python -m pipeline check",
            "source_fingerprint": fingerprint,
            "notes": "Freshness compares cache retrieval age with the declared refresh cadence; coverage is the share of owned hexes with a non-null value at the lens default/latest year. Null means no validated coverage, never zero.",
        },
    })


def check(web_dir):
    doc = json.loads((web_dir / "trust.json").read_text())
    assert doc["version"] == 1 and isinstance(doc["sources"], list) and isinstance(doc["layers"], list)
    assert all(s["status"] in STATUS for s in doc["sources"])
    assert len(doc["sources"]) == len(json.loads((web_dir / "sources.json").read_text()))
    layers = json.loads((web_dir / "lenses.json").read_text())["lenses"]
    assert len(doc["layers"]) >= len(layers)
    assert all(l.get("shape") != "ok" or 0 <= l["coverage"] <= 1 for l in doc["layers"])
    level = "WARN" if doc["summary"].get("due") or doc["summary"].get("duplicate_lens_ids") else "PASS"
    return [(level, f"trust.json: {len(doc['sources'])} source freshness rows and {len(doc['layers'])} lens coverage rows")]
