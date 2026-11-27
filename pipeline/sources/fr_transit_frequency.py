"""Scheduled GTFS stop-call frequency from consolidated and supplemental regional feeds."""

import csv
import hashlib
import json
import re
import unicodedata
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from datetime import date, timedelta
from io import TextIOWrapper

from ..core.source import Source, SourceInfo

API = "https://transport.data.gouv.fr/api/datasets"
GEO_API = "https://geo.api.gouv.fr/communes?fields=nom,code,codeDepartement,codeRegion,epci&format=json&geometry=centre"
CONSOLIDATED = {
    80921: "ile_de_france",
    78904: "auvergne_rhone_alpes",
    82321: "nouvelle_aquitaine",
    83634: "grand_est",
    79818: "pays_de_la_loire",
    81559: "bretagne",
    81942: "normandie",
    83521: "centre_val_de_loire",
}
MISSING_REGIONS = {"27", "32", "76", "93", "94", "01", "02", "03", "04", "06"}
GENERIC_NETWORK_WORDS = {"reseau", "network", "bus", "line", "lines", "ligne", "lignes", "transport", "transports", "mobilite", "mobilities", "gtfs", "urbain", "interurbain", "scolaire", "les", "des", "de", "du", "la", "le", "et"}


def norm_network(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def network_tokens(s):
    return {x for x in norm_network(s).split() if len(x) > 2 and x not in GENERIC_NETWORK_WORDS}


def network_key(s):
    filler = {"de", "du", "la", "le", "les", "des", "et", "reseau", "network"}
    tokens = sorted(x for x in norm_network(s).split() if x not in filler)
    return " ".join(tokens) if tokens else norm_network(s)


def ymd(s):
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def iso(s):
    return date.fromisoformat(s)


def next_wednesday(d):
    return d + timedelta(days=(2 - d.weekday()) % 7 or 7)


def wednesday_on_or_after(d):
    return d + timedelta(days=(2 - d.weekday()) % 7)


def wednesday_on_or_before(d):
    return d - timedelta(days=(d.weekday() - 2) % 7)


def member(zf, name):
    if name in zf.namelist():
        return name
    return next((n for n in zf.namelist() if n.endswith("/" + name)), None)


def rows(zf, name):
    real = member(zf, name)
    if not real:
        raise KeyError(name)
    with zf.open(real) as raw:
        yield from csv.reader(TextIOWrapper(raw, encoding="utf-8-sig", newline=""))


def active_services(zf, target):
    active = set()
    if member(zf, "calendar.txt"):
        it = rows(zf, "calendar.txt")
        head = next(it); ix = {k: i for i, k in enumerate(head)}
        wd = target.strftime("%A").lower()
        for r in it:
            if len(r) < len(head) or r[ix[wd]] != "1":
                continue
            if ymd(r[ix["start_date"]]) <= target <= ymd(r[ix["end_date"]]):
                active.add(r[ix["service_id"]])
    if member(zf, "calendar_dates.txt"):
        it = rows(zf, "calendar_dates.txt")
        head = next(it); ix = {k: i for i, k in enumerate(head)}
        wanted = target.strftime("%Y%m%d")
        for r in it:
            if len(r) < len(head) or r[ix["date"]] != wanted:
                continue
            if r[ix["exception_type"]] == "1":
                active.add(r[ix["service_id"]])
            elif r[ix["exception_type"]] == "2":
                active.discard(r[ix["service_id"]])
    return active

def parse_time_seconds(value):
    try:
        hours, minutes, seconds = (int(x) for x in value.split(":"))
        return hours * 3600 + minutes * 60 + seconds
    except (ValueError, AttributeError):
        return None


def parse_feed(zf, cfg, target):
    if not all(member(zf, n) for n in ("stops.txt", "trips.txt", "stop_times.txt")):
        raise ValueError("missing core GTFS files")
    md = cfg.get("metadata") or {}
    feed_target = target
    if md.get("start_date") and feed_target < iso(md["start_date"]):
        feed_target = wednesday_on_or_after(iso(md["start_date"]))
    if md.get("end_date") and feed_target > iso(md["end_date"]):
        feed_target = wednesday_on_or_before(iso(md["end_date"]))
    active = active_services(zf, feed_target)

    it = rows(zf, "trips.txt")
    head = next(it)
    ix = {k: i for i, k in enumerate(head)}
    if "trip_id" not in ix or "service_id" not in ix:
        raise ValueError("trips.txt missing trip_id or service_id")
    active_trips = {r[ix["trip_id"]] for r in it if len(r) >= len(head) and r[ix["service_id"]] in active}

    it = rows(zf, "stops.txt")
    head = next(it)
    ix = {k: i for i, k in enumerate(head)}
    if not {"stop_id", "stop_lat", "stop_lon"} <= set(ix):
        raise ValueError("stops.txt missing stop coordinates")
    stop_records = []
    stop_identity = {}
    lt = ix.get("location_type")
    for r in it:
        if len(r) < len(head):
            continue
        try:
            lat, lon = float(r[ix["stop_lat"]]), float(r[ix["stop_lon"]])
        except (ValueError, TypeError, IndexError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        stop_id = r[ix["stop_id"]]
        location_type = (r[lt] or "0") if lt is not None else "0"
        stop_records.append((stop_id, lat, lon, location_type))
        stop_identity[stop_id] = f"{lat:.4f},{lon:.4f}"

    # frequency-based GTFS trips are templates. Expand them by their published headway window;
    # otherwise cable cars and very frequent shuttles are counted as a single vehicle per template.
    multipliers = {}
    if member(zf, "frequencies.txt"):
        it = rows(zf, "frequencies.txt")
        head = next(it)
        ix = {k: i for i, k in enumerate(head)}
        if {"trip_id", "start_time", "end_time", "headway_secs"} <= set(ix):
            for r in it:
                if len(r) < len(head) or r[ix["trip_id"]] not in active_trips:
                    continue
                start, end = parse_time_seconds(r[ix["start_time"]]), parse_time_seconds(r[ix["end_time"]])
                try:
                    headway = int(r[ix["headway_secs"]])
                except (ValueError, TypeError):
                    continue
                if start is None or end is None or end <= start or headway <= 0:
                    continue
                multipliers[r[ix["trip_id"]]] = multipliers.get(r[ix["trip_id"]], 0) + max(1, (end - start + headway - 1) // headway)

    counts = Counter()
    trip_signatures = {}
    it = rows(zf, "stop_times.txt")
    head = next(it)
    ix = {k: i for i, k in enumerate(head)}
    if "trip_id" not in ix or "stop_id" not in ix:
        raise ValueError("stop_times.txt missing trip_id or stop_id")
    ti, si = ix["trip_id"], ix["stop_id"]
    ai, di = ix.get("arrival_time"), ix.get("departure_time")
    needed = max(ti, si, ai or 0, di or 0)
    for r in it:
        if len(r) <= needed:
            continue
        trip_id, stop_id = r[ti], r[si]
        if trip_id in active_trips:
            counts[stop_id] += multipliers.get(trip_id, 1)
        # Coordinates make the signature feed-independent: a republished copy is detected even if
        # its local stop identifiers differ, while equally numbered stops in unrelated networks do not collide.
        identity = stop_identity.get(stop_id, "id:" + stop_id)
        event = (identity + "\x1f" + (r[ai] if ai is not None else "") + "\x1f" + (r[di] if di is not None else "")).encode()
        key = (zlib.crc32(event) << 32) | zlib.adler32(event)
        acc, n = trip_signatures.get(trip_id, (0, 0))
        trip_signatures[trip_id] = ((acc + key) & 0xFFFFFFFFFFFFFFFF, n + 1)
    signatures = set(trip_signatures.values())

    rows_out = []
    for stop_id, lat, lon, location_type in stop_records:
        calls = counts.get(stop_id, 0)
        if location_type not in {"0", ""} and not calls:
            continue
        rows_out.append({"lat": lat, "lon": lon, "calls": calls, "feed": cfg["slug"], "kind": cfg["kind"]})
    expanded_trips = sum(multipliers.get(trip_id, 1) for trip_id in active_trips)
    stats = {"stops": len(rows_out), "active_trips": len(active_trips), "frequency_expanded_trips": expanded_trips, "stop_calls": sum(counts.values()), "kind": cfg["kind"], "target_date": feed_target.isoformat()}
    return rows_out, stats, signatures


class FrenchTransitFrequency(Source):
    info = SourceInfo(
        id="fr_transit_frequency",
        title="National GTFS scheduled service frequency",
        publisher="transport.data.gouv.fr and transport-data publishers",
        homepage="https://transport.data.gouv.fr/",
        license="Various open licences catalogued by transport.data.gouv.fr",
        description="Experimental true scheduled-service extraction. It counts stop calls in GTFS stop_times for one representative Wednesday after applying calendar/calendar_dates exceptions and expanding frequency-based trips across their headway windows. Consolidated regional feeds are used where available. Supplemental feeds are selected for regions without consolidated coverage using catalog covered_area metadata. Aggregate resources are preferred where network metadata shows duplication, exact duplicate zip snapshots and content-duplicate feed publications are skipped, expired feeds are excluded, and overlapping supplemental stops inside consolidated regions are suppressed during map construction; residual catalog inconsistencies can remain.",
        used_for=["Scheduled transit-frequency lens"],
    )

    def catalog(self):
        return json.loads(self.download(API, "transport_catalog.json").read_text())

    def commune_reference(self):
        return json.loads(self.download(GEO_API, "communes-epci-reference.json").read_text())

    def geography_lookup(self):
        communes = self.commune_reference()
        creg = {c["code"]: c["codeRegion"] for c in communes}
        dreg = {c["codeDepartement"]: c["codeRegion"] for c in communes}
        ereg = {}
        for c in communes:
            code = (c.get("epci") or {}).get("code")
            if code:
                ereg.setdefault(code, set()).add(c["codeRegion"])
        return creg, dreg, ereg

    def covered_regions(self, dataset, creg, dreg, ereg):
        out = set()
        for a in dataset.get("covered_area") or []:
            typ, code = a.get("type"), str(a.get("insee") or "")
            if typ == "region":
                out.add(code)
            elif typ == "departement":
                out.add(dreg.get(code, ""))
            elif typ == "commune":
                out.add(creg.get(code, ""))
            elif typ == "epci":
                out.update(ereg.get(code, set()))
        out.discard("")
        return out

    def consolidated_reference_date(self):
        starts = []
        for d in self.catalog():
            for r in d.get("resources", []):
                if r.get("id") in CONSOLIDATED and (r.get("metadata") or {}).get("start_date"):
                    starts.append(iso(r["metadata"]["start_date"]))
        return max(starts) if starts else date.today()

    def select_resources(self):
        creg, dreg, ereg = self.geography_lookup()
        reference_date = self.consolidated_reference_date()
        per_dataset = []
        for d in self.catalog():
            regions = self.covered_regions(d, creg, dreg, ereg)
            if not (regions & MISSING_REGIONS):
                continue
            rs = []
            for r in d.get("resources", []):
                stats = (r.get("metadata") or {}).get("stats") or {}
                end_date = ((r.get("metadata") or {}).get("end_date"))
                currently_valid = not end_date or iso(end_date) >= reference_date
                if r.get("format") == "GTFS" and r.get("original_url") and r.get("is_available", True) and stats.get("trips_count") and currently_valid:
                    networks = [network_key(x) for x in ((r.get("metadata") or {}).get("networks") or []) if norm_network(x)]
                    rs.append({"resource": r, "networks": sorted(set(networks)), "trips": stats.get("trips_count") or 0, "regions": regions, "dataset": d["title"]})
            if rs:
                per_dataset.append(rs)

        group_tokens = []
        for rs in per_dataset:
            tokens = set()
            for c in rs:
                for n in c["networks"]:
                    tokens |= network_tokens(n)
            group_tokens.append(tokens)

        candidates = []
        for group_index, rs in enumerate(per_dataset):
            multi = [x for x in rs if len(x["networks"]) > 1]
            selected = rs
            if multi and len(rs) > 1:
                # A multi-network resource in a dataset that also publishes granular feeds is normally
                # an aggregate of those feeds. Prefer the single aggregate, except when its brands are
                # already supplied by external regional feeds; then use the granular local resources.
                a = max(multi, key=lambda x: x["trips"])
                a_tokens = set().union(*(network_tokens(n) for n in a["networks"]))
                outside_tokens = set().union(*(t for i, t in enumerate(group_tokens) if i != group_index)) if len(group_tokens) > 1 else set()
                overlap = bool(a_tokens & outside_tokens & {"zou", "sncf", "ter"})
                selected = [x for x in rs if x is not a] if overlap else [a]
            candidates.extend(selected)

        # Across datasets, exact duplicate specific network labels indicate overlapping publications.
        # Single-brand labels such as liO are not sufficient evidence: different local or sectoral
        # feeds can carry the same regional brand while operating distinct routes. Content-duplicate
        # detection in process() handles exact republished trips for those cases.
        candidates.sort(key=lambda x: -x["trips"])
        claimed, chosen = set(), []
        for c in candidates:
            ns = {n for n in c["networks"] if len(n.split()) > 1}
            if ns and ns <= claimed:
                continue
            chosen.append(c)
            claimed |= ns
        out = {rid: {"slug": slug, "kind": "consolidated", "networks": []} for rid, slug in CONSOLIDATED.items()}
        for c in chosen:
            r = c["resource"]
            if r["id"] not in out:
                slug = re.sub(r"[^a-z0-9]+", "_", unicodedata.normalize("NFKD", c["dataset"]).encode("ascii", "ignore").decode().lower()).strip("_")[:60]
                out[r["id"]] = {"slug": f"supplement_{r['id']}_{slug}", "kind": "supplement", "networks": c["networks"], "regions": sorted(c["regions"]), "dataset": c["dataset"]}
        return out

    def resources(self):
        selected = self.select_resources()
        found = {}
        wanted = set(selected)
        for d in self.catalog():
            for r in d.get("resources", []):
                if r.get("id") in wanted and r.get("original_url"):
                    found[r["id"]] = {**r, **selected[r["id"]]}
        missing = sorted(set(CONSOLIDATED) - set(found))
        if missing:
            raise ValueError(f"missing consolidated GTFS resources in transport catalog: {missing}")
        return found

    def fetch(self, force=False):
        if force:
            self.download(API, "transport_catalog.json", force=True)
            self.download(GEO_API, "communes-epci-reference.json", force=True)
        failed = []

        def one(item):
            rid, r = item
            try:
                self.download(r["original_url"], f"gtfs_{rid}.zip", force=force, expect_binary=True, require_public=True)
                return None
            except Exception as exc:
                return (rid, str(exc))

        items = list(self.resources().items())
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(one, item) for item in items]
            for future in as_completed(futures):
                error = future.result()
                if error:
                    if error[0] in CONSOLIDATED:
                        raise RuntimeError(f"consolidated GTFS download failed: {error[0]}: {error[1]}")
                    failed.append(error)
        if failed:
            print(f"    warning: {len(failed)} supplemental GTFS downloads unavailable; coverage reduced")

    def process(self):
        meta = self.resources()
        reference_meta = [r for rid, r in meta.items() if rid in CONSOLIDATED]
        starts = [iso(r["metadata"]["start_date"]) for r in reference_meta if r.get("metadata", {}).get("start_date")]
        ends = [iso(r["metadata"]["end_date"]) for r in reference_meta if r.get("metadata", {}).get("end_date")]
        base = max(starts) + timedelta(days=7)
        target = next_wednesday(base)
        if ends and target > min(ends):
            target = next_wednesday(max(starts))
        parsed, skipped_missing, malformed = {}, 0, 0
        seen_hashes = {}
        for rid, cfg in sorted(meta.items()):
            path = self.raw_dir / f"gtfs_{rid}.zip"
            if not path.exists():
                if rid in CONSOLIDATED:
                    raise FileNotFoundError(f"missing required consolidated GTFS archive: {path.name}")
                skipped_missing += 1
                continue
            slug = cfg["slug"]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in seen_hashes:
                print(f"    {slug}: exact duplicate of {seen_hashes[digest]}, skipped")
                continue
            seen_hashes[digest] = slug
            try:
                with zipfile.ZipFile(path) as zf:
                    feed_rows, stats, signatures = parse_feed(zf, {**cfg, "slug": slug}, target)
            except Exception as exc:
                if rid in CONSOLIDATED:
                    raise
                malformed += 1
                print(f"    warning: skipped malformed supplemental feed {slug}: {exc}")
                continue
            parsed[slug] = {"rows": feed_rows, "stats": stats, "signatures": signatures, "kind": cfg["kind"], "rid": rid}

        owners = {}
        for slug, feed in parsed.items():
            for signature in feed["signatures"]:
                owners.setdefault(signature, set()).add(slug)
        overlap = Counter()
        for slugs in owners.values():
            if len(slugs) > 1:
                ordered = sorted(slugs)
                for i, a in enumerate(ordered):
                    for b in ordered[i + 1:]:
                        overlap[(a, b)] += 1
        duplicate_map = {}
        for (a, b), shared in overlap.items():
            fa, fb = parsed[a], parsed[b]
            # A feed whose trips are overwhelmingly contained in another publication is a duplicate
            # publication, not additional service. Consolidated feeds win over supplemental copies;
            # otherwise the larger feed is retained.
            if fa["kind"] != fb["kind"]:
                victim, keeper = (a, b) if fa["kind"] == "supplement" else (b, a)
            elif len(fa["signatures"]) != len(fb["signatures"]):
                victim, keeper = (a, b) if len(fa["signatures"]) < len(fb["signatures"]) else (b, a)
            else:
                victim, keeper = max(a, b), min(a, b)
            victim_size = len(parsed[victim]["signatures"])
            if victim_size and shared / victim_size >= 0.8:
                duplicate_map[victim] = keeper

        out, feed_stats, used_rids = [], {}, set()
        for slug, feed in parsed.items():
            if slug in duplicate_map:
                print(f"    {slug}: {len(feed['rows'])} stops suppressed as content duplicate of {duplicate_map[slug]}")
                continue
            out.extend(feed["rows"])
            feed_stats[slug] = feed["stats"]
            used_rids.add(feed["rid"])
        print(f"    {len(out)} stops in {len(feed_stats)} feeds; target Wednesday {target}; skipped {skipped_missing} unavailable, {malformed} malformed and {len(duplicate_map)} content-duplicate feeds")
        if len(out) < 150_000 or sum(r["calls"] for r in out) < 1_000_000:
            raise ValueError("unexpected GTFS frequency totals")
        return {"vintage": f"Scheduled stop calls around {target} from current GTFS feeds", "target_date": target.isoformat(), "_files": ["transport_catalog.json", "communes-epci-reference.json"] + [f"gtfs_{rid}.zip" for rid in sorted(used_rids)], "rows": out, "feed_stats": feed_stats, "suppressed_duplicate_feeds": duplicate_map, "feed_target_dates": sorted({v["target_date"] for v in feed_stats.values()})}
