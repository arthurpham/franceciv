import { esc, int, pct } from "../format.js";

const rows = [
  ["density", "Density", (v) => `${int(v)} / km²`],
  ["median_income", "Median standard of living", (v) => `€${int(v)} / year`],
  ["poverty", "Poverty", pct],
  ["growth", "Population growth", (v) => `${v >= 0 ? "+" : ""}${pct(v)} / year`],
  ["natural_balance", "Natural balance", (v) => `${v >= 0 ? "+" : ""}${pct(v)} / year`],
  ["business_density", "Business establishments", (v) => `${v.toFixed(1)} / 1k residents`],
  ["owner_share", "Owner-occupied homes", pct],
  ["second_home_share", "Second homes", pct],
  ["vacancy_share", "Vacant homes", pct],
];

export function initEpciPanel(opts = {}) {
  const el = document.createElement("aside");
  el.id = "epci-panel";
  el.hidden = true;
  document.body.appendChild(el);
  const notify = () => opts.onVisibility?.(!el.hidden);
  const close = () => { if (el.hidden) return; el.hidden = true; notify(); };
  el.addEventListener("click", (e) => { if (e.target.closest(".cp-close")) close(); });
  return {
    close,
    get isOpen() { return !el.hidden; },
    open(e) {
      const facts = rows.map(([k, label, fmt]) => e[k] == null ? "" : `<div class="cp-row"><span>${label}</span><b>${fmt(e[k])}</b></div>`).join("");
      el.innerHTML = `<button class="cp-close" aria-label="Close">×</button>
        <div class="cp-kicker">EPCI</div><h2>${esc(e.name)}</h2><div class="cp-sub">${int(e.population)} residents · ${int(e.commune_count)} communes${e.departments ? ` · ${esc(e.departments)}` : ""}</div>
        <div class="cp-grid">${facts}</div>
        <p class="cp-note">INSEE comparateur de territoires 2023 and geo.api.gouv.fr EPCI membership. Position is the population-weighted centroid of member communes. Poverty and income can be suppressed in small or revised territories.</p>`;
      el.hidden = false;
      notify();
    },
  };
}
