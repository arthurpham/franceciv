// Knowledge advisor: education and the Science yield from INSEE/Eurostat workplace-employment data.
import { esc, fin, ratio, colorScale, robustDomain, RAMPS } from "../core/util.js";
import { money, pct, int, count3, fmtShort } from "../core/fmt.js";
import { barList, rampLegend } from "../core/charts.js";
import { createScatter } from "../core/scatter.js";
import { section, tiles, segmented, mapPicker, frameBtn, sourcesHtml, topBy } from "../core/view.js";
import { rowsHighlight } from "../core/data.js";
import { scienceLens } from "../core/lenses.js";

const METRO_MIN = 250000;

export function mount(ctx) {
  const { app, data, el, link } = ctx;
  const n = data.nat;
  const nation = app.data.nation;
  const { metros, counties } = data.levels;
  const sci = nation.yields?.find((y) => y.key === "science");
  const scienceWorkers = n.yields?.science;
  const scienceShare = ratio(scienceWorkers, n.employed);
  const wavg = (k) => {
    if (!counties) return null;
    let a = 0, w = 0;
    for (const r of counties.rows) if (fin(r.v[k]) && fin(r.v.population)) { a += r.v[k] * r.v.population; w += r.v.population; }
    return w ? a / w : null;
  };

  el.insertAdjacentHTML("beforeend", tiles([
    { label: "Science workers", value: count3(scienceWorkers), sub: `${pct(scienceShare)} of workplace employment`, color: sci?.color },
    { label: "Bac+2 or higher", value: pct(wavg("higher_education")), sub: "population-weighted departmental mean" },
  ]));

  const mapRow = document.createElement("div");
  mapRow.className = "adv-sec adv-mapsec";
  el.appendChild(mapRow);
  const picker = mapPicker(ctx, mapRow, {
    value: counties ? "education" : "science",
    options: [
      ...(counties ? [{ value: "education", label: "Education", lens: () => "higher_education" }] : []),
      { value: "science", label: "Science jobs", lens: () => scienceLens(data) },
      { value: "terrain", label: "Terrain", lens: () => null },
    ],
  });

  // --- science yield --------------------------------------------------------------------------------------------
  const sBody = section(el, { title: "The Science yield", note: `${esc(sci?.description || "Workers in professional, scientific & technical services and information.")} Urban areas of ${count3(METRO_MIN)}+ people for the share ranking.` });
  const sHost = document.createElement("div");
  let mode = "share";
  segmented(sBody, { label: "Rank by", value: mode, options: [{ value: "share", label: "Share of jobs" }, { value: "abs", label: "Most workers" }], onChange: (v) => { mode = v; drawSci(); } });
  const sMap = document.createElement("button");
  sMap.type = "button";
  sMap.className = "adv-mini";
  sMap.textContent = "Colour the map by science jobs";
  sMap.addEventListener("click", () => picker.set("science"));
  sBody.querySelector(".adv-seg")?.after(sMap);
  sBody.appendChild(sHost);
  const share = (r) => ratio(r.v.y_science, r.v.employed);
  function drawSci() {
    sHost.innerHTML = "";
    const list = mode === "abs" ? topBy(metros.rows, (r) => r.v.y_science, { n: 12 }) : topBy(metros.rows, share, { n: 12, min: METRO_MIN });
    barList(sHost, {
      rank: true, ariaLabel: "Science leaders",
      rows: list.map((x) => ({ key: x.r.key, label: x.r.name, sub: mode === "abs" ? pct(share(x.r)) : `×${(share(x.r) / scienceShare).toFixed(2)} France`, value: x.v, text: mode === "abs" ? count3(x.v) : pct(x.v), color: sci?.color, row: x.r })),
      onHover: (r) => link.hover(r ? rowsHighlight(metros, [r.row]) : null),
      onClick: (r) => metros.focus(r.row),
    });
  }
  drawSci();

  if (!counties) {
    el.insertAdjacentHTML("beforeend", `<p class="adv-empty pad">counties.json is not built, so the department charts are missing.</p>`);
    el.insertAdjacentHTML("beforeend", sourcesHtml(data, ["fr_insee_stats"], []));
    return {};
  }

  // --- education vs income --------------------------------------------------------------------------------------
  const dBody = section(el, { title: "Education and income", note: "Share of adults with a Bac+2 or higher qualification against median standard of living; colour = unemployment. Drag to select; hover the map to find a place." });
  const dCtl = document.createElement("div");
  dCtl.className = "adv-row";
  dBody.appendChild(dCtl);
  let level = "counties";
  segmented(dCtl, { label: "Places", value: level, options: [{ value: "counties", label: "Departments" }, { value: "metros", label: "Urban areas" }], onChange: (v) => { level = v; drawDeg(); } });
  const lv = () => data.levels[level];
  const inc = (r) => (level === "counties" ? r.v.income : r.v.median_income);
  const unempDom = robustDomain(counties.rows.map((r) => r.v.unemployment), 0.02) || [0.06, 0.15];
  const unempColor = colorScale({ type: "seq", domain: unempDom, ramp: RAMPS.heat });
  const scatter = createScatter(dBody, {
    height: 300, points: [],
    x: { label: "Bac+2 or higher", fmt: (v) => fmtShort("pct", v) },
    y: { label: "Median standard of living", fmt: money, log: true },
    size: { label: "Population", fmt: count3, max: 14, min: 1.4 },
    color: (c) => unempColor(c), colorLabel: "Unemployment", colorFmt: (v) => pct(v),
    onHover: (p) => link.hover(p ? rowsHighlight(lv(), [p.row]) : null),
    onClick: (p) => lv().focus(p.row),
    onBrush: (set) => {
      const sel = set ? lv().rows.filter((r) => set.has(r.key)) : [];
      link.base(sel.length ? rowsHighlight(lv(), sel, { dim: true }) : null, { frame: sel.length > 1 });
      selInfo.innerHTML = sel.length ? `<b>${int(sel.length)}</b> ${level === "counties" ? "departments" : "urban areas"} · ${count3(sel.reduce((a, r) => a + (r.v.population || 0), 0))} people ${frameBtn()}<button type="button" class="adv-mini" data-clear>Clear</button>` : "";
    },
  });
  dBody.insertAdjacentHTML("beforeend", rampLegend({ ramp: RAMPS.heat, domain: unempDom, fmt: (v) => fmtShort("pct", v), label: "Unemployment" }));
  const selInfo = document.createElement("div");
  selInfo.className = "adv-brushinfo";
  dBody.appendChild(selInfo);
  const clearSel = () => { scatter.setSelected(null); link.base(null); selInfo.innerHTML = ""; };
  selInfo.addEventListener("click", (e) => { if (e.target.closest("[data-clear]")) clearSel(); });
  function drawDeg() {
    clearSel();
    const rows = lv().rows.filter((r) => fin(r.v.higher_education) && fin(inc(r)));
    scatter.update({
      points: rows.map((r) => ({ key: r.key, x: r.v.higher_education, y: inc(r), s: r.v.population, c: r.v.unemployment, label: r.name, sub: r.sub, row: r })),
      labels: topBy(rows, (r) => r.v.population, { n: 6 }).map((x) => x.r.key),
    });
  }
  drawDeg();

  el.insertAdjacentHTML("beforeend", sourcesHtml(data, ["fr_insee_stats", "fr_eurostat"], [
    "Science workers are workplace jobs in information/communication plus professional, scientific and technical activities; they cover whole industries, not only researchers.",
    `Department education, income and unemployment figures are ${esc(data.countyVintage)}; urban-area education values are population-weighted roll-ups of their departments.`,
    "INSEE education here means the share of adults whose highest diploma is Bac+2 or higher; it is not the same as the original US bachelor's-degree measure.",
    ...(data.countiesOffMap ? [`${int(data.countiesOffMap)} of the smallest departments are smaller than one hex, so selecting them outlines nothing on the map.`] : []),
  ]));

  return {
    onMapHover(h) {
      const r = h.cell >= 0 ? lv().rowAtCell(h.cell) : null;
      scatter.setHot(r ? r.key : null);
    },
    onEscape() {
      if (scatter.selected) { clearSel(); return true; }
      return false;
    },
  };
}
