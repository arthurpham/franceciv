// Military advisor ("General"): French defense bases from the Ministry of the Armed Forces' 2012 open-data file.
// Counts are stationed personnel at base seats, not troops counted at home and not a current order of battle.
import { esc, fin, el as mk } from "../core/util.js";
import { int, pct, count3 } from "../core/fmt.js";
import { barList } from "../core/charts.js";
import { createTable } from "../core/table.js";
import { section, tiles, sourcesHtml } from "../core/view.js";
import { rowsHighlight, extendData } from "../core/data.js";
import { focusPoint } from "../core/frame.js";

const COLOR = "#8796ab";
const TIER_LABEL = { major: "Major", base: "Base", site: "Site" };

export async function mount(ctx) {
  const { app, data, el, link } = ctx;
  await extendData(data, ["military"]);
  const mil = app.data.military;
  if (!mil) {
    el.innerHTML = `<p class="adv-empty pad">military.json is not built, so the General has nothing to report.</p>`;
    return {};
  }
  const { states: stLevel, metros } = data.levels;
  const insts = (mil.installations || []).map((it, i) => ({ ...it, key: it.id || String(i) }));
  const instById = new Map(insts.map((it) => [it.key, it]));
  const total = mil.national?.personnel?.total ?? mil.national?.personnel?.active?.total;
  const largest = [...insts].sort((a, b) => (b.personnel || 0) - (a.personnel || 0))[0];

  el.insertAdjacentHTML("beforeend", tiles([
    { label: "Stationed personnel", value: count3(total), sub: "sum of published base rows, 2012", color: COLOR },
    { label: "Defense bases", value: int(insts.length), sub: "geocoded base seats" },
    { label: "Largest base", value: largest ? count3(largest.personnel) : "–", sub: largest ? `${largest.name} · ${largest.seat_commune}` : "" },
  ]) + `<p class="adv-callout">${esc(mil.caveats || "")}</p>`);

  function flyTo(it) {
    if (!it || !fin(it.x) || !fin(it.y)) return;
    focusPoint(app, it.x, it.y, Math.min(app.cam.maxScale, Math.max(app.cam.scale, (app.cam.fitScale || 1) * 3.2)));
  }
  const bubbles = ctx.bubbles("bases", {
    rMax: 15, minR: 3, alpha: 0.62,
    tip: (b) => {
      const it = b.it;
      return `<b>${esc(it.name)}</b><br>${int(it.personnel)} stationed personnel (2012) · ${int(it.formations)} formations<br>${esc(it.seat_commune)} · ${esc(TIER_LABEL[it.tier] || it.tier)}`;
    },
    onHover: (b) => {
      table.setHot(b ? b.key : null);
      link.hover(b ? { cells: new Set([b.it.cell]), label: b.it.name } : null);
    },
    onClick: (b) => flyTo(b.it),
  });

  // --- installations -------------------------------------------------------------------------------------------
  const iBody = section(el, {
    title: "Defense bases", kicker: esc(mil.vintage?.installations || "Ministry of the Armed Forces, 2012"),
    note: esc(mil.rules?.installations || ""),
  });
  const table = createTable(iBody, {
    caption: "French defense bases", search: "Search bases, seats, regions", rank: true, maxHeight: 320,
    searchText: (r) => `${r.name} ${r.seat_commune} ${r.state} ${stLevel.byKey.get(r.state)?.name || ""}`,
    columns: [
      { key: "name", label: "Base", align: "l", width: "minmax(0,1.8fr)", value: (r) => r.name, html: (r) => `<i class="dot" style="background:${COLOR}"></i>${esc(r.name)}${r.joint ? ` <span class="sub">joint</span>` : ""}`, tip: (r) => `${r.name}: support-group seat ${r.seat_commune}; geocoding method: ${r.match}` },
      { key: "personnel", label: "Personnel", value: (r) => r.personnel, text: (r) => count3(r.personnel), bar: { max: Math.max(...insts.map((r) => r.personnel || 0), 1), color: "rgba(135,150,171,.35)" }, title: "Stationed personnel in 2012" },
      { key: "formations", label: "Formations", value: (r) => r.formations, text: (r) => r.formations == null ? "–" : int(r.formations), hideBelow: 430 },
      { key: "tier", label: "Tier", align: "l", width: "58px", value: (r) => ({ major: 0, base: 1, site: 2 })[r.tier], text: (r) => TIER_LABEL[r.tier] || r.tier, title: esc(mil.rules?.tier || "") },
      { key: "seat", label: "Seat", align: "l", width: "minmax(0,1fr)", value: (r) => r.seat_commune, text: (r) => r.seat_commune || "–", hideBelow: 520 },
      { key: "state", label: "Region", align: "l", width: "48px", value: (r) => r.state, text: (r) => r.state || "–" },
    ],
    rows: insts, sort: { key: "personnel", dir: "desc" },
    onHover: (r) => {
      bubbles.setHot(r ? r.key : null);
      link.hover(r ? { cells: new Set([r.cell]), label: r.name } : null);
    },
    onClick: flyTo,
  });
  bubbles.set(insts.filter((it) => fin(it.x) && fin(it.y)).map((it) => ({ key: it.key, x: it.x, y: it.y, value: it.personnel || 1, color: COLOR, it })));

  // --- regions -------------------------------------------------------------------------------------------------
  const stateRows = Object.entries(mil.states || {}).filter(([, s]) => s?.personnel?.total).map(([abbr, s]) => ({
    key: abbr, label: stLevel.byKey.get(abbr)?.name || abbr, value: s.personnel.total,
    sub: `${int(s.installations || 0)} base${s.installations === 1 ? "" : "s"}${s.ile_de_france_aggregate ? " + regional aggregate" : ""}`,
    row: stLevel.byKey.get(abbr), aggregate: s.ile_de_france_aggregate,
  })).sort((a, b) => b.value - a.value);
  if (stateRows.length) {
    const sBody = section(el, {
      title: "Stationed personnel by region",
      note: "Geocoded base seats plus the one aggregate Île-de-France row. This is not personnel by home residence and excludes overseas France.",
    });
    barList(sBody, {
      rank: true, compact: true, ariaLabel: "Stationed personnel by region",
      rows: stateRows.map((r) => ({ key: r.key, label: r.label, sub: r.sub, value: r.value, text: count3(r.value), color: COLOR })),
      onHover: (r) => {
        const row = r ? stateRows.find((x) => x.key === r.key)?.row : null;
        link.hover(row ? rowsHighlight(stLevel, [row], { dim: true, label: r.label }) : null);
      },
      onClick: (r) => {
        const row = stateRows.find((x) => x.key === r.key)?.row;
        if (row) stLevel.focus(row);
      },
    });
  }

  // --- garrison cities ------------------------------------------------------------------------------------------
  const garrisons = Object.entries(mil.cities || {}).map(([id, c]) => ({ ...c, key: id, row: metros.byKey.get(id) })).filter((g) => g.row)
    .sort((a, b) => (b.armed_forces || 0) - (a.armed_forces || 0));
  if (garrisons.length) {
    const gBody = section(el, { title: "Garrison cities", note: esc(mil.rules?.encampment || mil.rule || "") });
    createTable(gBody, {
      caption: "Garrison cities", rank: true, maxHeight: 280, search: "Search cities",
      searchText: (g) => g.row.name,
      columns: [
        { key: "name", label: "City", align: "l", width: "minmax(0,1.8fr)", value: (g) => g.row.name, html: (g) => `${esc(g.row.name)} <span class="sub">${esc(g.row.sub || "")}</span>`, tip: (g) => (g.installations || []).map((id) => instById.get(id)?.name || id).join(", ") || "Aggregate regional personnel only" },
        { key: "tier", label: "Tier", align: "l", width: "minmax(0,.7fr)", value: (g) => (g.tier === "fortress" ? 0 : 1), text: (g) => g.tier === "fortress" ? "Fortress" : "Garrison" },
        { key: "personnel", label: "Stationed", value: (g) => g.armed_forces, text: (g) => count3(g.armed_forces), title: "Stationed personnel assigned to this AAV by base seat; not residents in uniform" },
        { key: "share", label: "Share", value: (g) => g.share, text: (g) => pct(g.share), bar: { max: Math.max(...garrisons.map((g) => g.share || 0), 0.01), color: "rgba(135,150,171,.35)" }, title: "Stationed personnel ÷ AAV population" },
        { key: "bases", label: "Bases", value: (g) => g.installation_count, text: (g) => int(g.installation_count || 0), hideBelow: 430 },
      ],
      rows: garrisons, sort: { key: "personnel", dir: "desc" },
      onHover: (g) => link.hover(g ? rowsHighlight(metros, [g.row], { label: g.row.name }) : null),
      onClick: (g) => metros.focus(g.row),
    });
    gBody.insertAdjacentHTML("beforeend", `<p class="adv-note">Paris includes the file's one aggregate Île-de-France row because detailed bases in the region are not published in this file.</p>`);
  }

  // --- interpretation -------------------------------------------------------------------------------------------
  const cBody = section(el, { title: "What this does and does not show" });
  cBody.insertAdjacentHTML("beforeend", `<ul class="adv-list">
    <li>It shows 2012 <em>bases de défense</em>: joint support organisations and the personnel counted as stationed in them.</li>
    <li>Markers are at the support group's seat commune. They do not show every barracks, training ground, boundary or unit location.</li>
    <li>No branch split is published in this file, so every installation is shown as a joint defense base rather than guessed as Army, Navy or Air Force.</li>
    <li>No defense spending, veteran, reserve or current personnel geography is included because no comparable current public dataset was found.</li>
  </ul>`);

  el.insertAdjacentHTML("beforeend", sourcesHtml(data, mil.sources || ["fr_military"], [esc(mil.caveats || "")].filter(Boolean)));
  return {};
}
