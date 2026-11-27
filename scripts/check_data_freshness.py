#!/usr/bin/env python3
"""Evaluate the committed trust report at the current date and write a Markdown stale-data alert."""
import argparse, json
from datetime import datetime, timezone
from pathlib import Path

def parse(ts):
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trust", default="web/data/trust.json")
    ap.add_argument("--markdown", default="freshness-report.md")
    args = ap.parse_args()
    doc = json.loads(Path(args.trust).read_text())
    now = datetime.now(timezone.utc)
    generated = parse(doc["generated"])
    report_age = max(0, (now - generated).days)
    rows = []
    counts = {"due": 0, "attention": 0, "fresh": 0, "unknown": 0}
    for src in doc["sources"]:
        current_age = (src.get("age_days") or 0) + report_age
        cadence = src.get("refresh_cadence_days")
        if cadence is None:
            status = "unknown"
        elif current_age >= cadence:
            status = "due"
        elif current_age >= cadence * 0.75:
            status = "attention"
        else:
            status = "fresh"
        counts[status] += 1
        if status in {"due", "attention", "unknown"}:
            rows.append((status, src["title"], current_age, cadence, src.get("publisher") or ""))
    order = {"due": 0, "attention": 1, "unknown": 2}
    rows.sort(key=lambda r: (order[r[0]], r[1]))
    lines = [
        "# Franceciv data freshness report", "",
        f"Generated from `web/data/trust.json` built `{doc['generated']}`.", "",
        f"- Fresh: {counts['fresh']}", f"- Attention: {counts['attention']}", f"- Due: {counts['due']}", f"- Unknown cadence: {counts['unknown']}", "",
    ]
    if rows:
        lines += ["| Status | Source | Estimated age | Cadence | Publisher |", "|---|---|---:|---:|---|"]
        lines += [f"| {st} | {title} | {age} days | {cadence or 'unknown'} days | {pub} |" for st, title, age, cadence, pub in rows]
    else:
        lines.append("All sources are inside their declared refresh cadence.")
    lines += ["", "Refresh locally with `PYTHONPATH=. uv run python -m pipeline all`, commit regenerated `web/data`, and validate with `PYTHONPATH=. uv run pytest -q && PYTHONPATH=. uv run python -m pipeline check`."]
    Path(args.markdown).write_text("\n".join(lines) + "\n")
    print(f"due={counts['due']} attention={counts['attention']} unknown={counts['unknown']} fresh={counts['fresh']}")
    return 1 if counts["due"] else 0

if __name__ == "__main__":
    raise SystemExit(main())
