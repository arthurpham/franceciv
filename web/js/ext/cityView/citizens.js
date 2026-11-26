// City View "Citizens" rows: the metro's people as rows of small figures (citizens.json, INSEE census).
//
//   citizensHtml(m, data) → HTML      the rows (placeholders for the figure canvases)
//   mountCitizens(host, m, data)       paints the figures and wires the hover / focus read-out
//
// Each row: N figures (workforce 20, ages 10, commute 10 from the file; education and origins 10, rounded here with
// the same largest-remainder method), a caption ("each figure ≈ 72K workers"), a read-out line that a hovered or
// focused figure fills ("1 in 7 workers in Paris is a manager or intellectual professional (France: 1 in 14)"), and a thin
// national bar for comparison. A row Census left out is said so, never drawn as zeros.
import { esc, int, pct } from "../../format.js";
import { compact } from "./fmt.js";
import { CATEGORY_COLOR, figureCanvas, loadPainter } from "./figures.js";

const ROWS = [
  { id: "workforce", title: "Workforce", sub: "by broad socio-professional category", noun: ["worker", "workers"], n: null },
  { id: "age", title: "Generations", sub: "by broad age band", noun: ["resident", "residents"], n: null },
  { id: "commute", title: "Commute", sub: "how workers get to work", noun: ["worker", "workers"], n: null },
  { id: "education", title: "Education", sub: "highest diploma, non-enrolled residents 15+", noun: ["resident", "non-enrolled residents 15+"], n: 10 },
  { id: "nativity", title: "Origins", sub: "by immigrant status", noun: ["resident", "residents"], n: 10 },
];

// [singular verb phrase, plural verb phrase] per category, for "1 in 7 workers in X is …" / "7 in 10 … are …".
const PHRASE = {
  workforce: {
    farmer: ["is a farmer", "are farmers"],
    executive: ["is an artisan, merchant or business owner", "are artisans, merchants or business owners"],
    scholar: ["is a manager or intellectual professional", "are managers or intellectual professionals"],
    clerk: ["is an intermediate professional", "are intermediate professionals"],
    service: ["is an employee", "are employees"],
    maker: ["is a manual, industrial or transport worker", "are manual, industrial or transport workers"],
  },
  age: {
    child: ["is under 15", "are under 15"],
    young: ["is 15–24", "are 15–24"],
    midlife: ["is 25–64", "are 25–64"],
    elder: ["is 65 or older", "are 65 or older"],
  },
  commute: {
    drove_alone: ["uses a car, truck or van to work", "use a car, truck or van to work"],
    carpool: ["carpools to work", "carpool to work"],
    transit: ["takes public transit to work", "take public transit to work"],
    walk: ["walks to work", "walk to work"],
    other: ["cycles or uses a motorized two-wheeler", "cycle or use motorized two-wheelers"],
    home: ["does not use transport to work", "do not use transport to work"],
  },
  education: {
    less_than_hs: ["is below baccalauréat level", "are below baccalauréat level"],
    high_school: ["has a baccalauréat", "have a baccalauréat"],
    some_college: ["has a short higher-education degree", "have short higher-education degrees"],
    bachelors: ["has a bachelor-level degree", "have bachelor-level degrees"],
    graduate: ["has a bac+5 or higher degree", "have bac+5 or higher degrees"],
  },
  nativity: {
    born_in_state: ["is not an immigrant", "are not immigrants"],
    foreign_born: ["is an immigrant", "are immigrants"],
  },
};

// Short legend labels (the file's labels are long).
const SHORT = {
  workforce: { farmer: "Farmers", executive: "Artisans & owners", scholar: "Managers & professions", clerk: "Intermediate", service: "Employees", maker: "Workers" },
  age: { child: "Under 15", young: "15–24", midlife: "25–64", elder: "65+" },
  commute: { drove_alone: "Car/van", carpool: "Carpool", transit: "Transit", walk: "Walk", other: "Bike & 2-wheel", home: "No transport" },
  education: { less_than_hs: "Below bac", high_school: "Bac", some_college: "Bac+2", bachelors: "Bac+3/4", graduate: "Bac+5+" },
  nativity: { born_in_state: "Not immigrant", foreign_born: "Immigrant" },
};

/** Largest-remainder rounding of counts into n figures (the pipeline's method, for rows without figures). */
export function largestRemainder(counts, keys, n) {
  const tot = keys.reduce((a, k) => a + (counts[k] || 0), 0);
  if (!(tot > 0)) return null;
  const raw = keys.map((k) => ((counts[k] || 0) / tot) * n);
  const out = raw.map(Math.floor);
  let left = n - out.reduce((a, v) => a + v, 0);
  const order = raw.map((v, j) => [v - Math.floor(v), j]).sort((a, b) => b[0] - a[0] || a[1] - b[1]);
  for (let k = 0; k < left; k++) out[order[k][1]]++;
  return Object.fromEntries(keys.map((k, j) => [k, out[j]]));
}

/** "1 in 7", "3 in 10", "fewer than 1 in 1,000". */
export function oneIn(share) {
  if (share == null || !Number.isFinite(share)) return null;
  if (share <= 0) return { text: "none", plural: true };
  if (share < 0.001) return { text: "fewer than 1 in 1,000", plural: false };
  if (share >= 0.3) {
    const k = Math.round(share * 10);
    return k >= 10 ? { text: "nearly all", plural: true } : { text: `${k} in 10`, plural: k !== 1 };
  }
  const n = Math.round(1 / share);
  return { text: `1 in ${int(n)}`, plural: false };
}

function sentence(rowId, key, share, natShare, cityName, noun) {
  const a = oneIn(share);
  if (!a) return "";
  const ph = PHRASE[rowId]?.[key] || ["is in this group", "are in this group"];
  const us = oneIn(natShare);
  const lead = a.text.charAt(0).toUpperCase() + a.text.slice(1);
  return `${lead} ${noun[1]} in ${cityName} ${a.plural ? ph[1] : ph[0]}${us ? ` (France: ${us.text})` : ""}`;
}

function rowModel(rowDef, row, nat, groups, figuresN) {
  const keys = (groups[rowDef.id] || []).map((g) => g.key);
  const n = figuresN[rowDef.id] ?? rowDef.n ?? 10;
  const figs = row.figures || largestRemainder(row.counts || {}, keys, n);
  const natFigs = nat?.figures || (nat ? largestRemainder(nat.counts || {}, keys, n) : null);
  return { keys, n, figs, natFigs };
}

// Specialists by row/key from the file (ratios from unrounded shares).
function specMap(city) {
  const m = new Map();
  for (const s of city?.specialists || []) m.set(`${s.row}|${s.key}`, s);
  return m;
}

/** The Citizens rows. data = citizens.json (or null / undefined while loading). */
export function citizensHtml(m, data) {
  const c = m.city;
  if (data === undefined) return `<p class="muted cv-note">Loading the citizen mix…</p>`;
  if (!data || !data.cities) return `<p class="muted cv-note">The citizen mix is not available.</p>`;
  const row0 = data.cities[c.id];
  if (!row0) {
    return `<p class="muted cv-note">INSEE published none of the citizen tables for ${esc(c.name)} in the ${esc(data.vintage || "census")} release, so there are no citizen figures here.</p>`;
  }
  const nat = data.national || {};
  const groups = data.groups || {};
  const specs = specMap(row0);
  const label = Object.fromEntries(Object.entries(groups).map(([r, gs]) => [r, Object.fromEntries(gs.map((g) => [g.key, g.label]))]));

  // Headline: median age, degrees, foreign-born, and the "great person" call-out (the strongest specialist).
  const med = row0.age?.median, usMed = nat.age?.median;
  const ba = row0.education?.bachelors_plus, usBa = nat.education?.bachelors_plus;
  const fb = row0.nativity?.foreign_born ?? row0.nativity?.shares?.foreign_born;
  const usFb = nat.nativity?.foreign_born ?? nat.nativity?.shares?.foreign_born;
  const chip = (v, us, fmt, lbl, tip) => (v == null ? "" : `<div class="cv-cz-chip" title="${esc(tip)}"><b>${fmt(v)}</b><span>${esc(lbl)}</span>${us != null ? `<small>France ${fmt(us)}</small>` : ""}</div>`);
  const top = (row0.specialists || []).find((s) => s.ratio >= (data.rule?.specialist_high ?? 1.5));
  const topRow = ROWS.find((r) => r.id === top?.row);
  const great = top && topRow ? `<div class="cv-great" style="--fc:${esc(CATEGORY_COLOR[top.row]?.[top.key] || "#c9a45c")}">
      <span class="cv-great-fig" data-great="${esc(top.row)}|${esc(top.key)}" aria-hidden="true"></span>
      <div><small>Standout citizens</small><b>${esc(label[top.row]?.[top.key] || top.key)}</b>
      <span>${pct(top.share, 1)} of ${esc(topRow.noun[1])} here, ${pct(top.national, 1)} nationally: ${top.ratio.toFixed(1)}× the national share.</span></div></div>` : "";

  const rows = ROWS.map((rd) => {
    const row = row0[rd.id];
    const head = `<div class="cv-cz-h"><b>${esc(rd.title)}</b><span>${esc(rd.sub)}</span></div>`;
    if (!row) {
      return `<div class="cv-cz-row missing" data-row="${rd.id}">${head}
        <p class="muted cv-note">INSEE did not publish this table for ${esc(c.name)} in the ${esc(data.vintage || "census")} release, so this row is left out.</p></div>`;
    }
    const { keys, n, figs, natFigs } = rowModel(rd, row, nat[rd.id], groups, data.figures || {});
    if (!figs) return `<div class="cv-cz-row missing" data-row="${rd.id}">${head}<p class="muted cv-note">No counts for this row.</p></div>`;
    const per = row.total / n;
    const cells = [];
    for (const k of keys) {
      for (let j = 0; j < (figs[k] || 0); j++) {
        const sp = specs.get(`${rd.id}|${k}`);
        const mark = sp ? (sp.ratio >= 1 ? "up" : "down") : "";
        // One tab stop per category (its first figure), not one per figure.
        cells.push(`<span class="cv-fig${mark ? ` ${mark}` : ""}" tabindex="${j ? -1 : 0}" role="img" data-k="${esc(k)}" aria-label="${esc(label[rd.id]?.[k] || k)}"></span>`);
      }
    }
    // Legend: every category, with its share, the national share and a chevron for specialists. Categories that
    // round to no figure are still listed (greyed), so nothing silently disappears.
    const legend = keys.map((k) => {
      const sh = row.shares?.[k], us = nat[rd.id]?.shares?.[k];
      const sp = specs.get(`${rd.id}|${k}`);
      const chev = sp ? `<em class="${sp.ratio >= 1 ? "up" : "down"}" title="${sp.ratio.toFixed(1)}× the national share">${sp.ratio >= 1 ? "▲" : "▼"}</em>` : "";
      return `<span class="cv-cz-k${figs[k] ? "" : " zero"}" data-k="${esc(k)}" title="${esc(label[rd.id]?.[k] || k)}: ${sh != null ? pct(sh, 1) : "–"}${us != null ? ` (France ${pct(us, 1)})` : ""}${figs[k] ? "" : ". Rounds to no figure."}"><i style="background:${esc(CATEGORY_COLOR[rd.id]?.[k] || "#888")}"></i>${esc(SHORT[rd.id]?.[k] || k)} <small>${sh != null ? pct(sh, 0) : "–"}</small>${chev}</span>`;
    }).join("");
    // National comparison bar (shares), aligned with the figures' order.
    const usBar = nat[rd.id]?.shares ? `<div class="cv-cz-us" title="National mix, same order"><span>France</span><div>${keys.map((k) => {
      const s = nat[rd.id].shares[k] || 0;
      return s > 0 ? `<i style="flex:${s};background:${esc(CATEGORY_COLOR[rd.id]?.[k] || "#888")}" title="${esc(SHORT[rd.id]?.[k] || k)}: ${pct(s, 1)} in France"></i>` : "";
    }).join("")}</div></div>` : "";
    const cap = `Each figure ≈ ${compact(per)} ${rd.noun[1]} · ${compact(row.total)} in all${rd.n && !row.figures ? " · rounded here" : ""}`;
    const extra = rd.id === "age" && med != null ? ` · median age ${med.toFixed(1)}${usMed != null ? ` (France ${usMed.toFixed(1)})` : ""}` : "";
    return `<div class="cv-cz-row" data-row="${rd.id}" style="--n:${n}">${head}
      <div class="cv-figs" role="group" aria-label="${esc(rd.title)}: ${keys.filter((k) => figs[k]).map((k) => `${figs[k]} of ${n} ${SHORT[rd.id]?.[k] || k}`).join(", ")}">${cells.join("")}</div>
      ${usBar}
      <div class="cv-cz-out" aria-live="polite" data-default="${esc(cap + extra)}">${esc(cap + extra)}</div>
      <div class="cv-cz-legend">${legend}</div>
    </div>`;
  }).join("");

  const unreliable = row0.reliable === false
    ? `<p class="cv-warn">Small area: census margins of error are large here, so read these figures as rough.</p>` : "";
  return `
    <div class="cv-cz-top">
      ${chip(med, usMed, (v) => v.toFixed(1), "median age", "Median age")}
      ${chip(ba, usBa, (v) => pct(v, 0), "bac+3 or higher", "Non-enrolled residents aged 15+ whose highest diploma is bac+3 or above (INSEE census)")}
      ${chip(fb, usFb, (v) => pct(v, 0), "immigrants", "Residents counted as immigrants by INSEE")}
    </div>
    ${great}
    ${unreliable}
    <div class="cv-cz${row0.reliable === false ? " unreliable" : ""}">${rows}</div>
    <p class="cv-note">${esc(data.vintage || "INSEE census")}, Melodi census labour-force, population, commuting, diploma and immigration tables. Education counts non-enrolled residents aged 15+. Figures are rounded (largest remainder) so each row adds up; hover or tap a figure for its share. ▲▼ = at least 1.5× or at most 0.67× the national share. Commute counts workers, not all residents.</p>`;
}

/** Paint the figure canvases and wire the read-outs. */
export function mountCitizens(host, m, data) {
  if (!host || !data?.cities?.[m.city.id]) return;
  const row0 = data.cities[m.city.id];
  const nat = data.national || {};
  const dpr = Math.min(3, Math.max(1, Math.round((devicePixelRatio || 1) * 2) / 2));
  const paintAll = () => {
    host.querySelectorAll(".cv-cz-row[data-row]").forEach((rowEl) => {
      const rid = rowEl.dataset.row;
      rowEl.querySelectorAll(".cv-fig").forEach((el) => {
        const src = figureCanvas(rid, el.dataset.k, 36, dpr);
        const cv = document.createElement("canvas");
        cv.width = src.width;
        cv.height = src.height;
        cv.getContext("2d").drawImage(src, 0, 0);
        el.replaceChildren(cv);
      });
    });
    const g = host.querySelector("[data-great]");
    if (g) {
      const [rid, k] = g.dataset.great.split("|");
      const src = figureCanvas(rid, k, 36, dpr);
      const cv = document.createElement("canvas");
      cv.width = src.width;
      cv.height = src.height;
      cv.getContext("2d").drawImage(src, 0, 0);
      g.replaceChildren(cv);
    }
  };
  paintAll();
  // Once the citizen painter (render/art/people.js) loads, repaint the figures.
  loadPainter().then(() => { if (host.isConnected) paintAll(); });

  host.querySelectorAll(".cv-cz-row[data-row]").forEach((rowEl) => {
    const rid = rowEl.dataset.row;
    const rd = ROWS.find((r) => r.id === rid);
    const row = row0[rid];
    const out = rowEl.querySelector(".cv-cz-out");
    if (!row || !out) return;
    const show = (k) => {
      rowEl.querySelectorAll("[data-k]").forEach((el) => el.classList.toggle("lit", el.dataset.k === k));
      rowEl.classList.toggle("focus", !!k);
      if (!k) {
        out.textContent = out.dataset.default;
        out.classList.remove("on");
        return;
      }
      const sh = row.shares?.[k], us = nat[rid]?.shares?.[k];
      out.innerHTML = `${esc(sentence(rid, k, sh, us, m.city.name, rd.noun))}<small>${sh != null ? pct(sh, 1) : "–"} here${us != null ? ` · ${pct(us, 1)} in France` : ""}${row.counts?.[k] != null ? ` · ≈${compact(row.counts[k])} people` : ""}</small>`;
      out.classList.add("on");
    };
    let pinned = null;
    rowEl.addEventListener("pointerover", (e) => {
      const el = e.target.closest("[data-k]");
      if (el && rowEl.contains(el)) show(el.dataset.k);
    });
    rowEl.addEventListener("pointerleave", () => show(pinned));
    rowEl.addEventListener("focusin", (e) => {
      const el = e.target.closest("[data-k]");
      if (el) show(el.dataset.k);
    });
    rowEl.addEventListener("focusout", () => show(pinned));
    // A tap pins the category (phones have no hover); another tap on it lets go.
    rowEl.addEventListener("click", (e) => {
      const el = e.target.closest("[data-k]");
      if (!el) return;
      pinned = pinned === el.dataset.k ? null : el.dataset.k;
      show(pinned);
    });
  });
}
