// Culture advisor ("Keeper of Wonders"): French wonders by published rule and GASPAR natural-hazard recognitions.
import { esc, fin, el as mk, colorScale } from "../core/util.js";
import { int, pct, money, count3 } from "../core/fmt.js";
import { barList, shareBar, histogram } from "../core/charts.js";
import { createTable } from "../core/table.js";
import { section, tiles, segmented, mapPicker, sourcesHtml } from "../core/view.js";
import { rowsHighlight } from "../core/data.js";
import { frameBox, focusPoint } from "../core/frame.js";

const KIND = {
  natural: { label: "Nature", color: "#6aa84f" },
  university: { label: "Universities", color: "#4a86d6" },
  landmark: { label: "Landmarks", color: "#e0b54c" },
};
const RULE_TITLE = { national_park: "National parks", park_unit: "Other park units", research_university: "Research universities", landmark: "Landmarks", unesco_natural: "Natural World Heritage", unesco_cultural: "Cultural World Heritage", museum_attendance: "Most-visited museums", university_enrolment: "Largest universities" };
const DIS_COLOR = { hurricane: "#4f9ad6", flood: "#2fa4b8", fire: "#e8774a", severe_storm: "#9a7bc9", winter: "#c9dcef", other: "#9a9aa8" };

export async function mount(ctx) {
  const { app, data, el, link } = ctx;
  const won = await app.loadData("wonders");
  const { states: stLevel, counties } = data.levels;
  const lensFaith = app.lensById?.get("faith"), lensTrad = app.lensById?.get("faith_tradition");
  const lensAmen = app.lensById?.get("amenities"), lensDis = app.lensById?.get("disasters");

  // --- headline -------------------------------------------------------------------------------------------------
  const wonders = (won?.wonders || []).map((w) => ({ ...w, key: w.id }));
  const byKind = (k) => wonders.filter((w) => w.kind === k).length;
  let adherents = null;
  if (counties) {
    let a = 0, p = 0;
    for (const r of counties.rows) if (fin(r.v.faith) && fin(r.v.population)) { a += (r.v.faith / 100) * r.v.population; p += r.v.population; }
    adherents = p ? (a / p) * 100 : null;
  }
  const tileEl = mk("div");
  el.appendChild(tileEl);
  const drawTiles = (dis) => {
    const topMuseum = wonders.filter((w) => w.rule === "museum_attendance")[0];
    const topUniversity = wonders.filter((w) => w.rule === "university_enrolment")[0];
    tileEl.innerHTML = tiles([
      { label: "Wonders", value: int(wonders.length), sub: `${byKind("natural")} natural · ${byKind("university")} universities · ${byKind("landmark")} landmarks` },
      { label: "Top museum", value: topMuseum ? `${count3(topMuseum.metrics?.visits)} visits` : "–", sub: topMuseum ? `${topMuseum.short || topMuseum.name}, ${topMuseum.metrics?.year}` : "" },
      { label: "Largest university", value: topUniversity ? count3(topUniversity.metrics?.students) : "–", sub: topUniversity ? `${topUniversity.short || topUniversity.name} students` : "" },
    ]);
  };
  drawTiles(null);

  // --- map colour -----------------------------------------------------------------------------------------------
  const mapRow = mk("div", "adv-sec adv-mapsec");
  el.appendChild(mapRow);
  const picker = mapPicker(ctx, mapRow, {
    value: "terrain",
    options: [
      { value: "terrain", label: "Terrain", lens: () => null },
      ...(lensFaith ? [{ value: "faith", label: "Faith", lens: () => "faith" }] : []),
      ...(lensTrad ? [{ value: "trad", label: "Tradition", lens: () => "faith_tradition" }] : []),
      ...(lensAmen ? [{ value: "amen", label: "Amenities", lens: () => "amenities" }] : []),
      ...(lensDis ? [{ value: "dis", label: "Disasters", lens: () => "disasters" }] : []),
    ],
  });

  // --- wonders --------------------------------------------------------------------------------------------------
  let wonderBars = [];
  const bubbles = ctx.bubbles("wonders", {
    rMax: 9, minR: 9, alpha: 0.28,
    tip: (b) => `<b>${esc(b.it.name)}</b><br>${esc(RULE_TITLE[b.it.rule] || b.it.kind)} #${b.it.rank} · ${esc(metricText(b.it))}${b.it.curated ? `<br><span class="sub">hand-picked, not ranked by data</span>` : ""}`,
    onHover: (b) => { for (const w of wonderBars) w.setHot(b ? b.key : null); },
    onClick: (b) => flyTo(b.it),
  });
  if (won && wonders.length) {
    const wBody = section(el, { title: "Wonders", kicker: "Each chosen by a published rule", note: "Hover a wonder to find it on the map; click to fly there. Each section uses its own published rule: UNESCO inscription year, museum visits or university enrolment." });
    let kind = "all";
    segmented(wBody, {
      label: "Kind", value: kind,
      options: [{ value: "all", label: "All" }, ...Object.entries(KIND).filter(([k]) => byKind(k)).map(([k, v]) => ({ value: k, label: v.label }))],
      onChange: (v) => { kind = v; drawWonders(); },
    });
    const wHost = mk("div");
    wBody.appendChild(wHost);
    function drawWonders() {
      wHost.innerHTML = "";
      wonderBars = [];
      const vis = wonders.filter((w) => kind === "all" || w.kind === kind);
      for (const rule of won.rules || []) {
        const list = vis.filter((w) => w.rule === rule.id);
        if (!list.length) continue;
        wHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">${esc(RULE_TITLE[rule.id] || rule.id)}</h4><p class="adv-note adv-rule">${esc(rule.text)}</p>`);
        const host = mk("div");
        wHost.appendChild(host);
        const val = (w) => (w.kind === "university" ? w.metrics?.students : w.metrics?.visits ?? null);
        wonderBars.push(barList(host, {
          rank: !rule.curated, compact: true, ariaLabel: RULE_TITLE[rule.id] || rule.id,
          rows: list.map((w) => ({ key: w.key, label: w.short || w.name, full: w.name, sub: w.state, value: val(w), text: metricText(w), color: KIND[w.kind]?.color })),
          onHover: (r) => {
            const w = r ? wonders.find((x) => x.key === r.key) : null;
            link.hover(w ? { cells: new Set(w.cells && w.cells.length ? w.cells : w.cell != null ? [w.cell] : []), label: w.short || w.name } : null);
            bubbles.setHot(w ? w.key : null);
          },
          onClick: (r) => flyTo(wonders.find((x) => x.key === r.key)),
        }));
      }
      bubbles.set(vis.filter((w) => fin(w.x) && fin(w.y)).map((w) => ({ key: w.key, x: w.x, y: w.y, value: 1, color: KIND[w.kind]?.color || "#ccc", it: w })), { vMax: 1 });
    }
    drawWonders();
    wBody.insertAdjacentHTML("beforeend", `<p class="adv-note">Map markers: <i class="dot" style="background:${KIND.natural.color}"></i>natural · <i class="dot" style="background:${KIND.university.color}"></i>university · <i class="dot" style="background:${KIND.landmark.color}"></i>landmark.</p>`);
  } else el.insertAdjacentHTML("beforeend", `<p class="adv-empty pad">wonders.json is not built.</p>`);
  function flyTo(w) {
    if (!w) return;
    if (w.cells && w.cells.length > 2) {
      const b = app.highlightBounds({ cells: new Set(w.cells) });
      if (b) return frameBox(app, b, { pad: 60, maxScale: 3 });
    }
    focusPoint(app, w.x, w.y, Math.min(app.cam.maxScale, Math.max(app.cam.scale, (app.cam.fitScale || 1) * 3.2)));
  }

  // --- natural hazards ------------------------------------------------------------------------------------------
  const dSec = section(el, {
    title: "Natural hazards", kicker: "GASPAR catastrophe-naturelle recognitions",
    note: "Recognitions since 2000 are administrative declarations aggregated to departments and normalised by today's commune count. They measure recognition frequency, not physical exposure or damage.",
  });
  let hazardTable = null;
  if (counties) {
    const rows = counties.rows.filter((r) => fin(r.v.disasters));
    dSec.insertAdjacentHTML("beforeend", `<p class="adv-note">Use the Map colour control above to draw the recognition-frequency lens. Flood and drought columns are shares of each department's recognitions; other hazard types make up the remainder.</p>`);
    hazardTable = createTable(dSec, {
      caption: "Natural-hazard recognitions by department", rank: true, maxHeight: 260, search: "Search departments",
      rows,
      columns: [
        { key: "name", label: "Department", align: "l", width: "minmax(0,1.5fr)", value: (r) => r.name, html: (r) => `${esc(r.name)} <span class="sub">${esc(r.sub)}</span>` },
        { key: "frequency", label: "Frequency", value: (r) => r.v.disasters, text: (r) => r.v.disasters.toFixed(1), bar: { max: Math.max(...rows.map((r) => r.v.disasters || 0), 1), color: "rgba(47,102,144,.34)" }, title: "Recognitions since 2000 per current commune" },
        { key: "flood", label: "Flood", value: (r) => r.v.flood_events, text: (r) => pct(r.v.flood_events), title: "Share of recognitions involving flood, mudflow, waves or groundwater rise" },
        { key: "drought", label: "Drought", value: (r) => r.v.drought_events, text: (r) => pct(r.v.drought_events), title: "Share of recognitions involving drought" },
      ],
      sort: { key: "frequency", dir: "desc" },
      onHover: (r) => link.hover(r ? rowsHighlight(counties, [r], { dim: true }) : null),
      onClick: (r) => { picker.set("dis"); counties.focus(r); },
    });
  } else {
    dSec.insertAdjacentHTML("beforeend", `<p class="adv-empty">counties.json is not built.</p>`);
  }

  // --- sources --------------------------------------------------------------------------------------------------
  const srcEl = mk("div");
  el.appendChild(srcEl);
  srcEl.innerHTML = sourcesHtml(data, [...(won?.sources || []), "fr_hazards"], [
    "UNESCO serial properties are represented by one French component point rather than their full boundaries.",
    "Museum attendance uses each museum's latest annual total, summing distinct physical sites that share one Muséofile institution. Repeated correction rows for the same site are not double-counted.",
    "University enrolment includes principal and secondary enrolments and CPGE double enrolments. SISE places institutions at their administrative headquarters commune, not across every campus.",
    "France has no census religion question comparable to the original US faith lens, so that layer is intentionally absent.",
  ]);

  const api = {
    onMapHover(h) {
      const owner = h.cell >= 0 ? app.w.raw.owner[h.cell] : -1;
      const sr = owner >= 0 ? stLevel.rows[owner] : null;
      const c = h.cell >= 0 && counties ? counties.rowAtCell(h.cell) : null;
      hazardTable?.setHot(c ? c.key : null, false);
      if (h.item?.kind === "wonder") for (const w of wonderBars) w.setHot(h.item.data?.id ?? null);
    },
    onMapClick(ev) {
      if (ev.item?.kind !== "wonder") return false;
      flyTo(wonders.find((w) => w.id === ev.item.data?.id));
      return true;
    },
  };
  return api;

  function active() { return el.isConnected; }
}

function metricText(w) {
  const m = w.metrics || {};
  if (w.kind === "university") return fin(m.students) ? `${count3(m.students)} students` : "–";
  if (w.kind === "natural") return fin(m.visits) ? `${count3(m.visits)} visits` : fin(m.designated) ? `inscribed ${m.designated}` : "–";
  if (fin(m.visits)) return `${count3(m.visits)} visits`;
  return fin(m.designated) ? `landmark since ${m.designated}` : "landmark";
}

const titleCase = (s) => String(s || "").toLowerCase().replace(/\b([a-z])/g, (c) => c.toUpperCase()).replace(/\b(And|Of|The|In)\b/g, (w) => w.toLowerCase());

/** A small SVG column chart (one column per item). */
function columnChart(items, val, label) {
  const W = 400, H = 110, m = { l: 4, r: 4, t: 6, b: 18 };
  const max = Math.max(1, ...items.map(val));
  const bw = (W - m.l - m.r) / items.length;
  const div = document.createElement("div");
  div.className = "adv-hist adv-cols-chart";
  const first = items[0]?.year, last = items[items.length - 1]?.year;
  div.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="none" role="img" aria-label="Events per year">
    ${items.map((it, i) => { const h = (val(it) / max) * (H - m.t - m.b); return `<g class="bin"><rect class="hit" x="${(m.l + i * bw).toFixed(2)}" y="${m.t}" width="${bw.toFixed(2)}" height="${H - m.t - m.b}"/><rect class="bar" x="${(m.l + i * bw + 0.4).toFixed(2)}" y="${(H - m.b - h).toFixed(2)}" width="${Math.max(0.5, bw - 0.8).toFixed(2)}" height="${h.toFixed(2)}" fill="#cf6a4a"/><title>${esc(label(it))}</title></g>`; }).join("")}
    <line x1="${m.l}" x2="${W - m.r}" y1="${H - m.b + 0.5}" y2="${H - m.b + 0.5}" class="axis"/>
    <text x="${m.l}" y="${H - 5}" class="tick">${first ?? ""}</text><text x="${W - m.r}" y="${H - 5}" text-anchor="end" class="tick">${last ?? ""}</text>
    <text x="${m.l + 2}" y="${m.t + 9}" class="tick">${max} max</text>
  </svg>`;
  return div;
}

