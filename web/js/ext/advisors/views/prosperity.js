// Prosperity & Housing advisor: standards of living, poverty, unemployment and the housing stock.
import { esc, fin, colorScale, RAMPS } from "../core/util.js";
import { money, pct, int, count3, fmtShort } from "../core/fmt.js";
import { barList, histogram, rampLegend } from "../core/charts.js";
import { createTable } from "../core/table.js";
import { createScatter } from "../core/scatter.js";
import { section, tiles, segmented, lensButton, sourcesHtml, topBy, frameBtn } from "../core/view.js";
import { rowsHighlight } from "../core/data.js";

const BIG_METRO = 500000;

export function mount(ctx) {
  const { app, data, el, link } = ctx;
  const n = data.nat;
  const { states, metros, counties } = data.levels;
  const wavg = (k) => {
    if (!counties) return null;
    let a = 0, w = 0;
    for (const r of counties.rows) if (fin(r.v[k]) && fin(r.v.population)) { a += r.v[k] * r.v.population; w += r.v.population; }
    return w ? a / w : null;
  };

  el.insertAdjacentHTML("beforeend", tiles([
    { label: "Median standard of living", value: money(n.median_income), sub: "per consumption unit" },
    { label: "Owner-occupied", value: pct(wavg("homeownership")), sub: "share of main homes" },
    { label: "Unemployment", value: pct(n.unemployment), sub: data.vintage },
  ]));

  if (!counties) {
    el.insertAdjacentHTML("beforeend", `<p class="adv-empty pad">counties.json is not built, so the department charts are missing.</p>`);
    el.insertAdjacentHTML("beforeend", sourcesHtml(data, ["fr_insee_stats"], []));
    return {};
  }

  // --- housing stock --------------------------------------------------------------------------------------------
  const hBody = section(el, { title: "The housing stock", note: "Second homes against vacant homes, with colour showing owner-occupation. Drag a rectangle to select departments; hover the map to find one here." });
  const hCtl = document.createElement("div");
  hCtl.className = "adv-row";
  hBody.appendChild(hCtl);
  for (const [id, label] of [["homeownership", "Owner-occupation lens"], ["second_homes", "Second-home lens"], ["vacancy", "Vacancy lens"]]) {
    const b = lensButton(app, id, label);
    if (b) hCtl.appendChild(b);
  }
  const ownDom = [0.45, 0.85];
  const ownColor = colorScale({ type: "seq", domain: ownDom, ramp: RAMPS.seq });
  const scatter = createScatter(hBody, {
    height: 300,
    points: counties.rows.map((r) => ({ key: r.key, x: r.v.second_homes, y: r.v.vacancy, s: r.v.population, c: r.v.homeownership, label: r.name, sub: r.sub, row: r })),
    x: { label: "Second homes", fmt: (v) => fmtShort("pct", v) },
    y: { label: "Vacant homes", fmt: (v) => fmtShort("pct", v) },
    size: { label: "Population", fmt: count3, max: 14, min: 1.4 },
    color: (c) => ownColor(c), colorLabel: "Owner-occupied", colorFmt: (v) => pct(v),
    labels: topBy(counties.rows, (r) => r.v.population, { n: 6 }).map((x) => x.r.key),
    onHover: (p) => { link.hover(p ? rowsHighlight(counties, [p.row]) : null); housingTable.setHot(p ? p.key : null, false); },
    onClick: (p) => counties.focus(p.row),
    onBrush: (set) => {
      const sel = set ? counties.rows.filter((r) => set.has(r.key)) : [];
      link.base(sel.length ? rowsHighlight(counties, sel, { dim: true }) : null, { frame: sel.length > 1 });
      housingTable.setSelected(set);
      selInfo.innerHTML = sel.length ? `<b>${int(sel.length)}</b> departments selected · ${count3(sel.reduce((a, r) => a + (r.v.population || 0), 0))} people ${frameBtn()}<button type="button" class="adv-mini" data-clear>Clear</button>` : "";
    },
  });
  hBody.insertAdjacentHTML("beforeend", rampLegend({ ramp: RAMPS.seq, domain: ownDom, fmt: (v) => fmtShort("pct", v), label: "Owner-occupied main homes" }));
  const selInfo = document.createElement("div");
  selInfo.className = "adv-brushinfo";
  hBody.appendChild(selInfo);
  const clearSel = () => { scatter.setSelected(null); housingTable.setSelected(null); link.base(null); selInfo.innerHTML = ""; };
  selInfo.addEventListener("click", (e) => { if (e.target.closest("[data-clear]")) clearSel(); });
  const housingTable = createTable(hBody, {
    caption: "Housing stock", rank: true, maxHeight: 250, rows: counties.rows, search: "Search departments",
    columns: [
      { key: "name", label: "Department", align: "l", value: (r) => r.name, html: (r) => `${esc(r.name)} <span class="sub">${esc(r.sub)}</span>` },
      { key: "homeownership", label: "Owner", value: (r) => r.v.homeownership, text: (r) => pct(r.v.homeownership), bar: { max: 1, color: "rgba(114,186,140,.32)" } },
      { key: "second", label: "Second", value: (r) => r.v.second_homes, text: (r) => pct(r.v.second_homes) },
      { key: "vacancy", label: "Vacant", value: (r) => r.v.vacancy, text: (r) => pct(r.v.vacancy) },
      { key: "income", label: "Income", value: (r) => r.v.income, text: (r) => money(r.v.income), hideBelow: 430 },
    ],
    sort: { key: "second", dir: "desc" },
    onHover: (r) => { link.hover(r ? rowsHighlight(counties, [r]) : null); scatter.setHot(r ? r.key : null); },
    onClick: (r) => counties.focus(r),
  });

  // --- poverty --------------------------------------------------------------------------------------------------
  const pBody = section(el, { title: "Poverty", note: "Departments by the share of people below 60% of the median standard of living. Hover a bar to outline those departments; the table lists them all." });
  const pCtl = document.createElement("div");
  pCtl.className = "adv-row";
  pBody.appendChild(pCtl);
  const lb = lensButton(app, "poverty", "Poverty lens");
  if (lb) pCtl.appendChild(lb);
  const pHost = document.createElement("div");
  pBody.appendChild(pHost);
  const natPov = wavg("poverty");
  const povHist = histogram(pHost, {
    values: counties.rows.map((r) => ({ key: r.key, v: r.v.poverty, w: r.v.population })), bins: 30, domain: [0, 0.32], height: 120,
    fmt: (v) => fmtShort("pct", v), unitLabel: "departments", label: "Histogram of department poverty rates",
    colorOf: (_, t) => colorScale({ type: "seq", domain: [0, 1], ramp: RAMPS.heat })(t),
    markers: fin(natPov) ? [{ v: natPov, label: `France ${pct(natPov)}` }] : [],
    onHover: (bin) => link.hover(bin ? rowsHighlight(counties, bin.keys.map((k) => counties.byKey.get(k)), { dim: true }) : null),
  });
  createTable(pBody, {
    caption: "Department poverty rates", rank: true, maxHeight: 240, rows: counties.rows.filter((r) => fin(r.v.poverty)), search: "Search departments",
    columns: [
      { key: "name", label: "Department", align: "l", value: (r) => r.name, html: (r) => `${esc(r.name)} <span class="sub">${esc(r.sub)}</span>` },
      { key: "population", label: "People", value: (r) => r.v.population, text: (r) => count3(r.v.population) },
      { key: "poverty", label: "Poverty", value: (r) => r.v.poverty, text: (r) => pct(r.v.poverty), bar: { max: 0.35, color: "rgba(232,119,74,.4)" } },
      { key: "income", label: "Income", value: (r) => r.v.income, text: (r) => money(r.v.income) },
    ],
    sort: { key: "poverty", dir: "desc" },
    onHover: (r) => link.hover(r ? rowsHighlight(counties, [r]) : null),
    onClick: (r) => counties.focus(r),
  });

  // --- unemployment ---------------------------------------------------------------------------------------------
  const uBody = section(el, { title: "Unemployment", note: `Unemployed ÷ labour force (${esc(data.vintage)}). Urban areas of ${count3(BIG_METRO)}+ people.` });
  const uHost = document.createElement("div");
  let uLevel = "states";
  segmented(uBody, { label: "Areas", value: uLevel, options: [{ value: "states", label: "Regions" }, { value: "metros", label: "Large urban areas" }], onChange: (v) => { uLevel = v; drawU(); } });
  uBody.appendChild(uHost);
  function drawU() {
    uHost.innerHTML = "";
    const lvU = uLevel === "states" ? states : metros;
    const min = uLevel === "states" ? 0 : BIG_METRO;
    const high = topBy(lvU.rows, (r) => r.v.unemployment, { n: 8, min });
    const low = topBy(lvU.rows, (r) => r.v.unemployment, { n: 8, min, asc: true });
    const max = Math.max(...high.map((x) => x.v));
    const mk = (list) => list.map((x) => ({ key: x.r.key, label: x.r.name, sub: uLevel === "metros" ? x.r.sub : "", value: x.v, text: pct(x.v), tone: x.v > n.unemployment * 1.03 ? "bad" : x.v < n.unemployment * 0.97 ? "good" : null, row: x.r }));
    const o = { max, onHover: (r) => link.hover(r ? rowsHighlight(lvU, [r.row]) : null), onClick: (r) => lvU.focus(r.row) };
    uHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Highest</h4>`);
    barList(uHost, { ...o, rows: mk(high) });
    uHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Lowest</h4>`);
    barList(uHost, { ...o, rows: mk(low) });
  }
  drawU();

  el.insertAdjacentHTML("beforeend", sourcesHtml(data, ["fr_insee_stats"], [
    "Median standard of living is an INSEE income measure per consumption unit, not a median household-income total.",
    "No comparable public French median home-value or rent series is used, so affordability and rent-burden charts from the US version are intentionally absent.",
    "Poverty means below 60% of the median standard of living; housing shares are shares of dwellings or main homes, not people.",
    ...(data.countiesOffMap ? [`${int(data.countiesOffMap)} of the smallest departments are smaller than one hex, so selecting them outlines nothing on the map.`] : []),
  ]));

  return {
    onMapHover(h) {
      const r = h.cell >= 0 ? counties.rowAtCell(h.cell) : null;
      scatter.setHot(r ? r.key : null);
      housingTable.setHot(r ? r.key : null);
      povHist.setHot(r ? povHist.binOf(r.v.poverty)?.i ?? null : null);
    },
    onEscape() {
      if (scatter.selected) { clearSel(); return true; }
      return false;
    },
  };
}
