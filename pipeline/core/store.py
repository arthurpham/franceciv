"""Reading/writing interim and web output files.

All writes are atomic (temp file + os.replace), so an interrupted run never
leaves a truncated JSON file for the next step or the browser to choke on.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import INTERIM, WEB_DATA


def atomic_write_text(path: Path, text: str) -> None:
    """Write `text` to `path` via a sibling temp file and os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def save_interim(name: str, data: dict, *, vintage: str | None = None) -> None:
    """Save data/interim/<name>.json. A "_files" key (raw files used) is stored as payload["files"]."""
    data = dict(data)
    files = data.pop("_files", None)
    payload = {
        "name": name,
        "processed": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "vintage": vintage,
        "data": data,
    }
    if files is not None:
        payload["files"] = sorted(str(f) for f in files)
    atomic_write_text(INTERIM / f"{name}.json", json.dumps(payload, separators=(",", ":")))


def load_interim_payload(name: str) -> dict:
    path = INTERIM / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"interim '{name}' missing – run: uv run python -m pipeline process {name}")
    return json.loads(path.read_text())


def load_interim(name: str) -> Any:
    return load_interim_payload(name)["data"]


_LAND_INDICES = None


def land_indices() -> list[int] | None:
    """French land-cell indices in the committed world grid, cached for builder output packing."""
    global _LAND_INDICES
    if _LAND_INDICES is not None:
        return _LAND_INDICES
    path = WEB_DATA / "world.json"
    if not path.exists():
        return None
    try:
        world = json.loads(path.read_text())
        owner = world.get("owner")
        if not isinstance(owner, list):
            return None
        _LAND_INDICES = [i for i, v in enumerate(owner) if isinstance(v, int) and v >= 0]
        return _LAND_INDICES
    except (OSError, json.JSONDecodeError):
        return None


def pack_sparse_lenses(data: Any) -> Any:
    """Use land-index transport for large lens arrays when it is materially smaller.

    Lens values are always null outside French land cells, and those cells are most of the hex grid.
    Keeping only values in owner>=0 order preserves exact values while removing that repeated null
    padding. Unlike key-index sparse objects, arrays remain gzip-friendly for static hosting.
    """
    if not isinstance(data, dict) or not isinstance(data.get("lenses"), list):
        return data
    land = land_indices()
    if not land:
        return data
    for lens in data["lenses"]:
        vals = lens.get("values")
        if not isinstance(vals, list) or len(vals) < 500 or lens.get("encoding") in {"sparse-index-v1", "land-index-v1"}:
            continue
        if max(land, default=-1) >= len(vals):
            continue
        packed = [vals[i] for i in land]
        dense_text = json.dumps(vals, separators=(",", ":"), allow_nan=False)
        packed_text = json.dumps(packed, separators=(",", ":"), allow_nan=False)
        if len(packed_text) < len(dense_text) * 0.8:
            lens["encoding"] = "land-index-v1"
            lens["values"] = packed
    return data

def write_web(name: str, data: Any) -> None:
    text = json.dumps(pack_sparse_lenses(data), separators=(",", ":"), allow_nan=False)
    atomic_write_text(WEB_DATA / name, text)
    print(f"    → web/data/{name} ({len(text) / 1e3:.0f} kB)")
