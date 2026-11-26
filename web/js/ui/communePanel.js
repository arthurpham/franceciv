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
  const close = () => { if (el.hidden) return; el.hidden = true; notify(); };
  el.addEventListener("click", (e) => { if (e.target.closest(".cp-close")) close(); });
  return {
    close,
    get isOpen() { return !el.hidden; },
    open(c) {
      const facts = rows.map(([k, label, fmt]) => c[k] == null ? "" : `<div class="cp-row"><span>${label}</span><b>${fmt(c[k])}</b></div>`).join("");
      const hazard = c.hazard_events ? `${int(c.hazard_events)} recognitions since 2000 · mostly ${esc(c.hazard_dominant || "other")}` : "No catastrophe-naturelle recognition since 2000";
      el.innerHTML = `<button class="cp-close" aria-label="Close">×</button>
        <div class="cp-kicker">COMMUNE</div><h2>${esc(c.name)}</h2><div class="cp-sub">${esc(c.department)} · ${int(c.population)} residents</div>
        <div class="cp-grid">${facts}</div><h3>Natural disasters</h3><p>${hazard}</p>
        <p class="cp-note">INSEE comparateur 2023; official 2022 presidential second-round results; GASPAR recognitions 2000–2025. Election shares use valid votes; some recently merged communes lack a 2022 row. Hazards are administrative recognitions, not damage. Median income is suppressed in some small communes.</p>`;
      el.hidden = false;
      notify();
    },
  };
}
