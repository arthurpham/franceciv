"""Quality-of-life lenses: housing prices and healthcare accessibility."""

from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .connectivity import nearest_land

REQUIRES = ["_world", "fr_boundaries", "fr_housing", "fr_healthcare", "fr_social_housing"]
PRODUCES = ["quality_life.json"]

RAMP = ["#2d213f", "#58508d", "#4f86a8", "#62b58f", "#f0d264"]


def percentile(vals, p):
    xs = sorted(v for v in vals if v is not None)
    return xs[min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))] if xs else None


def weighted_series(size, rows):
    out = []
    for i in range(size):
        total = sum(w for v, w in rows.get(i, []) if v is not None)
        value = sum(v * w for v, w in rows.get(i, []) if v is not None) / total if total else None
        out.append(round(value, 4) if value is not None else None)
    return out


def lens(lens_id, name, emoji, unit, fmt, vals, source, description):
    return {
        "id": lens_id, "group": "quality", "name": name, "icon": lens_id, "emoji": emoji, "unit": unit,
        "format": fmt, "scale": "linear", "domain": [percentile(vals, 2), percentile(vals, 98)], "ramp": RAMP,
        "higher_is": "neutral", "source": source, "description": description, "values": vals,
    }


def build():
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    housing = load_interim("fr_housing")
    healthcare = load_interim("fr_healthcare")
    social = load_interim("fr_social_housing")
    grid = HexGrid(**world["grid"])
    proj = MapProjection(**world["projection"])
    communes = {c["code"]: c for c in bounds["communes"]}
    cells = {}
    for c in bounds["communes"]:
        if c.get("lon") is None: continue
        x, y = proj(c["lon"], c["lat"])
        cell = nearest_land(world, grid, x, y)
        if cell >= 0: cells[c["code"]] = cell

    house_rows = defaultdict(list); apartment_rows = defaultdict(list)
    for r in housing["rows"]:
        cell = cells.get(r["code"])
        if cell is None: continue
        if r["house_price"] and r["house_sales"]: house_rows[cell].append((r["house_price"], r["house_sales"]))
        if r["apartment_price"] and r["apartment_sales"]: apartment_rows[cell].append((r["apartment_price"], r["apartment_sales"]))
    house = weighted_series(grid.size, house_rows)
    apartment = weighted_series(grid.size, apartment_rows)

    health_vals = {}
    labels = {
        "gp": ("gp_access", "GP access", "🩺", "consultations / resident / year", "General-practitioner accessibility: accessible consultations, visits and teleconsultations per standardised resident per year."),
        "nurse": ("nurse_access", "Nurse access", "👩‍⚕️", "FTE / 100k residents", "Nurse accessibility in full-time equivalents per 100,000 standardised residents."),
        "dentist": ("dentist_access", "Dentist access", "🦷", "FTE / 100k residents", "Dentist accessibility in full-time equivalents per 100,000 standardised residents."),
        "midwife": ("midwife_access", "Midwife access", "🤱", "FTE / 100k residents", "Midwife accessibility in full-time equivalents per 100,000 standardised residents."),
    }
    social_rows = defaultdict(list)
    for code, value in social["rows"].items():
        cell = cells.get(code)
        if cell is not None:
            weight = max(1, round(communes.get(code, {}).get("population") or 1))
            social_rows[cell].append((value / 100, weight))
    social_share = weighted_series(grid.size, social_rows)

    for pid, prof in healthcare["professions"].items():
        rows = defaultdict(list)
        for code, value in prof["values"].items():
            cell = cells.get(code)
            if cell is None: continue
            weight = max(1, round(communes.get(code, {}).get("population") or 1))
            rows[cell].append((value, weight))
        health_vals[pid] = weighted_series(grid.size, rows)

    lenses = [
        lens("house_price", "House prices", "🏠", "euros / m²", "eur", house, "fr_housing",
             "Transaction-count-weighted mean of commune median house sale prices per m², DVF sales in 2024–2025. DVF excludes Alsace-Moselle and Mayotte."),
        lens("apartment_price", "Apartment prices", "🏢", "euros / m²", "eur", apartment, "fr_housing",
             "Transaction-count-weighted mean of commune median apartment sale prices per m², DVF sales in 2024–2025. Sparse rural coverage reflects few apartment sales."),
    ]
    lenses.append(lens("social_housing", "Social housing", "🏘️", "share of primary residences", "pct", social_share, "fr_social_housing",
                       "Population-weighted commune share of primary residences that are social housing in the 2023 RPLS. The published indicator excludes habitat spécifique and certain SEM stock and is not directly comparable with the legal SRU article-55 rate."))
    for pid, (lid, name, emoji, unit, desc) in labels.items():
        lenses.append(lens(lid, name, emoji, unit, "float", health_vals[pid], "fr_healthcare",
                           desc + " Commune APL values are population-weighted within each map hex; DREES coverage excludes Mayotte."))
    write_web("quality_life.json", {
        "version": 1, "vintage": "DVF 2024–2025 / DREES APL 2024 / RPLS 2023", "sources": ["fr_housing", "fr_healthcare", "fr_social_housing"],
        "group": {"id": "quality", "name": "Quality of life"}, "lenses": lenses,
    })


def check(web_dir):
    import json
    doc = json.loads((web_dir / "quality_life.json").read_text())
    assert len(doc["lenses"]) == 7
    n = len(json.loads((web_dir / "world.json").read_text())["owner"])
    assert all(len(l["values"]) == n for l in doc["lenses"])
    assert sum(v is not None for v in doc["lenses"][0]["values"]) > 2500
    return [("PASS", "quality_life.json: housing, healthcare and social-housing lenses")]
