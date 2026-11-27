"""Scheduled GTFS stop-call frequency from consolidated regional feeds."""

import csv
import json
import zipfile
from collections import Counter
from datetime import date, timedelta
from io import TextIOWrapper

from ..core.source import Source, SourceInfo

API = "https://transport.data.gouv.fr/api/datasets"
RESOURCES = {
    80921: "ile_de_france",
    78904: "auvergne_rhone_alpes",
    82321: "nouvelle_aquitaine",
    83634: "grand_est",
    79818: "pays_de_la_loire",
    81559: "bretagne",
    81942: "normandie",
    83521: "centre_val_de_loire",
}


def ymd(s):
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def iso(s):
    return date.fromisoformat(s)


def next_wednesday(d):
    return d + timedelta(days=(2 - d.weekday()) % 7 or 7)


def rows(zf, name):
    with zf.open(name) as raw:
        yield from csv.reader(TextIOWrapper(raw, encoding="utf-8-sig", newline=""))


def active_services(zf, target):
    active = set()
    if "calendar.txt" in zf.namelist():
        it = rows(zf, "calendar.txt")
        head = next(it); ix = {k: i for i, k in enumerate(head)}
        wd = target.strftime("%A").lower()
        for r in it:
            if len(r) < len(head) or r[ix[wd]] != "1":
                continue
            if ymd(r[ix["start_date"]]) <= target <= ymd(r[ix["end_date"]]):
                active.add(r[ix["service_id"]])
    if "calendar_dates.txt" in zf.namelist():
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


class FrenchTransitFrequency(Source):
    info = SourceInfo(
        id="fr_transit_frequency",
        title="Consolidated regional GTFS scheduled service frequency",
        publisher="transport.data.gouv.fr and regional transport-data publishers",
        homepage="https://transport.data.gouv.fr/",
        license="Various open licences catalogued by transport.data.gouv.fr",
        description="Experimental true scheduled-service extraction. It counts stop calls in GTFS stop_times for one representative Wednesday after applying calendar and calendar_dates exceptions. Coverage currently uses consolidated regional feeds for Île-de-France, Auvergne-Rhône-Alpes, Nouvelle-Aquitaine, Grand Est, Pays de la Loire, Bretagne, Normandie and Centre-Val de Loire; other regions are not yet covered.",
        used_for=["Scheduled transit-frequency lens"],
    )

    def catalog(self):
        return json.loads(self.download(API, "transport_catalog.json").read_text())

    def resources(self):
        found = {}
        for d in self.catalog():
            for r in d.get("resources", []):
                if r.get("id") in RESOURCES and r.get("original_url"):
                    found[r["id"]] = r
        missing = sorted(set(RESOURCES) - set(found))
        if missing:
            raise ValueError(f"missing GTFS resources in transport catalog: {missing}")
        return found

    def fetch(self, force=False):
        for rid, r in self.resources().items():
            self.download(r["original_url"], f"gtfs_{rid}.zip", force=force, expect_binary=True)

    def process(self):
        meta = self.resources()
        starts = [iso(r["metadata"]["start_date"]) for r in meta.values() if r.get("metadata", {}).get("start_date")]
        ends = [iso(r["metadata"]["end_date"]) for r in meta.values() if r.get("metadata", {}).get("end_date")]
        base = max(starts) + timedelta(days=7)
        target = next_wednesday(base)
        if ends and target > min(ends):
            target = next_wednesday(max(starts))
        out = []
        feed_stats = {}
        for rid, slug in RESOURCES.items():
            path = self.raw_dir / f"gtfs_{rid}.zip"
            with zipfile.ZipFile(path) as zf:
                active = active_services(zf, target)
                it = rows(zf, "trips.txt")
                head = next(it); ix = {k: i for i, k in enumerate(head)}
                active_trips = {r[ix["trip_id"]] for r in it if len(r) >= len(head) and r[ix["service_id"]] in active}
                counts = Counter()
                it = rows(zf, "stop_times.txt")
                head = next(it); ix = {k: i for i, k in enumerate(head)}
                ti, si = ix["trip_id"], ix["stop_id"]
                for r in it:
                    if len(r) > max(ti, si) and r[ti] in active_trips:
                        counts[r[si]] += 1
                it = rows(zf, "stops.txt")
                head = next(it); ix = {k: i for i, k in enumerate(head)}
                stop_count = 0
                for r in it:
                    if len(r) < len(head) or (r[ix.get("location_type", 0)] or "0") not in {"0", ""}:
                        continue
                    try:
                        lat, lon = float(r[ix["stop_lat"]]), float(r[ix["stop_lon"]])
                    except (ValueError, TypeError, KeyError):
                        continue
                    stop_count += 1
                    out.append({"lat": lat, "lon": lon, "calls": counts.get(r[ix["stop_id"]], 0), "feed": slug})
                feed_stats[slug] = {"stops": stop_count, "active_trips": len(active_trips), "stop_calls": sum(counts.values())}
                print(f"    {slug}: {len(active_trips)} active trips, {sum(counts.values())} stop calls")
        print(f"    {len(out)} stops in consolidated feeds; target Wednesday {target}")
        if len(out) < 100_000 or sum(r["calls"] for r in out) < 500_000:
            raise ValueError("unexpected GTFS frequency totals")
        return {"vintage": f"Scheduled stop calls on {target} from current consolidated GTFS feeds", "target_date": target.isoformat(), "_files": ["transport_catalog.json"] + [f"gtfs_{r}.zip" for r in RESOURCES], "rows": out, "feed_stats": feed_stats}
