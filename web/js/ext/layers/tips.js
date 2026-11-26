// Hover tooltips for the map-art layers (HTML strings; every data value is escaped). Each says where the number comes
// from and the caveat that matters for it (FAF values are model estimates; bases have no published headcount; the
// trade arc is a drawing aid; curated landmarks are an editorial pick).
import { esc, compact, int, pct } from "../../format.js";
import { FORT_KINDS, fortKind, WONDER_KINDS } from "../../render/art/sites.js";
import { MODE_STYLE } from "../../render/art/improvements.js";

const muted = (s) => `<span class="muted">${s}</span>`;
const num = (n, d = 1) => (n == null || !Number.isFinite(n) ? "–" : compact(n));
const sign = (x) => (x > 0 ? "+" : x < 0 ? "−" : "±");

function eur(n) {
  if (n == null || !Number.isFinite(n)) return "–";
  const a = Math.abs(n);
  if (a >= 1e12) return `€${(n / 1e12).toFixed(2)} trillion`;
  if (a >= 1e9) return `€${(n / 1e9).toFixed(a >= 1e10 ? 1 : 2)} billion`;
  if (a >= 1e6) return `€${(n / 1e6).toFixed(1)} million`;
  return `€${int(n)}`;
}

const HUB_NAME = { L: "Large hub", M: "Medium hub", S: "Small hub", N: "Nonhub primary airport" };
const PORT_TYPE = { coastal: "Coastal port", great_lakes: "Great Lakes port", inland: "Inland river port" };

export const tips = {
  port(p, m) {
    const yr = p.year ?? "";
    const lines = [
      `<b>${esc(p.name)}</b> ${muted(`${esc(PORT_TYPE[p.type] || "Port")}, ${esc(p.state || "")}`)}`,
      `#${esc(p.rank)} by tonnage · <b>${num(p.tons)}</b> metric tonnes (${esc(yr)})`,
    ];
    if (p.foreign != null || p.domestic != null) lines.push(`Foreign ${num(p.foreign)} · domestic ${num(p.domestic)}`);
    if (p.imports != null || p.exports != null) lines.push(`Imports ${num(p.imports)} · exports ${num(p.exports)}`);
    lines.push(muted("Eurostat maritime port tonnage; placed at the port area's centre (long river ports are approximate)."));
    return lines.join("<br>");
  },
  airport(a) {
    const lines = [`<b>${esc(a.id)} · ${esc(a.name)}</b> ${muted(esc([a.city, a.state].filter(Boolean).join(", ")))}`];
    lines.push(a.hub ? esc(HUB_NAME[a.hub] || a.hub) : "All-cargo airport (not a primary passenger airport)");
    if (a.enplanements != null) {
      let ch = "";
      if (a.enplanements_prev > 0) {
        const r = a.enplanements / a.enplanements_prev - 1;
        ch = ` (${sign(r)}${Math.abs(r * 100).toFixed(1)}% on ${a.year - 1})`;
      }
      lines.push(`<b>${num(a.enplanements)}</b> passengers (arrivals + departures) in ${esc(a.year)}${ch}`);
    }
    lines.push(muted("Eurostat airport passengers; letters are local display-size buckets."));
    return lines.join("<br>");
  },
  station(st) {
    return [
      `<b>${esc(st.name)} station</b> ${muted(esc(st.state || ""))}`,
      `<b>${num(st.passengers)}</b> passengers in ${esc(st.year)}`,
      muted("SNCF Gares & Connexions. The revised 2025 methodology is not directly comparable with 2015–2024."),
    ].join("<br>");
  },
  fort(f, m) {
    const comp = m.data.military?.components?.find((c) => c.id === f.component);
    const name = comp?.name || FORT_KINDS[fortKind(f.component)]?.name || "Defense site";
    const tier = { major: "Major installation", base: "Base", site: "Site" }[f.tier] || "";
    const status = { act: "", semi: " · semi-active", care: " · caretaker status" }[f.status] ?? "";
    const lines = [
      `<b>${esc(f.name)}</b> ${muted(esc(f.state || ""))}`,
      `${esc(name)}${f.joint ? " · joint base" : ""} · ${esc(tier)}${esc(status)}`,
    ];
    if (f.area_km2 != null) lines.push(`Boundary ${int(f.area_km2)} km²`);
    lines.push(muted("Ministry of the Armed Forces, 2012. Marker is the support-group seat, not a boundary."));
    return lines.join("<br>");
  },
  range(r, m) {
    const comp = m.data.military?.components?.find((c) => c.id === r.component);
    return [
      `<b>${esc(r.name)}</b> ${muted(esc(r.state || ""))}`,
      `Restricted ground · ${esc(comp?.name || "")} · ${int(r.area_km2)} km²`,
      muted("Restricted-ground polygons are not currently available in the French open-data military layer."),
    ].join("<br>");
  },
  wonder(x, m) {
    const k = WONDER_KINDS[x.kind]?.name || "Wonder";
    const rule = m.data.wonders?.rules?.find((r) => r.id === x.rule);
    const mt = x.metrics || {};
    const lines = [`<b>${esc(x.name)}</b> ${muted(esc([x.state].filter(Boolean).join("")))}`];
    if (x.kind === "university") {
      lines.push(`${esc(k)} · #${esc(x.rank)} by enrolment`);
      if (mt.students != null) lines.push(`<b>${num(mt.students)}</b> students (${esc(mt.academic_year || mt.year)})`);
    } else if (x.rule === "museum_attendance") {
      lines.push(`${esc(k)} · #${esc(x.rank)} by museum visits`);
      if (mt.visits != null) lines.push(`<b>${num(mt.visits)}</b> visits (${esc(mt.year)})${mt.sites > 1 ? ` ${muted(`across ${int(mt.sites)} reporting sites`)}` : ""}`);
    } else if (x.curated) {
      lines.push(`${esc(k)} · hand-picked (curated, not ranked by data)`);
      if (mt.visits != null) lines.push(`${num(mt.visits)} recreation visits (${esc(mt.year)})`);
      if (mt.designated) lines.push(`National Historic Landmark since ${esc(mt.designated)}`);
    } else if (mt.designated) {
      lines.push(`${esc(k)} · UNESCO World Heritage, inscribed ${esc(mt.designated)}`);
      if (mt.criteria) lines.push(`Criteria: ${esc(mt.criteria)}`);
    } else {
      lines.push(`${esc(k)} · #${esc(x.rank)} by visits${mt.unit_type ? ` among ${esc(mt.unit_type === "National Park" ? "National Parks" : "other park units")}` : ""}`);
      if (mt.visits != null) lines.push(`<b>${num(mt.visits)}</b> recreation visits (${esc(mt.year)})${mt.visits_of ? ` ${muted(`(${esc(mt.visits_of)})`)}` : ""}`);
      if (mt.area_km2 != null) lines.push(`${int(mt.area_km2)} km²`);
    }
    if (rule?.text) lines.push(muted(esc(rule.text)));
    return lines.join("<br>");
  },
  route(rt, m) {
    const r = rt.route;
    const t = m.data.trade || {};
    const a = rt.a?.short || rt.a?.name || r.a, b = rt.b?.short || rt.b?.name || r.b;
    const modes = Object.entries(r.modes || {}).filter(([, v]) => v >= 0.05).sort((p, q) => q[1] - p[1])
      .map(([k, v]) => `${esc(MODE_STYLE[k]?.label || k)} ${Math.round(v * 100)}%`).join(" · ");
    const com = t.commodities?.[r.top_commodity];
    const lines = [
      `<b>${esc(a)} ⇄ ${esc(b)}</b> ${muted(`trade route #${esc(r.rank)}`)}`,
      `<b>${num((r.volume_mtkm ?? 0) * 1e6)}</b> tonne-kilometres a year, about ${num((r.tons_k ?? 0) * 1e3)} metric tonnes (SDES ${esc(t.year ?? "")})`,
    ];
    if (modes) lines.push(modes);
    if (com) lines.push(`Commodities: ${esc(com)}`);
    lines.push(muted("Both directions combined. Drawn as an arc between regional anchors: SDES records where freight starts and ends, not its physical route."));
    return lines.join("<br>");
  },
};
