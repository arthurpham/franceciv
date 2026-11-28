#!/usr/bin/env python3
"""Refresh the draft French UI dictionary.

Existing translations are preserved, so manual corrections in web/data/i18n_fr.json
survive subsequent runs. Newly discovered strings are translated with Google's
public translate endpoint as a first-draft aid; review visible terminology before release.
"""

import html
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "data" / "i18n_fr.json"
SEPARATOR = "\nZXQJSEP\n"
ENDPOINT = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=fr&dt=t&q="

KEYBOARD = {
    "Alt", "Arrow", "ArrowDown", "ArrowLeft", "ArrowRight", "ArrowUp", "Backspace",
    "Ctrl", "Delete", "End", "Enter", "Esc", "Escape", "Home", "Shift", "Space", "Tab",
}

# Terminology that should remain stable even if the machine draft chooses a literal wording.
MANUAL_OVERRIDES = {
    "Lenses": "Couches",
    "Lens": "Couche",
    "Map layers": "Couches de la carte",
    "Choose a lens": "Choisir une couche",
    "Lens legend": "Légende de la couche",
    "All lenses (L cycles)": "Toutes les couches (L pour changer)",
    "Environment depth": "Milieu naturel",
    "Hazards": "Risques",
    "Prosperity": "Prospérité",
    "Built-up": "Artificialisé",
    "Housing-driven land take": "Artificialisation liée au logement",
    "Commuting out": "Migrations pendulaires sortantes",
    "Le Pen vote 2022": "Vote Le Pen 2022",
    "no data": "aucune donnée",
}

SKIP_SUBSTRINGS = (
    "http", "data/", "rgba", "var(--", "px ", "em ", "rem ", "${",
    "return ", "function ", "=>", "querySelector", "addEventListener", "className", "aria-",
    "/js/", ".json", "image/", "rgb(", "hsl(", "matrix", "translate", "scale(",
    "viewBox", "xmlns", "font", "Palatino", "Georgia", "serif", "#lens-", "#topbar", "prefers-reduced-motion",
)


def add_text(strings, value):
    if not isinstance(value, str):
        return
    value = html.unescape(value).strip()
    if value and re.search(r"[A-Za-zÀ-ÿ]", value):
        strings.add(value)


def collect_data_strings(strings):
    for path in (ROOT / "web" / "data").glob("*.json"):
        if path.name.startswith("i18n_"):
            continue
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for lens in data.get("lenses", []):
            if isinstance(lens, dict):
                for key in ("name", "unit", "description"):
                    add_text(strings, lens.get(key))
        for group in data.get("groups", []):
            if isinstance(group, dict):
                add_text(strings, group.get("name"))
        if isinstance(data.get("group"), dict):
            add_text(strings, data["group"].get("name"))
        for key in ("items", "wonders", "rules", "sources", "types"):
            rows = data.get(key, [])
            if isinstance(rows, dict):
                rows = rows.values()
            for row in rows:
                if isinstance(row, dict):
                    for field in ("name", "short", "text", "title", "description"):
                        add_text(strings, row.get(field))
        add_text(strings, data.get("title"))
        add_text(strings, data.get("description"))


def collect_html_strings(strings):
    text = (ROOT / "web" / "index.html").read_text()
    for value in re.findall(r'(?:placeholder|aria-label|title)="([^"]+)"', text):
        add_text(strings, value)
    for value in re.findall(r">([^<>{}]+)<", text):
        add_text(strings, value)


def plausible_ui_literal(value):
    if len(value) < 2 or len(value) > 180 or not re.search(r"[A-Za-zÀ-ÿ]", value):
        return False
    if any(part in value for part in SKIP_SUBSTRINGS):
        return False
    if value in KEYBOARD or re.fullmatch(r"[A-Z0-9_]+", value):
        return False
    if re.fullmatch(r"[a-z0-9_./:-]+", value):
        return False
    if value[0] in " '\"`)+]}>,:;.?" or value[-1] in " '\"`([{<,:=+-":
        return False
    if re.search(r"\b(?:class|style|fill|stroke|id|type|role|tabindex|width|height|x1|x2|y1|y2|y)=\s*$", value):
        return False
    if re.search(r"[{}<>\\]|\$\{|\\n", value):
        return False
    if re.search(r"\b(?:get|set|cls|color|format|scale|unit|label|description|lens|group|width|level|kind|note|sub|text|value|onClick|title)\s*[:=]", value):
        return False
    # Most user-facing text is a sentence/caption or a title-case label. Lower-case single identifiers are code.
    return " " in value or value[0].isupper() or value in {"no data"}


def collect_js_strings(strings):
    quoted = re.compile(r"(['\"])(.*?)(?<!\\)\1", re.DOTALL)
    template = re.compile(r"`([^`]{2,220})`")
    paths = list((ROOT / "web/js/ui").glob("*.js")) + list((ROOT / "web/js/app").glob("*.js"))
    paths += [ROOT / "web/js/main.js"] + list((ROOT / "web/js/ext").rglob("*.js"))
    for path in paths:
        text = path.read_text(errors="ignore")
        candidates = []
        # Template strings often contain nested quoted literals. Keep simple templates intact, then
        # remove backticks so quoted ternary/label strings inside larger templates remain visible.
        candidates.extend(template.findall(text))
        unquoted_text = text.replace("`", "")
        candidates.extend(match.group(2) for match in quoted.finditer(unquoted_text))
        for value in candidates:
            value = html.unescape(value).strip()
            if plausible_ui_literal(value):
                strings.add(value)


def translate_batch(batch):
    query = SEPARATOR.join(batch)
    url = ENDPOINT + urllib.parse.quote(query)
    data = json.loads(urllib.request.urlopen(url, timeout=25).read())
    text = "".join(part[0] for part in data[0])
    parts = [part.strip("\n ") for part in text.split("ZXQJSEP")]
    if len(parts) != len(batch):
        raise ValueError(f"translation batch split into {len(parts)} parts for {len(batch)} inputs")
    return parts


def translate_missing(missing):
    chunks, current, size = [], [], 0
    for text in missing:
        needed = len(text) + len(SEPARATOR)
        if current and size + needed > 3500:
            chunks.append(current)
            current, size = [], 0
        current.append(text)
        size += needed
    if current:
        chunks.append(current)

    translated = {}
    for index, chunk in enumerate(chunks, 1):
        parts = None
        for attempt in range(4):
            try:
                parts = translate_batch(chunk)
                break
            except Exception:
                if attempt < 3:
                    time.sleep(1 + attempt)
        if parts is None:
            parts = []
            for text in chunk:
                try:
                    parts.append(translate_batch([text])[0])
                except Exception:
                    parts.append(text)
        for source, target in zip(chunk, parts):
            if target and target.strip():
                translated[source] = target.strip()
        print(f"translated batch {index}/{len(chunks)}")
    return translated


def main():
    strings = set()
    collect_data_strings(strings)
    collect_html_strings(strings)
    collect_js_strings(strings)
    existing = json.loads(OUT.read_text()) if OUT.exists() else {}
    translations = {key: value for key, value in existing.items() if key in strings}
    missing = sorted(strings - translations.keys())
    print(f"strings={len(strings)} existing={len(translations)} missing={len(missing)}")
    if missing:
        translations.update(translate_missing(missing))
    translations.update(MANUAL_OVERRIDES)
    OUT.write_text(json.dumps(translations, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    print(f"wrote {OUT} entries={len(translations)} bytes={OUT.stat().st_size}")


if __name__ == "__main__":
    main()
