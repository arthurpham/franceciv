// The advisors' data model: three "levels" (states, metros, counties) of rows with typed fields, plus the links
// between rows and the hex map (row → highlight, cell → row). Built once from app.data (counties.json optional).
//
//   level = {id, label, noun, rows: [row], fields: [field], field(key), value(row, key),
//            highlight(rows, opts) → app.state.highlight, rowAtCell(cell) → row | null, focus(row), byKey: Map}
//   row   = {key, name, sub, level, ref, v: {fieldKey: value}}
//   field = {key, label, format, unit, higher_is, source, description, lens?, group, derived?}
import { fin, ratio } from "./util.js";
import { frameBox } from "./frame.js";

const COUNTY_LENS = {
  density: "density", income: "income", poverty: "poverty", homeownership: "homeownership", second_homes: "second_homes", vacancy: "vacancy",
  unemployment: "unemployment", higher_education: "higher_education", seniors: "seniors", immigration: "immigration",
  public_transit: "public_transit", car_commuting: "car_commuting", disasters: "disasters", flood_events: "flood_events", drought_events: "drought_events",
  macron_2022: "macron_2022", lepen_2022: "lepen_2022", abstention_2022: "abstention_2022", forest: "forest", crop: "farmland", developed: "developed",
};
// Department measures we can roll up to states and metros as population-weighted means.
const ROLLUP = ["density", "income", "poverty", "higher_education", "seniors", "immigration", "public_transit", "car_commuting", "homeownership", "second_homes", "vacancy", "disasters", "flood_events", "drought_events", "macron_2022", "lepen_2022", "abstention_2022"];
// Rolled-up means that only approximate the area's true value (a median or an index whose denominator is not population).
const APPROX = new Set(["income", "disasters"]);
// No count/share pairs are currently rolled up from departments.
const SUMS = [];
const LAND_KEYS = ["forest", "crop", "pasture", "grass", "shrub", "wetland", "developed"];
export const LAND_LABEL = {
  forest: "Forest", crop: "Cropland", pasture: "Pasture & hay", grass: "Grassland", shrub: "Scrub & desert", wetland: "Wetland", developed: "Built-up",
};
export const LAND_COLOR = {
  forest: "#3f7a3a", crop: "#d2c457", pasture: "#93b852", grass: "#b9b06a", shrub: "#c9a874", wetland: "#4f9a86", developed: "#9a8f9e",
};
export { LAND_KEYS };

export function buildData(app) {
  const { cities = [], states = [], nation = {}, counties, resources, sources = [] } = app.data;
  const w = app.w;
  const grid = w.grid;
  const owner = w.raw.owner;
  const countyOf = w.raw.county || [];
  const n = grid.size;

  // --- cell indexes ---------------------------------------------------------------------------------------------
  const stateCells = new Map();
  const countyCells = new Map();
  for (let i = 0; i < n; i++) {
    const o = owner[i];
    if (!(o >= 0)) continue;
    if (!stateCells.has(o)) stateCells.set(o, []);
    stateCells.get(o).push(i);
    const c = countyOf[i];
    if (c >= 0) {
      if (!countyCells.has(c)) countyCells.set(c, []);
      countyCells.get(c).push(i);
    }
  }
  // cell → metro: footprints, smaller metros first so a bigger metro's majority wins; then every city's own cell.
  const cellMetro = new Map();
  for (let k = cities.length - 1; k >= 0; k--) for (const cell of cities[k].footprint || []) cellMetro.set(cell, cities[k]);
  for (const c of cities) if (c.cell != null) cellMetro.set(c.cell, c);

  const srcTitle = new Map(sources.map((s) => [s.id, s]));
  const nat = nation.nation || {};
  const vintage = nation.vintage || "INSEE census";
  const countyVintage = counties?.vintage || "INSEE / Eurostat";

  // --- fields ---------------------------------------------------------------------------------------------------
  const F = (key, label, format, o = {}) => ({ key, label, format, unit: o.unit || null, higher_is: o.higher_is || "neutral", source: o.source || "", description: o.description || "", lens: o.lens || null, group: o.group || "Economy", derived: !!o.derived });
  const econFields = (src) => [
    F("population", "Population", "int", { unit: "people", source: src, group: "People", description: `Residents (${vintage}).`, lens: "density" }),
    F("growth", "Growth", "signed", { unit: "population change", higher_is: "neutral", source: "fr_insee_stats", group: "People", description: `Population change ${(nat.growth_years || []).join("–")} in INSEE comparateur-de-territoires populations, on current borders.` }),
    F("gdp", "GDP", "money", { unit: "euros per year", source: "fr_eurostat", description: `${nation.gdp_vintage || "Eurostat regional accounts"}: GDP in current euros, counted where the work is done.` }),
    F("gdp_pc", "GDP per person", "eur", { unit: "euros per resident", higher_is: "good", source: "fr_eurostat", description: "GDP ÷ residents. Regional GDP and population can come from different statistical years." }),
    F("median_income", "Standard of living", "eur", { unit: "median standard of living", higher_is: "good", source: src, group: "Prosperity", description: `Median standard of living (${vintage}).`, lens: "income" }),
    F("homeownership", "Owner-occupied homes", "pct", { unit: "share of main homes", higher_is: "good", source: "fr_insee_stats", group: "Prosperity", description: "Owner-occupied main homes ÷ all main homes (INSEE Comparateur 2023).", lens: "homeownership" }),
    F("second_homes", "Second homes", "pct", { unit: "share of dwellings", source: "fr_insee_stats", group: "Prosperity", description: "Second homes ÷ all dwellings (INSEE Comparateur 2023).", lens: "second_homes" }),
    F("vacancy", "Vacant homes", "pct", { unit: "share of dwellings", higher_is: "bad", source: "fr_insee_stats", group: "Prosperity", description: "Vacant dwellings ÷ all dwellings (INSEE Comparateur 2023).", lens: "vacancy" }),
    F("unemployment", "Unemployment", "pct", { unit: "unemployed ÷ labour force", higher_is: "bad", source: src, group: "Prosperity", description: `Unemployed ÷ labour force (${vintage}).` }),
    F("employed", "Workplace employment", "int", { unit: "jobs", source: src, description: `Jobs counted at employers/workplaces in the area (${vintage}).` }),
    ...(nation.yields || []).filter((y) => y.unit !== "usd").map((y) => F(`y_${y.key}`, `${y.label} workers`, "int", { unit: "workers", source: src, group: "Yields", description: y.description })),
  ];
  const rollupFields = () => counties ? [...ROLLUP.map((k) => {
    const f = counties.fields.find((x) => x.key === k);
    if (!f) return null;
    const approx = APPROX.has(k);
    return F(k, f.label + (approx ? " ≈" : ""), f.format, {
      unit: f.unit, higher_is: f.higher_is, source: f.source || "fr_insee_stats", group: groupOf(k), lens: COUNTY_LENS[k],
      description: k === "density" ? `Residents ÷ land area, summed over member departments (${countyVintage}).`
        : `${f.description} Rolled up from departments as a population-weighted mean${approx ? " (an approximation: not the area's own figure)" : ""}${!f.source ? ` (${countyVintage})` : ""}.`,
      derived: true,
    });
  }), ...SUMS.flatMap(([n, p]) => {
    const fn = counties.fields.find((x) => x.key === n), fp = counties.fields.find((x) => x.key === p);
    if (!fn || !fp) return [];
    return [
      F(n, fn.label, fn.format, { unit: fn.unit, source: fn.source, group: groupOf(n), description: `${fn.description} Summed over member departments (${countyVintage}).`, derived: true }),
      F(p, fp.label, fp.format, { unit: fp.unit, source: fp.source, group: groupOf(p), lens: COUNTY_LENS[p], description: `${fp.description} Summed counts over member departments ÷ their summed base populations (${countyVintage}).`, derived: true }),
    ];
  })].filter(Boolean) : [];

  // --- roll-ups from departments -------------------------------------------------------------------------------------
  const roll = { states: new Map(), metros: new Map() };
  const cRows = [];
  if (counties) {
    const col = Object.fromEntries(counties.columns.map((k, j) => [k, j]));
    counties.rows.forEach((r, i) => cRows.push({ r, i }));
    const add = (map, key, r) => {
      if (key == null) return;
      let a = map.get(key);
      if (!a) map.set(key, (a = { pop: 0, land: 0, s: {}, wt: {}, n: {}, d: {}, dn: {}, dp: {}, zp: {} }));
      const pop = r[col.population];
      if (fin(pop)) a.pop += pop;
      if (fin(r[col.land_km2])) a.land += r[col.land_km2];
      for (const k of ROLLUP) {
        if (k === "density") continue;
        const v = r[col[k]];
        if (fin(v) && fin(pop) && pop > 0) {
          a.s[k] = (a.s[k] || 0) + v * pop;
          a.wt[k] = (a.wt[k] || 0) + pop;
        }
      }
      for (const [n, p] of SUMS) {
        if (col[n] == null) continue;
        const c = r[col[n]], s = col[p] != null ? r[col[p]] : null;
        if (!fin(c)) continue;
        a.n[n] = (a.n[n] || 0) + c;
        // A county with a zero count (share 0) has no implied base: it is estimated from its population at the
        // base-to-population ratio of the other counties (if every county is zero the share stays null, not 0).
        if (fin(s) && s > 0) {
          a.d[n] = (a.d[n] || 0) + c / s;
          a.dn[n] = (a.dn[n] || 0) + c;
          if (fin(pop)) a.dp[n] = (a.dp[n] || 0) + pop;
        } else if (c === 0 && fin(pop)) a.zp[n] = (a.zp[n] || 0) + pop;
      }
    };
    for (const { r } of cRows) {
      add(roll.states, r[col.state], r);
      add(roll.metros, r[col.aav], r);
    }
  }
  const rolled = (map, key) => {
    const a = map.get(key);
    const out = {};
    if (!a) return out;
    out.density = a.land > 0 ? a.pop / a.land : null;
    out.land_km2 = a.land || null;
    for (const k of ROLLUP) if (k !== "density") out[k] = a.wt[k] ? a.s[k] / a.wt[k] : null;
    for (const [n, p] of SUMS) {
      out[n] = a.n[n] ?? null;
      const zeroBase = a.zp[n] && a.dp[n] ? (a.zp[n] * a.d[n]) / a.dp[n] : 0;
      out[p] = a.d[n] > 0 ? a.dn[n] / (a.d[n] + zeroBase) : null;
    }
    return out;
  };

  const econValues = (o) => ({
    population: o.population ?? null,
    growth: o.growth ?? null,
    gdp: o.gdp ?? o.yields?.gold ?? null,
    gdp_pc: ratio(o.gdp ?? o.yields?.gold, o.population),
    median_income: o.median_income ?? null,
    median_rent: o.median_rent ?? null,
    home_value: o.home_value ?? null,
    affordability: ratio(o.home_value, o.median_income),
    rent_burden: o.rent_burden ?? null,
    unemployment: o.unemployment ?? null,
    employed: o.employed ?? null,
    ...Object.fromEntries((nation.yields || []).filter((y) => y.unit !== "usd").map((y) => [`y_${y.key}`, o.yields?.[y.key] ?? null])),
  });

  // --- resources by place ---------------------------------------------------------------------------------------
  const items = resources?.items || [];
  const typeById = new Map((resources?.types || []).map((t) => [t.id, t]));
  const mwByMetro = new Map();
  items.forEach((it) => {
    if (typeById.get(it.type)?.unit !== "MW" || !fin(it.value) || !it.aav) return;
    mwByMetro.set(it.aav, (mwByMetro.get(it.aav) || 0) + it.value);
  });

  // --- states ---------------------------------------------------------------------------------------------------
  const stateRows = (Array.isArray(states) ? states : []).map((s, idx) => ({
    key: s.abbr, name: s.name, sub: s.abbr, level: "states", ref: idx,
    v: {
      name: s.name, abbr: s.abbr, ...econValues(s), ...rolled(roll.states, s.abbr),
      ...Object.fromEntries(LAND_KEYS.map((k) => [`land_${k}`, s.land?.[k] ?? null])),
      energy_mw: s.energy ? s.energy.total : null,
    },
  }));
  const landFields = LAND_KEYS.map((k) => F(`land_${k}`, LAND_LABEL[k], "pct", { unit: "share of land", source: "fr_corine", group: "Land", description: `Share of the land in ${LAND_LABEL[k].toLowerCase()} (CORINE Land Cover, mean over the area's hexes).`, lens: k === "forest" ? "forest" : k === "developed" ? "developed" : null }));
  const energyField = F("energy_mw", "Mapped power", "mw", { unit: "MW of mapped sites", source: "fr_energy", group: "Energy", description: "Capacity of the power sites mapped as resources (each type above its size threshold): not total generating capacity." });
  const states_ = makeLevel({
    id: "states", label: "Regions", noun: "region",
    rows: stateRows,
    fields: [F("name", "Region", "text", { group: "Name" }), ...econFields("fr_insee_stats"), ...rollupFields(), F("land_km2", "Land area", "km2", { unit: "km²", source: "fr_insee_stats", group: "Land", derived: true }), ...landFields, energyField],
    highlight: (rows) => ({ states: new Set(rows.map((r) => r.ref)) }),
    rowAtCell: (cell, byKey) => (owner[cell] >= 0 ? stateRows[owner[cell]] || null : null),
    focus: (row) => app.selectState(row.ref, { fly: true }),
    cellsOf: (row) => stateCells.get(row.ref) || [],
  });

  // --- metros ---------------------------------------------------------------------------------------------------
  const metroRows = cities.map((c) => ({
    key: c.id, name: c.name, sub: (c.states || []).join("–"), level: "metros", ref: c,
    v: {
      name: c.name, states: (c.states || []).join("–"), kind: "AAV",
      ...econValues(c), ...rolled(roll.metros, c.id), energy_mw: mwByMetro.get(c.id) ?? 0,
    },
  }));
  const metroByCity = new Map(metroRows.map((r) => [r.ref, r]));
  const metros = makeLevel({
    id: "metros", label: "Urban areas", noun: "urban area",
    rows: metroRows,
    fields: [F("name", "Urban area", "text", { group: "Name" }), F("states", "Regions", "text", { group: "Name" }), F("kind", "Type", "text", { group: "Name", description: "Aire d'attraction des villes (INSEE 2020): a functional urban area, not an administrative metro government." }), ...econFields("fr_insee_stats"), ...rollupFields(), F("land_km2", "Land area", "km2", { unit: "km²", source: "fr_insee_stats", group: "Land", derived: true }), energyField],
    highlight: (rows, o = {}) => {
      const cells = new Set();
      for (const r of rows) for (const c of r.ref.footprint || [r.ref.cell]) cells.add(c);
      return { cells, cities: rows.length <= (o.ringMax ?? 30) ? new Set(rows.map((r) => r.key)) : undefined };
    },
    rowAtCell: (cell) => { const c = cellMetro.get(cell); return c ? metroByCity.get(c) : null; },
    focus: (row) => app.selectCity(row.ref, { fly: true }),
    cellsOf: (row) => row.ref.footprint || [row.ref.cell],
  });

  // --- counties ---------------------------------------------------------------------------------------------------
  let counties_ = null;
  if (counties) {
    const cols = counties.columns;
    const cityName = new Map(cities.map((c) => [c.id, c.name]));
    const countyRows = cRows.map(({ r, i }) => {
      const v = {};
      cols.forEach((k, j) => (v[k] = r[j]));
      v.metro = v.aav ? cityName.get(v.aav) || null : null;
      return { key: v.geoid, name: shortCounty(v.name), full: v.name, sub: v.state, level: "counties", ref: i, v };
    });
    // counties.json rows follow world.json counties; map by geoid anyway in case they ever diverge.
    const worldIdx = new Map((w.raw.counties || []).map((c, k) => [c.geoid, k]));
    for (const row of countyRows) row.ref = worldIdx.get(row.key) ?? row.ref;
    const rowByWorld = new Map(countyRows.map((r) => [r.ref, r]));
    // Departments smaller than a hex own no cell: counties.json `cell` (the hex nearest the department's centre) stands in.
    const cellsOfRow = (r) => countyCells.get(r.ref) || (Number.isInteger(r.v.cell) ? [r.v.cell] : []);
    const fields = counties.fields.filter((f) => f.key !== "aav" && f.key !== "geoid" && f.key !== "cell").map((f) => ({
      ...F(f.key, f.key === "name" ? "Department" : f.label, f.format, { unit: f.unit, higher_is: f.higher_is, source: f.source, description: f.description, lens: COUNTY_LENS[f.key], group: groupOf(f.key) }),
    }));
    fields.splice(2, 0, F("metro", "Main urban area", "text", { group: "Name", description: "The largest aire d'attraction des villes touching the department, if it is on the map." }));
    counties_ = makeLevel({
      id: "counties", label: "Departments", noun: "department",
      rows: countyRows, fields,
      highlight: (rows) => {
        const cells = new Set();
        for (const r of rows) for (const c of cellsOfRow(r)) cells.add(c);
        return { cells };
      },
      rowAtCell: (cell) => (countyOf[cell] >= 0 ? rowByWorld.get(countyOf[cell]) || null : null),
      focus: (row) => {
        let cells = cellsOfRow(row);
        // A county smaller than a hex owns no cell: frame its metro instead, or open its state.
        if (!cells.length && row.v.aav) cells = cities.find((c) => c.id === row.v.aav)?.footprint || [];
        if (!cells.length) return app.selectState(row.v.state, { fly: true });
        let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
        for (const c of cells) {
          const x = grid.cx(c), y = grid.cy(c);
          x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
        }
        const R = grid.R * 6;
        frameBox(app, { x0: x0 - R, y0: y0 - R, x1: x1 + R, y1: y1 + R }, { pad: 24, maxScale: 2.4 });
      },
      cellsOf: (row) => cellsOfRow(row),
    });
  }

  const countiesOffMap = counties_ ? counties_.rows.filter((r) => !counties_.cellsOf(r).length).length : 0; // no hex, not even a stand-in
  return {
    app, nation, nat, vintage, countyVintage, countiesOffMap,
    levels: { states: states_, metros, counties: counties_ },
    stateCells, countyCells, cellMetro, metroByCity,
    items, typeById,
    source: (id) => srcTitle.get(id) || null,
  };
}

/** French department names are already compact; keep the hook for table labels. */
export function shortCounty(name) {
  return String(name || "");
}

function groupOf(k) {
  if (["population", "density", "seniors", "immigration", "growth"].includes(k)) return "People";
  if (["income", "poverty", "homeownership", "second_homes", "vacancy", "unemployment"].includes(k)) return "Prosperity";
  if (["higher_education"].includes(k)) return "Knowledge";
  if (["public_transit", "car_commuting"].includes(k)) return "Daily life";
  if (["forest", "crop", "pasture", "developed", "land_km2"].includes(k)) return "Land";
  if (["name", "state", "metro"].includes(k)) return "Name";
  if (["macron_2022", "lepen_2022", "abstention_2022"].includes(k)) return "Elections";
  if (["disasters", "flood_events", "drought_events"].includes(k)) return "Hazards";
  if (["veterans", "veterans_pct", "armed_forces", "armed_forces_pct"].includes(k)) return "Military";
  return "Other";
}

function makeLevel(def) {
  const fieldByKey = new Map(def.fields.map((f) => [f.key, f]));
  const byKey = new Map(def.rows.map((r) => [r.key, r]));
  return {
    ...def,
    byKey,
    field: (k) => fieldByKey.get(k) || null,
    value: (row, k) => row.v[k] ?? null,
    numericFields: () => def.fields.filter((f) => f.format !== "text"),
    /** Add fields after the fact (optional files that load on demand); a key already present is skipped. */
    addFields(list) {
      for (const f of list) {
        if (fieldByKey.has(f.key)) continue;
        def.fields.push(f);
        fieldByKey.set(f.key, f);
      }
    },
  };
}

// --- fields from files that load on demand ------------------------------------------------------------------------
// extendData(data, names) loads the named files (military, districts, citizens) through app.loadData and adds their
// columns to the levels once per data model. Missing files (null) add nothing. Returns the loaded files by name.
const F4 = (key, label, format, o = {}) => ({ key, label, format, unit: o.unit || null, higher_is: o.higher_is || "neutral", source: o.source || "", description: o.description || "", lens: o.lens || null, group: o.group || "Other", derived: !!o.derived });

export async function extendData(data, names) {
  const app = data.app;
  const files = Object.fromEntries(await Promise.all(names.map(async (n) => [n, await app.loadData(n).catch(() => null)])));
  data.extended ??= new Set();
  for (const n of names) {
    if (data.extended.has(n) || !files[n]) continue;
    data.extended.add(n);
    try {
      if (n === "military") extendMilitary(data, files[n]);
      if (n === "districts") extendDistricts(data, files[n]);
      if (n === "citizens") extendCitizens(data, files[n]);
    } catch (err) {
      console.error(`advisors: could not add the ${n} columns`, err);
    }
  }
  return files;
}

function extendMilitary(data, mil) {
  const { states, metros } = data.levels;
  const v = mil.vintage || {};
  const instBy = (k) => {
    const m = new Map();
    for (const it of mil.installations || []) if (it[k]) m.set(it[k], (m.get(it[k]) || 0) + 1);
    return m;
  };
  const byState = instBy("state"), byMetro = instBy("aav");
  states.addFields([
    F4("mil_active", "Stationed military personnel", "int", { unit: "people at base seats", source: "fr_military", group: "Military", description: `Stationed personnel in bases de défense whose support-group seat is in the region (${v.personnel || "2012"}). Includes the one aggregate Île-de-France row there; not troops by home residence or current strength.` }),
    F4("installations", "Defense bases", "int", { unit: "base seats", source: "fr_military", group: "Military", description: `Geocoded bases de défense in the region (${v.installations || "2012"}). Markers are support-group seats, not boundaries or every barracks.` }),
  ]);
  for (const r of states.rows) {
    const s = mil.states?.[r.key];
    Object.assign(r.v, {
      mil_active: s?.personnel?.total ?? null,
      installations: s ? byState.get(r.key) || 0 : null,
    });
  }
  metros.addFields([
    F4("encampment", "Garrison", "text", { source: "fr_military", group: "Military", description: `Fortress or garrison when the AAV passes the stationed-personnel rule; blank otherwise. ${mil.rules?.encampment || mil.rule || ""}` }),
    F4("installations", "Defense bases", "int", { unit: "base seats", source: "fr_military", group: "Military", description: `Geocoded bases de défense whose support-group seat lies in the AAV (${v.installations || "2012"}).` }),
  ]);
  for (const r of metros.rows) {
    const c = mil.cities?.[r.key];
    r.v.encampment = c ? (c.tier === "fortress" ? "Fortress" : "Garrison") : null;
    r.v.installations = byMetro.get(r.key) || 0;
  }
}

function extendDistricts(data, d) {
  const { metros, counties } = data.levels;
  const cat = new Map((d.catalog || []).map((c) => [c.id, c]));
  const vint = d.vintage || "INSEE census";
  const lb = (x) => (x?.lower_bound ? " (at least)" : "");
  metros.addFields([
    F4("city_type", "City type", "text", { source: "fr_insee_stats", group: "Districts", description: `The city's badge: named after its strongest exceptionally concentrated district when one passes the badge override, otherwise its strongest district; a speciality nickname is used when one is at least 3× the national share of jobs (${vint}). Blank: no district passes (a diversified economy).` }),
    F4("districts", "Districts", "text", { source: "fr_insee_stats", group: "Districts", description: `Industry districts the urban area qualifies for, strongest first. ${d.rule?.text || ""}` }),
    F4("n_districts", "Number of districts", "int", { source: "fr_insee_stats", group: "Districts", description: "How many districts pass the rule (up to 5)." }),
    F4("qcew_jobs", "Jobs (INSEE)", "int", { unit: "covered jobs, where the employer is", source: "fr_insee_stats", group: "Districts", description: `Census workplace jobs (${vint}). Counted where the employer is, not where workers live.` }),
    F4("top_industry", "Most specialised industry", "text", { source: "fr_insee_stats", group: "Districts", description: "The detailed industry (of those this project fetches) with the highest location quotient and at least 1,000 jobs." }),
    F4("top_lq", "Its location quotient", "lq", { unit: "× the metropolitan-France share of jobs", source: "fr_insee_stats", group: "Districts", description: "Location quotient of the most specialised industry: its share of the urban area's jobs ÷ its share of metropolitan-France jobs." }),
  ]);
  for (const r of metros.rows) {
    const c = d.cities?.[r.key];
    const top = c?.top?.[0];
    Object.assign(r.v, {
      city_type: c?.badge?.label ?? null,
      districts: c ? (c.districts || []).map((x) => cat.get(x.id)?.name || x.id).join(", ") || null : null,
      n_districts: c ? (c.districts || []).length : null,
      qcew_jobs: c?.emp ?? null,
      top_industry: top ? `${d.industries?.[top.naics]?.title || top.naics}${lb(top)}` : null,
      top_lq: top?.lq ?? null,
    });
  }
  if (counties && d.counties) {
    counties.addFields([
      F4("districts", "Districts", "text", { source: "fr_insee_stats", group: "Districts", description: `Industry districts the department qualifies for, strongest first (${vint}). ${d.rule?.county_note || ""}` }),
      F4("qcew_jobs", "Jobs (INSEE)", "int", { unit: "covered jobs, where the employer is", source: "fr_insee_stats", group: "Districts", description: `Census workplace jobs (${vint}).` }),
    ]);
    for (const r of counties.rows) {
      const c = d.counties[r.key];
      r.v.districts = c ? (c.districts || []).map((x) => cat.get(x[0])?.name || x[0]).join(", ") || null : null;
      r.v.qcew_jobs = c?.emp ?? null;
    }
  }
}

// Citizens: a few telling shares of each INSEE row (the City View draws the whole mix as person icons).
const CZ = [
  ["workforce", "farmer", "Farmers"], ["workforce", "executive", "Artisans & owners"], ["workforce", "scholar", "Managers & professions"],
  ["workforce", "clerk", "Intermediate professions"], ["workforce", "service", "Employees"], ["workforce", "maker", "Workers"],
  ["age", "child", "Children under 15"], ["age", "young", "Residents 15–24"], ["age", "elder", "Elders 65+"],
  ["commute", "drove_alone", "Car to work"], ["commute", "transit", "Public transit"], ["commute", "walk", "Walk to work"], ["commute", "home", "No transport"],
  ["education", "graduate", "Bac+5 or higher"],
  ["nativity", "born_in_state", "Not immigrants"], ["nativity", "foreign_born", "Immigrants"],
];
function extendCitizens(data, cz) {
  const { metros } = data.levels;
  const vint = cz.vintage || "INSEE census";
  const label = new Map(Object.entries(cz.groups || {}).flatMap(([row, list]) => list.map((g) => [`${row}.${g.key}`, g.label])));
  const rowDesc = cz.rows || {};
  const grp = { workforce: "Citizens: work", age: "Citizens: age", commute: "Citizens: commute", education: "Citizens: education", nativity: "Citizens: origin" };
  metros.addFields([
    ...CZ.map(([row, key, lbl]) => F4(`cz_${key}`, lbl, "pct", {
      unit: `share of ${(rowDesc[row] || row).toLowerCase()}`, source: "fr_insee_stats", group: grp[row],
      description: `${label.get(`${row}.${key}`) || lbl}: share of ${(rowDesc[row] || row).toLowerCase()} (${vint}). Blank where INSEE left the area out of that table.${row === "commute" ? " Shares of workers, not of all residents." : ""}`,
    })),
    F4("cz_median_age", "Median age", "years", { unit: "years", source: "fr_insee_stats", group: grp.age, description: `Median age of residents (${vint}), when published in the citizen contract.` }),
    F4("cz_degree", "Bac+3 or higher", "pct", { unit: "of non-enrolled residents 15+", source: "fr_insee_stats", group: grp.education, description: `Non-enrolled residents aged 15+ whose highest diploma is bac+3 or above (${vint}).` }),
    F4("cz_specialist", "Most over-represented citizen", "text", { source: "fr_insee_stats", group: "Citizens", description: `The category most over-represented against the national share (at least 1.5×). ${cz.rule?.text || ""}` }),
  ]);
  for (const r of metros.rows) {
    const c = cz.cities?.[r.key];
    for (const [row, key] of CZ) r.v[`cz_${key}`] = c?.[row]?.shares?.[key] ?? null;
    r.v.cz_median_age = c?.age?.median ?? null;
    r.v.cz_degree = c?.education?.bachelors_plus ?? null;
    const sp = (c?.specialists || []).find((s) => s.ratio >= 1);
    r.v.cz_specialist = sp ? `${label.get(`${sp.row}.${sp.key}`) || sp.key} ×${sp.ratio.toFixed(1)}${c.reliable === false ? " (micro: rough)" : ""}` : null;
  }
}

/** The highlight for a set of rows of one level, with defaults (gold outline, other land dimmed when asked). */
export function rowsHighlight(level, rows, opts = {}) {
  if (!level || !rows || !rows.length) return null;
  const one = rows.length === 1 ? rows[0] : null;
  const label = opts.label ?? (one ? (one.level === "states" ? one.name : `${one.full || one.name}${one.sub ? `, ${one.sub}` : ""}`) : "");
  return { ...level.highlight(rows, opts), dimOthers: !!opts.dim, color: opts.color, label };
}
