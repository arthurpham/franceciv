import { esc, int, pct } from "../format.js";

const rows = [
  ["density", "Density", (v) => `${int(v)} / km²`],
  ["home_price", "Existing-home price", (v) => `€${int(v)} / m²`],
  ["annual_sales", "Existing-home sales", (v) => `${int(v)} / year`],
  ["mobility", "Residential mobility", pct],
  ["outside_migration", "In-migration from outside department/abroad", pct],
];

export function initGeographyPanel(opts = {}) {
  const el = document.createElement("aside");
  el.id = "geography-panel";
  el.hidden = true;
  document.body.appendChild(el);
  const notify = () => opts.onVisibility?.(!el.hidden);
  const close = () => { if (el.hidden) return; el.hidden = true; notify(); };
  el.addEventListener("click", (e) => { if (e.target.closest(".cp-close")) close(); });
  return {
    close,
    get isOpen() { return !el.hidden; },
    open(g, kindLabel) {
      const cell = opts.cellAt?.(g.x, g.y);
      const local = opts.inspector?.section(cell, { x: g.x, y: g.y });
      const facts = rows.map(([k, label, fmt]) => g[k] == null ? "" : `<div class="cp-row"><span>${label}</span><b>${fmt(g[k])}</b></div>`).join("");
      el.innerHTML = `<button class="cp-close" aria-label="Close">×</button>
        <div class="cp-kicker">${esc(kindLabel)}</div><h2>${esc(g.name)}</h2><div class="cp-sub">${int(g.population)} residents · ${int(g.commune_count)} communes${g.departments ? ` · ${esc(g.departments)}` : ""}</div>
        <div class="cp-grid">${facts}</div>${local ? `<h3>${esc(local.title)}</h3>${local.html}` : ""}
        <p class="cp-note">INSEE official functional geography at 1 January 2025. Position is the population-weighted centroid of member communes. Housing values are 2025 transaction-weighted existing-home indicators where enough sales exist; mobility shares use census 2023 residents.</p>`;
      if (local) opts.inspector.wire(el, cell, { x: g.x, y: g.y });
      el.hidden = false;
      notify();
    },
  };
}
