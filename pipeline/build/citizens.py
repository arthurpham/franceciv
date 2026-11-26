"""Citizen mix for City View, from INSEE census tables."""

import json

from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web

REQUIRES = ["fr_insee_stats", "cities.json"]
PRODUCES = ["citizens.json"]

FIGURES = {"workforce": 20, "age": 10, "commute": 10, "education": 10, "nativity": 10}

GROUPS = {
    "workforce": [
        {"key": "farmer", "label": "Farmers"},
        {"key": "executive", "label": "Artisans, merchants and business owners"},
        {"key": "scholar", "label": "Managers and intellectual professions"},
        {"key": "clerk", "label": "Intermediate professions"},
        {"key": "service", "label": "Employees"},
        {"key": "maker", "label": "Workers"},
    ],
    "age": [
        {"key": "child", "label": "Under 15"}, {"key": "young", "label": "15–24"},
        {"key": "midlife", "label": "25–64"}, {"key": "elder", "label": "65 or older"},
    ],
    "commute": [
        {"key": "home", "label": "No transport / works at home"}, {"key": "walk", "label": "Walking"},
        {"key": "other", "label": "Bicycle or motorized two-wheeler"}, {"key": "drove_alone", "label": "Car, truck or van"},
        {"key": "transit", "label": "Public transport"},
    ],
    "education": [
        {"key": "less_than_hs", "label": "Below baccalauréat"}, {"key": "high_school", "label": "Baccalauréat"},
        {"key": "some_college", "label": "Short higher education (bac+2)"}, {"key": "bachelors", "label": "Bachelor-level degree (bac+3/4)"},
        {"key": "graduate", "label": "Graduate degree (bac+5 or more)"},
    ],
    "nativity": [
        {"key": "born_in_state", "label": "Not an immigrant"}, {"key": "foreign_born", "label": "Immigrant"},
    ],
}


def largest_remainder(counts, keys, n):
    total = sum(counts.get(k, 0) for k in keys)
    if total <= 0:
        return None
    raw = [counts.get(k, 0) / total * n for k in keys]
    out = [int(v) for v in raw]
    left = n - sum(out)
    order = sorted(range(len(keys)), key=lambda i: (-(raw[i] - int(raw[i])), i))
    for i in order[:left]:
        out[i] += 1
    return dict(zip(keys, out))


def pack(counts, keys, n, extra=None):
    raw_total = sum(counts.get(k, 0) for k in keys)
    if raw_total <= 0:
        return None
    rounded = {k: int(round(counts.get(k, 0))) for k in keys}
    shares = {k: round(counts.get(k, 0) / raw_total, 4) for k in keys}
    out = {
        "total": sum(rounded.values()),
        "counts": rounded,
        "shares": shares,
        "figures": largest_remainder(counts, keys, n),
    }
    if extra:
        out.update(extra)
    return out


def value(row, key):
    return row.get(key) or 0


def city_row(ds, geo, level="AAV2020"):
    age_src = ds["population_age"][level].get(geo, {})
    commute_src = ds["commuting"][level].get(geo, {})
    educ_src = ds["education"][level].get(geo, {})
    immi_src = ds["immigration"][level].get(geo, {})
    workforce_src = ds.get("workforce", {}).get(level, {}).get(geo, {})

    age_counts = {
        "child": value(age_src, "AGE=Y_LT15"),
        "young": value(age_src, "AGE=Y15T24"),
        "midlife": sum(value(age_src, f"AGE={a}") for a in ("Y25T39", "Y40T54", "Y55T64")),
        "elder": value(age_src, "AGE=Y_GE65"),
    }
    commute_counts = {
        "home": value(commute_src, "TRANS=1|AGE=Y_GE15|EMPSTA_ENQ=1"),
        "walk": value(commute_src, "TRANS=2|AGE=Y_GE15|EMPSTA_ENQ=1"),
        "other": value(commute_src, "TRANS=3|AGE=Y_GE15|EMPSTA_ENQ=1") + value(commute_src, "TRANS=4|AGE=Y_GE15|EMPSTA_ENQ=1"),
        "drove_alone": value(commute_src, "TRANS=5|AGE=Y_GE15|EMPSTA_ENQ=1"),
        "transit": value(commute_src, "TRANS=6|AGE=Y_GE15|EMPSTA_ENQ=1"),
    }
    education_counts = {
        "less_than_hs": sum(value(educ_src, f"AGE=Y_GE15|EDUC={e}") for e in ("001T100_RP", "200_RP", "300_RP")),
        "high_school": value(educ_src, "AGE=Y_GE15|EDUC=350T351_RP"),
        "some_college": value(educ_src, "AGE=Y_GE15|EDUC=500_RP"),
        "bachelors": value(educ_src, "AGE=Y_GE15|EDUC=600_RP"),
        "graduate": value(educ_src, "AGE=Y_GE15|EDUC=700_RP"),
    }
    nativity_counts = {
        "born_in_state": value(immi_src, "IMMI=0"),
        "foreign_born": value(immi_src, "IMMI=1"),
    }

    workforce_counts = workforce_mix(workforce_src)
    education_keys = [g["key"] for g in GROUPS["education"]]
    ed_total = sum(education_counts.values())
    higher = (education_counts["bachelors"] + education_counts["graduate"]) / ed_total if ed_total else None
    return {
        "workforce": pack(workforce_counts, [g["key"] for g in GROUPS["workforce"]], FIGURES["workforce"]),
        "age": pack(age_counts, [g["key"] for g in GROUPS["age"]], FIGURES["age"]),
        "commute": pack(commute_counts, [g["key"] for g in GROUPS["commute"]], FIGURES["commute"]),
        "education": pack(education_counts, education_keys, FIGURES["education"], {"bachelors_plus": round(higher, 4) if higher is not None else None}),
        "nativity": pack(nativity_counts, [g["key"] for g in GROUPS["nativity"]], FIGURES["nativity"], {"foreign_born": round(nativity_counts["foreign_born"] / sum(nativity_counts.values()), 4) if sum(nativity_counts.values()) else None}),
    }


def workforce_mix(src):
    # The resident-labour-force census table publishes the six broad PCS groups.
    # Use those official groups rather than inventing US-style occupation splits.
    pcs = {"farmer": ["1"], "executive": ["2"], "scholar": ["3"], "clerk": ["4"], "service": ["5"], "maker": ["6"]}
    out = {}
    for key, codes in pcs.items():
        out[key] = sum(v for k, v in src.items() if pcs_code(k) in codes)
    return out


def pcs_code(key):
    parts = dict(part.split("=", 1) for part in key.split("|") if "=" in part)
    if parts.get("EMPSTA_ENQ", "1") != "1" or parts.get("AGE", "Y15T64") != "Y15T64":
        return None
    return parts.get("PCS") or parts.get("CSP")


def specialists(city, national):
    out = []
    for row_id, groups in GROUPS.items():
        row, nat = city.get(row_id), national.get(row_id)
        if not row or not nat:
            continue
        for g in groups:
            key = g["key"]
            share, base = row["shares"].get(key), nat["shares"].get(key)
            if share is None or not base or (share < 0.01 and base < 0.01):
                continue
            ratio = share / base
            if ratio >= 1.5 or ratio <= 0.67:
                out.append({"row": row_id, "key": key, "share": round(share, 4), "national": round(base, 4), "ratio": round(ratio, 2)})
    high = sorted((s for s in out if s["ratio"] >= 1.5), key=lambda s: -s["ratio"])[:4]
    low = sorted((s for s in out if s["ratio"] <= 0.67), key=lambda s: s["ratio"])[:2]
    return high + low


def build():
    stats = load_interim("fr_insee_stats")
    ds = stats["datasets"]
    city_ids = [c["id"] for c in json.loads((WEB_DATA / "cities.json").read_text())]

    national = city_row(ds, "FM", "FRANCE")
    cities = {}
    for geo in city_ids:
        row = city_row(ds, geo)
        if any(row.values()):
            row["specialists"] = specialists(row, national)
            row["reliable"] = True
            cities[geo] = row
        else:
            cities[geo] = None
    write_web("citizens.json", {
        "version": 1,
        "vintage": f"INSEE census {stats['year']}",
        "year": stats["year"],
        "sources": ["fr_insee_stats"],
        "figures": FIGURES,
        "rows": {
            "workforce": "Employed residents by broad socio-professional category",
            "age": "Residents by broad age band",
            "commute": "Main transport mode of employed residents aged 15+",
            "education": "Highest diploma of non-enrolled residents aged 15+",
            "nativity": "Residents by immigrant status",
        },
        "groups": GROUPS,
        "rule": {"specialist_high": 1.5, "specialist_low": 0.67, "min_share": 0.01, "max_high": 4, "max_low": 2,
                 "text": "Standout citizens are categories at least 1.5 times the metropolitan-France share; underrepresented categories are at most two-thirds of it."},
        "national": national,
        "cities": cities,
    })
    print(f"    {len(cities)} cities")


def check(web_dir):
    path = web_dir / "citizens.json"
    if not path.exists():
        return [("FAIL", "citizens.json missing")]
    data = json.loads(path.read_text())
    errors = []
    groups = data.get("groups") or {}
    figures = data.get("figures") or {}
    if set(groups) != set(FIGURES):
        errors.append("group rows do not match the expected five rows")
    for row_id, n in FIGURES.items():
        if figures.get(row_id) != n:
            errors.append(f"{row_id}: figure count is {figures.get(row_id)!r}, expected {n}")

    def validate_row(city_id, row, row_id):
        keys = [g["key"] for g in groups.get(row_id, [])]
        prefix = f"{city_id}/{row_id}"
        if row is None:
            errors.append(f"{prefix}: missing row")
            return
        counts, shares, figs = row.get("counts"), row.get("shares"), row.get("figures")
        if not isinstance(counts, dict) or set(counts) != set(keys):
            errors.append(f"{prefix}: count keys differ from groups")
            return
        if not all(isinstance(v, int) and v >= 0 for v in counts.values()):
            errors.append(f"{prefix}: counts must be non-negative integers")
        if row.get("total") != sum(counts.values()):
            errors.append(f"{prefix}: total does not equal the sum of counts")
        if not isinstance(figs, dict) or set(figs) != set(keys) or sum(figs.values()) != FIGURES[row_id]:
            errors.append(f"{prefix}: figures do not sum to {FIGURES[row_id]}")
        if not isinstance(shares, dict) or set(shares) != set(keys) or not all(0 <= v <= 1 for v in shares.values()):
            errors.append(f"{prefix}: shares missing, out of range or keyed incorrectly")
        elif abs(sum(shares.values()) - 1) > 0.01:
            errors.append(f"{prefix}: shares do not sum to 1")

    national = data.get("national")
    if not isinstance(national, dict):
        errors.append("national row missing")
    else:
        for row_id in FIGURES:
            validate_row("national", national.get(row_id), row_id)

    city_ids = [c["id"] for c in json.loads((web_dir / "cities.json").read_text())]
    cities = data.get("cities") or {}
    missing_files = [c for c in city_ids if c not in cities]
    if missing_files:
        errors.append(f"cities missing entries: {', '.join(missing_files[:5])}")
    present = 0
    for city_id in city_ids:
        row = cities.get(city_id)
        if row is None:
            continue
        present += 1
        for row_id in FIGURES:
            validate_row(city_id, row.get(row_id), row_id)
        for sp in row.get("specialists") or []:
            if sp.get("row") not in groups or sp.get("key") not in {g["key"] for g in groups.get(sp.get("row"), [])}:
                errors.append(f"{city_id}: specialist references an unknown row/key")
    if present < len(city_ids) * 0.95:
        errors.append(f"only {present}/{len(city_ids)} cities have census rows")
    if errors:
        return [("FAIL", "; ".join(errors[:4]) + (f" … (+{len(errors) - 4})" if len(errors) > 4 else ""))]
    return [("PASS", f"citizens.json: {present}/{len(city_ids)} cities, 5 rows each, counts and figures consistent")]
