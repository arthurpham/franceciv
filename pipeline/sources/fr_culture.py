"""French museum attendance and university enrolment used for culture wonders."""

from __future__ import annotations

import csv

from ..core.source import Source, SourceInfo

MUSEUM_ATTENDANCE_URL = "https://ministere-culture.s3.sbg.io.cloud.ovh.net/FREQ_MUSEES/ENTREES_ET_CATEGORIES_DE_PUBLIC.csv"
MUSEOFILE_URL = "https://ministere-culture.s3.sbg.io.cloud.ovh.net/POP/museofile.csv"
SISE_URL = "https://data.enseignementsup-recherche.gouv.fr/api/explore/v2.1/catalog/datasets/fr-esr-statistiques-sur-les-effectifs-d-etudiants-inscrits-par-etablissement/exports/csv?lang=fr&timezone=Europe%2FParis&use_labels=true&delimiter=%3B"


def integer(value):
    try:
        return int(str(value or "").strip())
    except ValueError:
        return None


class FrenchCulture(Source):
    info = SourceInfo(
        id="fr_culture",
        title="Museum attendance and university enrolment",
        publisher="ministère de la Culture / MESRI",
        homepage="https://www.data.gouv.fr/datasets/frequentation-des-musees-de-france-1",
        license="Licence Ouverte / Open Licence 2.0",
        description="Annual visitor counts for Musées de France, the Muséofile museum directory and SISE enrolment "
        "by public higher-education establishment. Multi-site museum attendance rows are summed for their shared Muséofile "
        "identifier after deduplicating repeated site rows. University geography is the administrative headquarters "
        "commune, not the footprint of every campus.",
        used_for=["Museum and university wonders"],
    )

    def fetch(self, force=False):
        self.download(MUSEUM_ATTENDANCE_URL, "museum-attendance.csv", force=force)
        self.download(MUSEOFILE_URL, "museofile.csv", force=force)
        self.download(SISE_URL, "sise-establishments.csv", force=force)

    def museums(self):
        directory = {}
        with open(self.raw_dir / "museofile.csv", encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter="|"):
                coords = (row.get("Coordonnees") or "").split(",")
                if len(coords) != 2:
                    continue
                try:
                    lat, lon = float(coords[0]), float(coords[1])
                except ValueError:
                    continue
                directory[row["Identifiant"]] = {
                    "id": row["Identifiant"], "name": row.get("Nom_officiel") or row.get("AUTNOM") or row["Identifiant"],
                    "city": row.get("Ville"), "lat": lat, "lon": lon, "domain": row.get("Domaine_thematique"),
                    "url": row.get("URL"),
                }
        # The attendance file is keyed by physical site (`IDPatrimostat`), while several physical
        # sites can share one museum institution (`IDMuseofile`). Aggregate distinct sites for the
        # institution's latest year. A very small number of corrected extracts repeat the same
        # institution/year/site row; keep the larger value instead of double-counting it.
        site_rows = {}
        years = set()
        with open(self.raw_dir / "museum-attendance.csv", encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter=";"):
                year, total = integer(row.get("annee")), integer(row.get("total"))
                mid, site = row.get("IDMuseofile"), row.get("IDPatrimostat")
                if not year or total is None or not mid or not site:
                    continue
                years.add(year)
                key = (mid, year, site)
                if total >= site_rows.get(key, {}).get("visits", -1):
                    site_rows[key] = {"visits": total, "closed": row.get("ferme") == "OUI"}
        by_museum_year = {}
        for (mid, year, _site), row in site_rows.items():
            by_museum_year.setdefault(mid, {}).setdefault(year, []).append(row)
        rows = []
        for mid, annual in by_museum_year.items():
            year = max(annual)
            entries = annual[year]
            stats = {
                "visits": sum(row["visits"] for row in entries),
                "year": year,
                "closed": all(row["closed"] for row in entries),
                "sites": len(entries),
            }
            d = directory.get(mid)
            if d and not stats["closed"] and stats["visits"] > 0:
                rows.append({**d, **stats})
        rows.sort(key=lambda x: x["visits"], reverse=True)
        return rows, max(years) if years else None

    def universities(self):
        rows = []
        years = set()
        with open(self.raw_dir / "sise-establishments.csv", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f, delimiter=";"):
                year = row.get("Année universitaire")
                if year != "2024-25" or not (row.get("Typologie de l'établissement") or "").startswith("Université"):
                    continue
                students = integer(row.get("Nombre total d'étudiants inscrits (inscriptions principales et secondes) y compris doubles inscriptions CPGE"))
                commune = row.get("etablissement_code_commune")
                if not students or not commune:
                    continue
                years.add(year)
                code = commune.zfill(5)
                # SISE uses municipal-arrondissement codes for the three largest cities; the map's
                # commune boundaries use their parent commune codes.
                if code.startswith("751"):
                    code = "75056"
                elif code.startswith("132"):
                    code = "13055"
                elif code.startswith("693"):
                    code = "69123"
                rows.append({
                    "id": row.get("Identifiant interne de l'établissement") or row["Établissement"],
                    "name": row["Établissement"], "students": students, "year": 2024,
                    "commune": code, "seat": row.get("Commune du siège de l’établissement"),
                    "type": row.get("Typologie de l'établissement"),
                })
        rows.sort(key=lambda x: x["students"], reverse=True)
        return rows, 2024 if years else None

    def process(self):
        museums, museum_year = self.museums()
        universities, university_year = self.universities()
        print(f"    {len(museums)} museums with attendance; {len(universities)} universities in 2024-25")
        return {
            "vintage": f"Musées de France attendance through {museum_year}; SISE 2024-25",
            "_files": ["museum-attendance.csv", "museofile.csv", "sise-establishments.csv"],
            "museums": museums[:30], "universities": universities[:30],
            "years": {"museums": museum_year, "universities": university_year},
        }
