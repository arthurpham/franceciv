// Multi-layer inspector embedded in city, region and geography cards. It reads the already-loaded lens value
// arrays for one hex cell, so opening it adds no network traffic; ranks and coverage statistics are cached per lens.
import { esc, int } from "../format.js";
import { formatLensValue } from "./lenses.js";
import { glyph } from "./icon.js";

const norm = (s) => String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
const isMissing = (v) => v == null || (typeof v === "number" && !Number.isFinite(v));

function upperBound(values, x) {
  let lo = 0, hi = values.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (values[mid] <= x) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

function compactRange(start, end) {
  const shortEnd = end.length === 2 || start.slice(0, 2) !== end.slice(0, 2) ? end : end.slice(2);
  return `${start}–${shortEnd}`;
}

const yearRangePattern = () => /\b((?:19|20)\d{2})\s*[–-]\s*((?:19|20)?\d{2})\b(?!-)/g;

function vintageYear(vintage) {
  const text = String(vintage || "");
  // Prefer an explicit statistical period over a later geographic-reference year ("census 2023, geography 2026").
  // Do not mistake ISO dates such as 2026-11-02 for year ranges.
  const range = yearRangePattern().exec(text);
  if (range) return compactRange(range[1], range[2]);
  return text.match(/\b(?:19|20)\d{2}\b/)?.[0] || "";
}

function measurementYear(lens, fallback) {
  const text = String(lens.description || "");
  const ranges = [...text.matchAll(yearRangePattern())];
  if (!ranges.length) return fallback;
  const first = compactRange(ranges[0][1], ranges[0][2]);
  if (ranges.length > 1 && /\b(?:difference|change|between)\b/i.test(text)) return `${first} vs ${compactRange(ranges[1][1], ranges[1][2])}`;
  return first;
}

/**
 * opts: {lensFile, sources, w, getActiveLens(), onPick(lens)}
 * section(cell) returns a city/state panel section; wire(panel, cell) fills it. update() reuses an open panel when
 * the user clicks another hex in the same region, and refresh() updates the active lens after external lens changes.
 */
export function createLocationInspector(opts) {
  const lensFile = opts.lensFile || { groups: [], lenses: [] };
  const lenses = (lensFile.lenses || []).filter((l) => l?.id && Array.isArray(l.values));
  const sourceById = new Map((opts.sources || []).map((s) => [s.id, s]));
  const w = opts.w;
  const statsCache = new Map();
  let query = "";
  let showMissing = false;
  let openGroups = new Set();
  let groupsTouched = false;

  const explicitGroups = [...(lensFile.groups || [])];
  const groupById = new Map(explicitGroups.map((g) => [g.id, g]));
  const groups = [...explicitGroups];
  const groupTotals = new Map();
  for (const lens of lenses) {
    const id = lens.group || "__other";
    if (!groupById.has(id)) {
      const g = { id, name: id === "__other" ? "Other" : id };
      groupById.set(id, g);
      groups.push(g);
    }
    groupTotals.set(id, (groupTotals.get(id) || 0) + 1);
  }

  function stats(lens) {
    if (statsCache.has(lens.id)) return statsCache.get(lens.id);
    const values = [];
    for (let i = 0; i < lens.values.length; i++) {
      const v = lens.values[i];
      if (w.raw.owner?.[i] >= 0 && typeof v === "number" && Number.isFinite(v)) values.push(v);
    }
    values.sort((a, b) => a - b);
    const out = { values, count: values.length };
    statsCache.set(lens.id, out);
    return out;
  }

  function rank(lens, value) {
    if (lens.format === "category" || typeof value !== "number" || !Number.isFinite(value)) return null;
    const st = stats(lens);
    if (!st.count) return null;
    // Competition ranking among measured cells, highest raw value first. Ties share the better rank.
    const r = st.count - upperBound(st.values, value) + 1;
    return { rank: r, count: st.count, share: r / st.count };
  }

  const sourceOf = (lens) => sourceById.get(lens.source) || null;
  const yearOf = (lens) => vintageYear(sourceOf(lens)?.vintage || "");
  const sourceLabel = (lens) => {
    const s = sourceOf(lens);
    const year = measurementYear(lens, yearOf(lens));
    return [year, s?.publisher || s?.title || lens.source].filter(Boolean).join(" · ");
  };

  function place(cell) {
    const raw = w.raw;
    const bits = [];
    const city = w.cityByCell.get(cell);
    if (city) bits.push(city.name);
    const ci = raw.county?.[cell];
    if (ci >= 0 && raw.counties?.[ci]) bits.push(raw.counties[ci].name);
    const owner = raw.owner?.[cell];
    if (owner >= 0 && raw.states?.[owner]) bits.push(raw.states[owner].name);
    return bits.filter((x, i) => x && bits.indexOf(x) === i).join(" · ") || "French territory";
  }

  function rowHtml({ lens, value, missing }) {
    const r = missing ? null : rank(lens, value);
    const active = opts.getActiveLens?.()?.id === lens.id;
    const src = sourceLabel(lens);
    const direction = lens.higher_is === "better" ? "higher is better" : lens.higher_is === "worse" ? "higher is worse" : "direction neutral";
    const title = [lens.description || lens.name, direction, src, sourceOf(lens)?.vintage].filter(Boolean).join("\n");
    const meta = missing ? `No data — unavailable, suppressed or outside coverage${src ? ` · ${src}` : ""}` : src;
    return `<button type="button" class="li-row${missing ? " missing" : ""}${active ? " active" : ""}" data-lens="${esc(lens.id)}" title="${esc(title)}">
      <span class="li-ic">${glyph(lens, 15)}</span>
      <span class="li-main"><span class="li-name">${esc(lens.name)}</span>
        <span class="li-meta">${esc(meta)}</span></span>
      <span class="li-value"><b>${missing ? "—" : esc(formatLensValue(lens, value))}</b>${r ? `<span class="li-rank" title="Rank among measured hex cells, highest raw value first">#${int(r.rank)} of ${int(r.count)}</span>` : ""}</span>
    </button>`;
  }

  function entriesFor(cell) {
    const q = norm(query);
    const entries = [];
    for (const lens of lenses) {
      const value = lens.values[cell];
      const missing = isMissing(value);
      if (missing && !showMissing) continue;
      if (q) {
        const g = groupById.get(lens.group || "__other");
        const hay = norm([lens.name, lens.description, lens.unit, g?.name, sourceLabel(lens)].filter(Boolean).join(" "));
        if (!hay.includes(q)) continue;
      }
      entries.push({ lens, value, missing, group: lens.group || "__other" });
    }
    return entries;
  }

  function activeHtml(cell) {
    const active = opts.getActiveLens?.();
    if (!active?.id || !active.values) return `<div class="li-active empty">Terrain view — pick a row below to colour the map and pin that lens here.</div>`;
    const value = active.values[cell];
    const missing = isMissing(value);
    const r = missing ? null : rank(active, value);
    const src = sourceLabel(active);
    return `<div class="li-active" title="${esc(active.description || active.name)}">
      <span class="li-bigic">${glyph(active, 22)}</span>
      <span class="li-active-main"><span class="li-kicker">ACTIVE LENS</span><b>${esc(active.name)}</b><span>${esc(src)}</span></span>
      <span class="li-active-value">${missing ? "No data" : esc(formatLensValue(active, value))}${r ? `<small>#${int(r.rank)} of ${int(r.count)}</small>` : ""}</span>
    </div>`;
  }

  const ownedCell = (cell) => Number.isInteger(cell) && cell >= 0 && cell < w.grid.size && w.raw.owner?.[cell] >= 0;
  const resolvedCache = new Map();
  // Commune/EPCI reference points can fall in a coastal or foreign hex even though the territory itself is French.
  // Use the closest measured hex and disclose the approximation rather than dropping the whole local-data section.
  function resolveCell(cell, point = null) {
    if (!Number.isInteger(cell) || cell < 0 || cell >= w.grid.size) return null;
    if (ownedCell(cell)) return { cell, approximate: false };
    const px = Number.isFinite(point?.x) ? point.x : null;
    const py = Number.isFinite(point?.y) ? point.y : null;
    const key = px == null || py == null ? cell : `${cell}:${px}:${py}`;
    if (resolvedCache.has(key)) return resolvedCache.get(key);
    const x0 = px ?? w.grid.cx(cell), y0 = py ?? w.grid.cy(cell);
    let best = -1, bestD = Infinity;
    for (let i = 0; i < w.grid.size; i++) {
      if (!ownedCell(i)) continue;
      const dx = w.grid.cx(i) - x0, dy = w.grid.cy(i) - y0;
      const d = dx * dx + dy * dy;
      if (d < bestD) { bestD = d; best = i; }
    }
    const out = best >= 0 ? { cell: best, approximate: true, distance: Math.sqrt(bestD) } : null;
    resolvedCache.set(key, out);
    return out;
  }

  function renderResults(root, cell) {
    const entries = entriesFor(cell);
    const measuredTotal = lenses.filter((l) => !isMissing(l.values[cell])).length;
    const hiddenMissing = lenses.length - measuredTotal;
    const byGroup = new Map(groups.map((g) => [g.id, []]));
    for (const e of entries) {
      if (!byGroup.has(e.group)) byGroup.set(e.group, []);
      byGroup.get(e.group).push(e);
    }
    let groupIndex = -1;
    const activeGroup = opts.getActiveLens?.()?.group || null;
    const body = groups.map((g) => {
      const rows = byGroup.get(g.id) || [];
      if (!rows.length) return "";
      groupIndex++;
      const measured = lenses.filter((l) => (l.group || "__other") === g.id && !isMissing(l.values[cell])).length;
      const isOpen = groupsTouched ? openGroups.has(g.id) : (query.trim() ? true : (g.id === activeGroup || groupIndex === 0));
      return `<details class="li-group" data-group="${esc(g.id)}"${isOpen ? " open" : ""}>
        <summary><span>${esc(g.name)}</span><span class="li-count" title="Measured layers in this group at the selected hex">${measured}/${groupTotals.get(g.id) || rows.length}</span></summary>
        <div class="li-rows">${rows.map(rowHtml).join("")}</div>
      </details>`;
    }).join("");
    root.querySelector(".li-results").innerHTML = `
      <div class="li-summary"><b>${measuredTotal}</b> of ${lenses.length} layers measured here${hiddenMissing && !showMissing ? ` · ${hiddenMissing} no-data hidden` : ""}</div>
      ${activeHtml(cell)}
      ${body || `<div class="li-empty">No layer matches “${esc(query)}” at this location.</div>`}
      <p class="li-note">Values describe ${root._liApproximate ? "the nearest measured hex to the reference point" : "the containing/reference hex cell"}, not an exact address or a whole commune/EPCI/IRIS. “No data” means unavailable, suppressed or outside source coverage; it is not zero unless the lens definition says so. Rankings compare measured hex cells, highest raw value first.</p>`;
  }

  function layout(root, requestedCell, point = null) {
    const resolved = resolveCell(requestedCell, point);
    if (!resolved) return;
    const cell = resolved.cell;
    root.dataset.cell = String(cell);
    root._liApproximate = resolved.approximate;
    const elev = w.raw.elev?.[cell];
    root.innerHTML = `
      <div class="li-context"><b>${esc(place(cell))}</b><span>8 km hex${resolved.approximate ? ` · nearest measured · ~${int(resolved.distance)} km away` : ""}${Number.isFinite(elev) ? ` · ${int(elev)} m mean elevation` : ""}</span></div>
      <div class="li-tools">
        <input class="li-search" type="search" value="${esc(query)}" placeholder="Filter local layers…" aria-label="Filter local layers">
        <label class="li-toggle" title="Include layers with no measured value at this hex"><input type="checkbox"${showMissing ? " checked" : ""}> show no data</label>
      </div>
      <div class="li-results"></div>`;
    root.querySelector(".li-search").addEventListener("input", (e) => {
      query = e.target.value;
      renderResults(root, cell);
    });
    root.querySelector(".li-toggle input").addEventListener("change", (e) => {
      showMissing = !!e.target.checked;
      renderResults(root, cell);
    });
    if (!root._liWired) {
      root._liWired = true;
      root.addEventListener("click", (e) => {
        const row = e.target.closest("[data-lens]");
        if (!row) return;
        const lens = lenses.find((l) => l.id === row.dataset.lens);
        if (!lens) return;
        opts.onPick?.(lens);
      });
      root.addEventListener("click", (e) => {
        const summary = e.target.closest("summary");
        if (!summary) return;
        const d = summary.closest("details[data-group]");
        if (!d) return;
        if (!groupsTouched) {
          // Preserve the automatic expansion state before applying the user's first manual toggle.
          openGroups = new Set([...root.querySelectorAll("details[data-group]")].filter((x) => x.open).map((x) => x.dataset.group));
          groupsTouched = true;
        }
        // The details element's open state flips after the click handler, so read it on the next task.
        setTimeout(() => {
          if (d.open) openGroups.add(d.dataset.group);
          else openGroups.delete(d.dataset.group);
        }, 0);
      });
    }
    renderResults(root, cell);
  }

  return {
    section(cell, point = null) {
      if (!resolveCell(cell, point)) return null;
      return { title: "Local data inspector", html: `<div class="location-inspector" data-cell="${cell}"></div>` };
    },
    wire(panel, cell, point = null) {
      const root = panel.querySelector(".location-inspector");
      if (root && resolveCell(cell, point)) layout(root, cell, point);
    },
    update(panel, cell, point = null) {
      const root = panel?.querySelector(".location-inspector");
      if (!root || !resolveCell(cell, point)) return false;
      layout(root, cell, point);
      return true;
    },
    refresh(panel) {
      const root = panel?.querySelector(".location-inspector");
      if (!root) return;
      const cell = Number(root.dataset.cell);
      if (ownedCell(cell)) renderResults(root, cell);
    },
  };
}
