import { esc, int, pct } from "../format.js";

const rows = [
  ["density", "Density", (v) => `${int(v)} / km²`],
  ["median_income", "Median standard of living", (v) => `€${int(v)} / year`],
  ["growth", "Population growth", (v) => `${v >= 0 ? "+" : ""}${pct(v)} / year`],
  ["owner_share", "Owner-occupied homes", pct],
  ["second_home_share", "Second homes", pct],
  ["vacancy_share", "Vacant homes", pct],
  ["macron_share", "Macron 2022", pct],
  ["lepen_share", "Le Pen 2022", pct],
  ["abstention_share", "Abstention 2022", pct],
];

export function initCommunePanel(opts = {}) {
  const el = document.createElement("aside");
  el.id = "commune-panel";
  el.hidden = true;
  document.body.appendChild(el);
  const notify = () => opts.onVisibility?.(!el.hidden);
  let commuteSeq = 0;
  const close = () => { if (el.hidden) return; commuteSeq++; opts.showCommuteFlows?.(null); el.hidden = true; notify(); };
  el.addEventListener("click", (e) => { if (e.target.closest(".cp-close")) close(); });
  return {
    close,
    get isOpen() { return !el.hidden; },
    open(c) {
      const cell = opts.cellAt?.(c.x, c.y);
      const local = opts.inspector?.section(cell, { x: c.x, y: c.y });
      const facts = rows.map(([k, label, fmt]) => c[k] == null ? "" : `<div class="cp-row"><span>${label}</span><b>${fmt(c[k])}</b></div>`).join("");
      const hazardStart = c.hazard_start_year || 2000, hazardEnd = c.hazard_end_year || "present";
      const hazard = c.hazard_events ? `${int(c.hazard_events)} recognitions since ${hazardStart} · mostly ${esc(c.hazard_dominant || "other")}` : `No catastrophe-naturelle recognition since ${hazardStart}`;
      el.innerHTML = `<button class="cp-close" aria-label="Close">×</button>
        <div class="cp-kicker">COMMUNE</div><h2>${esc(c.name)}</h2><div class="cp-sub">${esc(c.department)} · ${int(c.population)} residents${c.epci_name ? ` · ${esc(c.epci_name)}` : ""}</div>
        <div class="cp-grid">${facts}</div><div id="cp-commute"></div>${local ? `<h3>${esc(local.title)}</h3>${local.html}` : ""}<h3>Natural disasters</h3><p>${hazard}</p>
        <p class="cp-note">INSEE comparateur 2023; EPCI geography from geo.api.gouv.fr; official 2022 presidential second-round results; GASPAR recognitions ${hazardStart}–${hazardEnd}. Election shares use valid votes; some recently merged communes lack a 2022 row. Hazards are administrative recognitions, not damage. Median income is suppressed in some small communes.</p>`;
      if (opts.loadCommuteFlows && opts.showCommuteFlows) {
        const token = ++commuteSeq;
        opts.showCommuteFlows(null);
        opts.loadCommuteFlows().then((payloads) => {
          if (token !== commuteSeq || el.hidden) return;
          const [flows, communeIndex] = payloads;
          const row = flows?.communes?.[c.code];
          if (!row) return;
          const positions = new Map();
          const cols = communeIndex?.columns || [];
          for (const r of communeIndex?.communes || []) {
            const x = r[cols.indexOf("x")], y = r[cols.indexOf("y")], code = r[cols.indexOf("code")], name = r[cols.indexOf("name")];
            positions.set(code, { x, y, name });
          }
          const flowLines = (arr) => (arr || []).map(([code, workers]) => ({ ...(positions.get(code) || {}), code, workers })).filter((f) => f.x != null);
          const out = flowLines(row[0]), incoming = flowLines(row[1]);
          opts.showCommuteFlows({ x: c.x, y: c.y, out, in: incoming });
          const max = Math.max(1, ...out.map((f) => f.workers), ...incoming.map((f) => f.workers));
          const list = (title, arr, cls) => arr.length ? `<h4>${title}</h4>` + arr.map((f) => `<div class="cf-row ${cls}"><span>${esc(f.name || f.code)}</span><i style="width:${Math.max(5, f.workers / max * 100)}%"></i><b>${int(f.workers)}</b></div>`).join("") : "";
          const target = el.querySelector("#cp-commute");
          if (target) target.innerHTML = `<h3>Commuting flows</h3><p class="cp-note">Lines on the map show the three largest recorded residence ↔ workplace links.</p>${list("Residents work in", out, "out")}${list("Workers live in", incoming, "in")}`;
        }).catch(() => {});
      }
      if (local) opts.inspector.wire(el, cell, { x: c.x, y: c.y });
      el.hidden = false;
      notify();
    },
  };
}
