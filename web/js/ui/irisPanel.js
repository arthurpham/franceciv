import { esc, int, pct } from "../format.js";

const rows = [
  ["density", "Density", (v) => `${int(v)} / km²`],
  ["area_km2", "Area", (v) => `${v.toFixed(v < 10 ? 2 : 1)} km²`],
  ["senior_share", "Residents 65+", pct],
  ["youth_share", "Residents under 20", pct],
  ["working_age_share", "Residents 20–64", pct],
  ["immigration_share", "Immigrants", pct],
  ["foreign_share", "Foreign nationals", pct],
];

export function initIrisPanel(opts = {}) {
  const el = document.createElement("aside");
  el.id = "iris-panel";
  el.hidden = true;
  document.body.appendChild(el);
  const notify = () => opts.onVisibility?.(!el.hidden);
  const close = () => { if (el.hidden) return; el.hidden = true; notify(); };
  el.addEventListener("click", (e) => { if (e.target.closest(".cp-close")) close(); });
  return {
    close,
    get isOpen() { return !el.hidden; },
    open(r) {
      const facts = rows.map(([k, label, fmt]) => r[k] == null ? "" : `<div class="cp-row"><span>${label}</span><b>${fmt(r[k])}</b></div>`).join("");
      const kind = r.true_iris ? "IRIS NEIGHBORHOOD" : "COMMUNE-SCALE IRIS";
      el.innerHTML = `<button class="cp-close" aria-label="Close">×</button>
        <div class="cp-kicker">${kind}</div><h2>${esc(r.name)}</h2><div class="cp-sub">${esc(r.commune)} · ${int(r.population)} residents${r.type ? ` · type ${esc(r.type)}` : ""}</div>
        <div class="cp-grid">${facts}</div>
        <p class="cp-note">INSEE 2022 census infra-communal population and IGN/INSEE Contours IRIS. Communes not divided into IRIS are represented as commune-scale pseudo-IRIS. Population statistics exclude Mayotte. Position and area are derived from polygon geometry.</p>`;
      el.hidden = false;
      notify();
    },
  };
}
