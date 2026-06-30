// NSW Site Controls — browser port of the Python `controls` CLI.
// All network access is to public NSW gov ArcGIS REST services + OSM Nominatim,
// which all send permissive CORS headers, so this runs fully client-side.

// ----------------------------------------------------------------------------
// registry.py
// ----------------------------------------------------------------------------
const PLANNING_SERVICE =
  "https://mapprod1.environment.nsw.gov.au/arcgis/rest/services/" +
  "Planning/EPI_Primary_Planning_Layers/MapServer";
const CADASTRE_SERVICE =
  "https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Cadastre/MapServer";
const CADASTRE_LOT_LAYER = 9;

// One row per LEP/SEPP control. Order = display order.
const LAYER_REGISTRY = [
  { key: "zoning", name: "Land zoning", layer_id: 2, value_field: "SYM_CODE", label_field: "LAY_CLASS", epi_field: "EPI_NAME", kind: "scalar" },
  { key: "fsr", name: "Floor space ratio (FSR)", layer_id: 1, value_field: "FSR", label_field: "SYM_CODE", epi_field: "EPI_NAME", kind: "scalar" },
  { key: "height", name: "Max building height", layer_id: 5, value_field: "MAX_B_H", label_field: "SYM_CODE", unit_field: "UNITS", epi_field: "EPI_NAME", kind: "scalar" },
  { key: "min_lot", name: "Minimum lot size", layer_id: 4, value_field: "LOT_SIZE", label_field: "SYM_CODE", unit_field: "UNITS", epi_field: "EPI_NAME", kind: "scalar" },
  { key: "heritage", name: "Heritage", layer_id: 0, value_field: "H_NAME", label_field: "SIG", epi_field: "EPI_NAME", kind: "heritage" },
];

// ----------------------------------------------------------------------------
// arcgis.py
// ----------------------------------------------------------------------------
class ArcGISError extends Error {}

const DEFAULT_TIMEOUT = 40000;
const DEFAULT_RETRIES = 2;
const BACKOFF = [600, 1500];

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

async function httpGetJson(url, { timeout = DEFAULT_TIMEOUT, retries = DEFAULT_RETRIES } = {}) {
  let lastErr = null;
  for (let attempt = 0; attempt <= retries; attempt++) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeout);
    try {
      const resp = await fetch(url, { signal: ctrl.signal, headers: { Accept: "application/json" } });
      clearTimeout(t);
      const raw = await resp.text();
      let data;
      try { data = JSON.parse(raw); }
      catch { throw new ArcGISError(`non-JSON response from ${url}: ${raw.slice(0, 200)}`); }
      if (data && typeof data === "object" && data.error) {
        throw new ArcGISError(`ArcGIS error from ${url}: ${JSON.stringify(data.error)}`);
      }
      return data;
    } catch (exc) {
      clearTimeout(t);
      if (exc instanceof ArcGISError) throw exc; // not retried — would just repeat
      lastErr = exc;
      if (attempt < retries) await sleep(BACKOFF[Math.min(attempt, BACKOFF.length - 1)]);
    }
  }
  throw new ArcGISError(`GET failed after ${retries + 1} tries: ${url}: ${lastErr}`);
}

function pointGeometry(lon, lat) {
  return { x: lon, y: lat, spatialReference: { wkid: 4326 } };
}

async function arcQuery(serviceUrl, layerId, {
  geometry, geometryType = "esriGeometryPoint", inSr = 4326, outFields = "*",
  spatialRel = "esriSpatialRelIntersects", returnGeometry = false, outSr = null, where = "1=1",
} = {}) {
  const base = serviceUrl.replace(/\/+$/, "") + `/${layerId}/query`;
  const params = new URLSearchParams({
    f: "json", where, geometry: JSON.stringify(geometry), geometryType,
    inSR: String(inSr), spatialRel, outFields, returnGeometry: returnGeometry ? "true" : "false",
  });
  if (outSr !== null) params.set("outSR", String(outSr));
  const data = await httpGetJson(base + "?" + params.toString());
  return data.features || [];
}

async function arcQueryWhere(serviceUrl, layerId, {
  where, outFields = "*", returnGeometry = true, outSr = 4326,
} = {}) {
  const base = serviceUrl.replace(/\/+$/, "") + `/${layerId}/query`;
  const params = new URLSearchParams({
    f: "json", where, outFields, returnGeometry: returnGeometry ? "true" : "false",
  });
  if (outSr !== null) params.set("outSR", String(outSr));
  const data = await httpGetJson(base + "?" + params.toString());
  return data.features || [];
}

// ----------------------------------------------------------------------------
// locate.py
// ----------------------------------------------------------------------------
function convertArea(value, units) {
  if (value === null || value === undefined || value === "" || value === 0) return null;
  const v = Number(value);
  if (!isFinite(v)) return null;
  const u = (units || "").trim().toLowerCase();
  if (u.startsWith("ha") || u === "h") return v * 10000.0;
  return v;
}

function polygonAreaM2(rings) {
  if (!rings || !rings.length) return null;
  let total = 0.0;
  for (const ring of rings) {
    let pts = ring;
    if (ring.length > 1 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1]) {
      pts = ring.slice(0, -1);
    }
    if (pts.length < 3) continue;
    const lat0 = pts.reduce((s, p) => s + p[1], 0) / pts.length;
    const mx = 111320.0 * Math.cos((lat0 * Math.PI) / 180);
    const my = 110540.0;
    const xy = pts.map((p) => [p[0] * mx, p[1] * my]);
    let s = 0.0;
    for (let i = 0; i < xy.length; i++) {
      const [x1, y1] = xy[i];
      const [x2, y2] = xy[(i + 1) % xy.length];
      s += x1 * y2 - x2 * y1;
    }
    total += s / 2.0;
  }
  const area = Math.abs(total);
  return area > 0 ? area : null;
}

function ringCentroid(rings) {
  if (!rings || !rings.length) return null;
  const ring = rings[0];
  let pts = ring;
  if (ring.length > 1 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1]) {
    pts = ring.slice(0, -1);
  }
  if (!pts.length) return null;
  const x = pts.reduce((s, p) => s + p[0], 0) / pts.length;
  const y = pts.reduce((s, p) => s + p[1], 0) / pts.length;
  return [x, y];
}

function parcelFromFeature(feat) {
  const attrs = feat.attributes || {};
  const geom = feat.geometry;
  let parcel = null;
  if (geom && geom.rings) parcel = { rings: geom.rings, spatialReference: { wkid: 4326 } };
  const lotid = attrs.lotidstring ?? null;
  let area = convertArea(attrs.planlotarea, attrs.planlotareaunits);
  let areaSource = area !== null ? "planlotarea" : null;
  if (area === null && parcel) {
    area = polygonAreaM2(parcel.rings);
    areaSource = area !== null ? "geometry" : null;
  }
  return { parcel, lotid, area, areaSource };
}

function newSite(o) {
  return Object.assign({ lon: null, lat: null, lotidstring: null, area_m2: null, area_source: null, parcel: null, source: "", warnings: [] }, o);
}

async function fromCoords(lon, lat) {
  const site = newSite({ lon, lat, source: "coords" });
  let feats;
  try {
    feats = await arcQuery(CADASTRE_SERVICE, CADASTRE_LOT_LAYER, {
      geometry: pointGeometry(lon, lat), geometryType: "esriGeometryPoint", inSr: 4326,
      returnGeometry: true, outSr: 4326,
    });
  } catch (exc) {
    site.warnings.push(`cadastre lookup failed: ${exc.message}`);
    return site;
  }
  if (!feats.length) {
    site.warnings.push("no cadastral parcel found at this point; site area unknown");
    return site;
  }
  if (feats.length > 1) site.warnings.push(`${feats.length} parcels at this point (strata?); using the first`);
  const { parcel, lotid, area, areaSource } = parcelFromFeature(feats[0]);
  site.parcel = parcel; site.lotidstring = lotid; site.area_m2 = area; site.area_source = areaSource;
  return site;
}

function parseLot(ref) {
  const s = ref.trim().toUpperCase().replace(/\\/g, "/");
  let m = s.match(/^\s*([0-9A-Z]+)\s*\/{1,2}\s*(?:[0-9A-Z]*\s*\/\s*)?((?:DP|SP)?\s*\d+)\s*$/);
  if (!m) m = s.match(/^\s*(?:LOT\s*)?([0-9A-Z]+)\s+(?:SEC\s*\S+\s+)?((?:DP|SP)?\s*\d+)\s*$/);
  if (!m) throw new Error(`could not parse lot reference '${ref}' (try '5/DP12345')`);
  const lot = m[1];
  let plan = m[2].replace(/\s+/g, "");
  if (!(plan.startsWith("DP") || plan.startsWith("SP"))) plan = "DP" + plan;
  return [lot, plan];
}

async function fromLot(ref) {
  const [lot, plan] = parseLot(ref);
  const where = `lotnumber='${lot}' AND planlabel='${plan}'`;
  const feats = await arcQueryWhere(CADASTRE_SERVICE, CADASTRE_LOT_LAYER, { where, returnGeometry: true, outSr: 4326 });
  if (!feats.length) throw new Error(`no parcel found for lot ${lot}/${plan}`);
  const { parcel, lotid, area, areaSource } = parcelFromFeature(feats[0]);
  const centroid = parcel ? ringCentroid(parcel.rings) : null;
  if (centroid === null) throw new Error(`parcel ${lot}/${plan} has no usable geometry`);
  const site = newSite({
    lon: centroid[0], lat: centroid[1], lotidstring: lotid || `${lot}/${plan}`,
    area_m2: area, area_source: areaSource, parcel, source: "lot/DP",
  });
  if (feats.length > 1) site.warnings.push(`${feats.length} parcels matched ${lot}/${plan}; using the first`);
  return site;
}

async function geocodeAddress(address) {
  const params = new URLSearchParams({ q: address, format: "json", countrycodes: "au", limit: "1" });
  const url = "https://nominatim.openstreetmap.org/search?" + params.toString();
  let data;
  try {
    const resp = await fetch(url, { headers: { Accept: "application/json" } });
    data = await resp.json();
  } catch (exc) {
    throw new Error(`geocoding failed for '${address}': ${exc}`);
  }
  if (!data || !data.length) throw new Error(`no geocoding match for '${address}'`);
  return [parseFloat(data[0].lon), parseFloat(data[0].lat)];
}

async function fromAddress(address) {
  const [lon, lat] = await geocodeAddress(address);
  const site = await fromCoords(lon, lat);
  site.source = `address (geocoded): ${address}`;
  site.warnings.unshift("address was geocoded approximately — verify the point/lot in SixMaps");
  return site;
}

// ----------------------------------------------------------------------------
// lep.py
// ----------------------------------------------------------------------------
function distinct(values) {
  const seen = new Set(); const out = [];
  for (const v of values) {
    const key = `${v.value} ${v.epi}`;
    if (!seen.has(key)) { seen.add(key); out.push(v); }
  }
  return out;
}

function parseFeatures(spec, feats) {
  const values = [];
  for (const feat of feats) {
    const attrs = feat.attributes || {};
    const raw = attrs[spec.value_field];
    if (raw === null || raw === undefined || raw === "" || raw === " ") continue;
    values.push({
      value: raw,
      label: spec.label_field ? attrs[spec.label_field] ?? null : null,
      epi: attrs[spec.epi_field] ?? null,
      unit: spec.unit_field ? attrs[spec.unit_field] ?? null : null,
    });
  }
  return { spec, values: distinct(values), error: null };
}

async function buildEnvelope(site) {
  let geom, gtype;
  if (site.parcel) { geom = site.parcel; gtype = "esriGeometryPolygon"; }
  else { geom = pointGeometry(site.lon, site.lat); gtype = "esriGeometryPoint"; }

  const results = {};
  // Fire all layer queries in parallel; one failing must not sink the rest.
  await Promise.all(LAYER_REGISTRY.map(async (spec) => {
    try {
      const feats = await arcQuery(PLANNING_SERVICE, spec.layer_id, { geometry: geom, geometryType: gtype });
      results[spec.key] = parseFeatures(spec, feats);
    } catch (exc) {
      results[spec.key] = { spec, values: [], error: exc.message };
    }
  }));

  const env = { results, max_gfa_m2: [], subdivision: null, notes: [] };
  deriveEnvelope(site, env);
  return env;
}

function deriveEnvelope(site, env) {
  const fsr = env.results.fsr;
  if (fsr && fsr.values.length && site.area_m2) {
    for (const cv of fsr.values) {
      const f = Number(cv.value);
      if (isFinite(f)) env.max_gfa_m2.push(Math.round(f * site.area_m2));
    }
  } else if (fsr && fsr.values.length && !site.area_m2) {
    env.notes.push("max GFA not computed — site area unknown (give a lot/DP or coords on a parcel)");
  }

  const minLot = env.results.min_lot;
  if (minLot && minLot.values.length && site.area_m2) {
    const sizes = minLot.values.map((v) => Number(v.value)).filter((x) => isFinite(x));
    if (sizes.length) {
      const smallest = Math.min(...sizes);
      if (smallest > 0) {
        const n = Math.floor(site.area_m2 / smallest);
        env.subdivision = n >= 1
          ? `${site.area_m2.toFixed(0)} m² / ${smallest.toFixed(0)} m² min lot = up to ${n} lot(s) on min-lot-size alone`
          : `site (${site.area_m2.toFixed(0)} m²) is below the ${smallest.toFixed(0)} m² minimum lot size`;
      }
    }
  }
}

// ----------------------------------------------------------------------------
// dcp.py + ryde_dcp_2014.yaml (inlined)
// ----------------------------------------------------------------------------
const DCP_ALIASES = {
  "dwelling": "dwelling-house", "dwelling house": "dwelling-house", "dwelling_house": "dwelling-house",
  "dwelling-house": "dwelling-house", "house": "dwelling-house",
  "dual": "dual-occupancy", "dual occ": "dual-occupancy", "dual occupancy": "dual-occupancy",
  "dual_occupancy": "dual-occupancy", "dual-occupancy": "dual-occupancy", "duplex": "dual-occupancy",
};

// --- Council DCP registry (the multi-council skeleton) ----------------------
// To add a council: add ONE entry below keyed by a lowercase slug, in the same
// shape as `ryde` (name, instrument, source_part, source_url, retrieved,
// dev_types). It then appears automatically in the Council dropdown, and its
// dev_types drive the Development-type dropdown — no other code changes needed.
// This mirrors the Python tool's per-council curated-data design: adding a
// council is adding data, not writing code. Keep each council's numbers
// transcribed + clause-cited, exactly like Ryde.
const DEFAULT_COUNCIL = "ryde";

const COUNCILS = {
  ryde: {
  name: "City of Ryde",
  instrument: "Development Control Plan 2014",
  source_part: "Part 3.3 — Dwelling Houses and Dual Occupancy",
  source_url: "https://www.ryde.nsw.gov.au/Planning-and-Development/Planning-Controls/Development-Control-Plan",
  retrieved: "2026-06-29",
  dev_types: {
    "dwelling-house": {
      label: "Dwelling house",
      controls: [
        { control: "Front setback", value: "6 m from the primary street boundary. Corner lots: min 2 m to the secondary street. Garages set back ≥1 m behind the front façade.", clause: "2.9.1 (a),(b),(c)" },
        { control: "Side setback", value: "Single storey: 0.9 m. Two storey: 1.5 m. Lots wider than long: one side ≥ 20% of the width or 8 m, whichever is greater.", clause: "2.9.2 (a),(b),(d)" },
        { control: "Rear setback", value: "25% of the site length or 8 m, whichever is greater. Battle-axe lots: 8 m. Constrained lots: min 4 m. Must fit the 8 m × 8 m deep-soil area.", clause: "2.9.3 (a),(b),(c)" },
        { control: "Max building height", value: "9.5 m overall; max wall-plate 7.5 m (8 m for a pitched roof); maximum 2 storeys.", clause: "2.8.1" },
        { control: "Ceiling height", value: "Habitable rooms min 2.4 m.", clause: "2.8.2" },
        { control: "Deep soil", value: "≥ 35% of the allotment, including an 8 m × 8 m area in the rear yard; 100% permeable, no structures.", clause: "2.6.1 (2)" },
        { control: "Landscaping (front garden)", value: "Hard-paved area ≤ 40% of the front garden; provide ≥ 1 tree capable of 10 m mature height.", clause: "2.13" },
        { control: "Site coverage", value: "No fixed % in Part 3.3 — governed by FSR (from the LEP) + the 35% deep-soil control.", clause: "(see FSR in LEP + 2.6.1)" },
        { control: "Car parking", value: "Up to 2 spaces per dwelling (Part 9.3). 36 m² (2 cars) / 18 m² (1 car) may be excluded from GFA.", clause: "2.11.1 (a) / Part 9.3" },
        { control: "Excavation / cut", value: "Excavation depth limited to 1.2 m max under the deep-soil provisions; cut/fill to keep within height & storey limits.", clause: "2.6.1 (e)" },
        { control: "Front fence", value: "Max 1.8 m if ≥ 50% open above a solid base (base ≤ 900 mm); solid masonry up to 1.8 m only on arterial roads.", clause: "2.x Fences" },
      ],
    },
    "dual-occupancy": {
      label: "Dual occupancy (attached)",
      controls: [
        { control: "Minimum lot", value: "≥ 580 m², road frontage ≥ 10 m, width ≥ 15 m at 7.5 m from the frontage. Battle-axe: ≥ 740 m² (excl. access corridor), frontage ≥ 3 m, corridor ≥ 3 m wide.", clause: "Part 3.3 General / Ryde LEP 2014 cl 4.1B" },
        { control: "Max height / storeys", value: "Max 2 storeys. A duplex is a single building, ≤ 2 storeys, containing 2 dwellings (9.5 m height as per dwelling house).", clause: "2.8.1" },
        { control: "Setbacks", value: "As per dwelling-house controls (front 6 m, side 0.9/1.5 m, rear 25%-or-8 m). The primary street frontage takes the larger setback.", clause: "2.9" },
        { control: "Deep soil", value: "≥ 35% deep soil; the allotment needs only ONE 8 m × 8 m deep-soil area (not one per dwelling).", clause: "2.6.1 (2)(c)" },
        { control: "Car parking", value: "1 space per dwelling (Part 9.3).", clause: "2.11.1 / Part 9.3" },
      ],
    },
  },
  }, // end ryde

  // --- Skeleton for the NEXT council (uncomment + fill, no other changes) -----
  // Copy this block, key it by the council slug, transcribe the DCP numbers with
  // their clause cites, and it appears in the Council dropdown automatically.
  // willoughby: {
  //   name: "Willoughby City Council",
  //   instrument: "Willoughby DCP 2022",
  //   source_part: "Part ...",
  //   source_url: "https://www.willoughby.nsw.gov.au/...",
  //   retrieved: "YYYY-MM-DD",
  //   dev_types: {
  //     "dwelling-house": {
  //       label: "Dwelling house",
  //       controls: [
  //         { control: "Front setback", value: "...", clause: "..." },
  //       ],
  //     },
  //   },
  // },
};

function availableCouncils() {
  return Object.entries(COUNCILS).map(([slug, c]) => ({ slug, name: c.name }));
}

function availableDevTypes(councilSlug) {
  const c = COUNCILS[councilSlug];
  if (!c) return [];
  return Object.entries(c.dev_types).map(([key, b]) => ({ key, label: b.label }));
}

function controlsFor(devType, councilSlug = DEFAULT_COUNCIL) {
  const c = COUNCILS[councilSlug];
  if (!c) throw new Error(`no curated DCP for council '${councilSlug}'`);
  const devs = c.dev_types;
  // Accept aliases ("duplex" -> "dual-occupancy"), or a raw canonical key.
  const canonical = DCP_ALIASES[(devType || "").trim().toLowerCase()] || (devType in devs ? devType : null);
  if (!canonical || !(canonical in devs)) {
    throw new Error(`dev-type '${devType}' not in ${c.name} DCP. Available: ${Object.keys(devs).join(", ")}`);
  }
  const block = devs[canonical];
  return {
    council: c.name, instrument: c.instrument, source_part: c.source_part,
    dev_type: canonical, dev_label: block.label, retrieved: c.retrieved,
    controls: block.controls.map((x) => ({ control: x.control, value: x.value, clause: x.clause || "" })),
  };
}

// ----------------------------------------------------------------------------
// sheet.py (rendered as HTML)
// ----------------------------------------------------------------------------
const DISCLAIMER =
  "Decision-support only. Generated from public NSW spatial data and a curated " +
  "transcription of the council DCP. It is NOT planning advice or a certificate. " +
  "Verify against the source instruments / a planner / a s10.7 certificate before lodging a DA.";

const REFORM_WARNING =
  "This is a residential zone — the NSW Low & Mid-Rise Housing reforms (2024–2025) " +
  "may permit additional dwelling types, height and FSR here that the base LEP layer " +
  "does NOT show. Check the Housing SEPP / reform mapping before assuming these limits.";

function isResidential(env) {
  const z = env.results.zoning;
  if (!z || !z.values.length) return false;
  for (const v of z.values) {
    const code = String(v.value || "").toUpperCase();
    const lab = String(v.label || "").toLowerCase();
    if (code.startsWith("R") || lab.includes("residential")) return true;
  }
  return false;
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function fmtValue(cv) {
  let s = String(cv.value);
  if (cv.unit) s += " " + cv.unit;
  if (cv.label && String(cv.label) !== String(cv.value)) s += `  (${cv.label})`;
  return s;
}

function renderSheet(site, env, dcp) {
  const L = [];
  // head
  const lotLine = site.lotidstring ? `Lot/DP ${esc(site.lotidstring)}` : "";
  let areaLine = "";
  if (site.area_m2) {
    const src = { planlotarea: "cadastre planlotarea", geometry: "from parcel geometry" }[site.area_source] || "cadastre";
    areaLine = `${site.area_m2.toFixed(0)} m² (${src})`;
  }
  L.push(`<div class="sheet-head">
    <h2>NSW Site Control Sheet</h2>
    <div class="meta">${site.lon.toFixed(6)}, ${site.lat.toFixed(6)} · ${esc(site.source)}</div>
  </div>`);
  L.push(`<table>`);
  if (lotLine) L.push(`<tr><td class="k">Lot / DP</td><td class="v">${esc(site.lotidstring)}</td></tr>`);
  if (areaLine) L.push(`<tr><td class="k">Site area</td><td class="v">${areaLine}</td></tr>`);
  L.push(`</table>`);

  // envelope
  L.push(`<div class="sec-title">LEP / SEPP envelope</div>`);
  L.push(`<table>`);
  for (const key of Object.keys(env.results)) {
    const res = env.results[key];
    const name = res.spec.name;
    if (res.error) {
      L.push(`<tr><td class="k">${esc(name)}</td><td class="v">(unavailable — ${esc(res.error.split("\n")[0].slice(0, 80))})</td></tr>`);
      continue;
    }
    if (!res.values.length) {
      L.push(`<tr><td class="k">${esc(name)}</td><td class="v">none mapped</td></tr>`);
      continue;
    }
    if (res.spec.kind === "heritage") {
      for (const cv of res.values) {
        L.push(`<tr><td class="k">${esc(name)}</td><td class="v">${esc(cv.value)} <span class="src">[${esc(cv.label)}] (${esc(cv.epi)})</span></td></tr>`);
      }
      continue;
    }
    let cell = "";
    res.values.forEach((cv, i) => {
      const src = cv.epi ? `<span class="src">— ${esc(cv.epi)}</span>` : "";
      cell += `<div>${esc(fmtValue(cv))} ${src}</div>`;
    });
    if (res.values.length > 1) cell += `<div class="split">^ site straddles ${res.values.length} ${name.toLowerCase()} areas</div>`;
    L.push(`<tr><td class="k">${esc(name)}</td><td class="v">${cell}</td></tr>`);
  }
  if (env.max_gfa_m2.length) {
    const gfa = env.max_gfa_m2.map((g) => g.toLocaleString() + " m²").join(" or ");
    L.push(`<tr class="derived"><td class="k">Max GFA (derived)</td><td class="v">≈ ${gfa}  <span class="src">FSR × site area</span></td></tr>`);
  }
  if (env.subdivision) L.push(`<tr class="derived"><td class="k">Subdivision</td><td class="v">${esc(env.subdivision)}</td></tr>`);
  L.push(`</table>`);
  for (const n of env.notes) L.push(`<div class="src" style="margin-top:8px">• ${esc(n)}</div>`);

  // dcp
  if (dcp) {
    L.push(`<div class="sec-title">${esc(dcp.council)} DCP — ${esc(dcp.dev_label)}</div>`);
    L.push(`<div class="meta">${esc(dcp.instrument)}, ${esc(dcp.source_part)}; retrieved ${esc(dcp.retrieved)}</div>`);
    L.push(`<table>`);
    for (const c of dcp.controls) {
      L.push(`<tr><td class="k">${esc(c.control)}</td><td class="v">${esc(c.value)}<span class="clause"><br>└ clause ${esc(c.clause)}</span></td></tr>`);
    }
    L.push(`</table>`);
  }

  // warnings
  const warnings = [...site.warnings];
  if (isResidential(env)) warnings.push(REFORM_WARNING);
  for (const w of warnings) L.push(`<div class="warn">⚠ ${esc(w)}</div>`);

  L.push(`<div class="disclaimer">${esc(DISCLAIMER)}</div>`);
  return L.join("\n");
}

// ----------------------------------------------------------------------------
// Map previews — NSW aerial (Leaflet + SIX imagery tiles, parcel overlaid) +
// Google satellite (keyless embed). Both centre on the resolved site.
// ----------------------------------------------------------------------------
const NSW_IMAGERY_TILES =
  "https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Imagery/MapServer/tile/{z}/{y}/{x}";
let _sixMap = null;
let _parcelLayer = null;
let _markerLayer = null;

function renderMaps(site) {
  const card = document.getElementById("maps");
  card.style.display = "block";
  const { lat, lon, parcel } = site;

  // Google satellite iframe
  const gmap = document.getElementById("gmap");
  gmap.src = `https://maps.google.com/maps?q=${lat},${lon}&z=18&t=k&output=embed`;
  document.getElementById("g-link").href = `https://www.google.com/maps/@${lat},${lon},19z/data=!3m1!1e3`;
  document.getElementById("six-link").href = "https://maps.six.nsw.gov.au/";

  // Google Street View iframe (keyless svembed)
  const sv = document.getElementById("svmap");
  sv.src = `https://maps.google.com/maps?q=&layer=c&cbll=${lat},${lon}&cbp=11,0,0,0,0&output=svembed`;
  document.getElementById("sv-link").href = `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${lat},${lon}`;

  // Leaflet NSW imagery map (init once, reuse after)
  if (!_sixMap) {
    _sixMap = L.map("sixmap", { attributionControl: true, zoomControl: true });
    L.tileLayer(NSW_IMAGERY_TILES, {
      maxZoom: 21, maxNativeZoom: 20,
      attribution: "Imagery © Spatial Services NSW",
    }).addTo(_sixMap);
  }
  if (_parcelLayer) { _sixMap.removeLayer(_parcelLayer); _parcelLayer = null; }
  if (_markerLayer) { _sixMap.removeLayer(_markerLayer); _markerLayer = null; }

  // Container was display:none until now — Leaflet needs a size recalculation.
  setTimeout(() => {
    _sixMap.invalidateSize();
    if (parcel && parcel.rings && parcel.rings.length) {
      // rings are [lon,lat]; Leaflet wants [lat,lon]. Array-of-rings handles holes.
      const latlngs = parcel.rings.map((ring) => ring.map((p) => [p[1], p[0]]));
      _parcelLayer = L.polygon(latlngs, { color: "#4ea1ff", weight: 2, fillOpacity: 0.12 }).addTo(_sixMap);
      _sixMap.fitBounds(_parcelLayer.getBounds(), { padding: [24, 24], maxZoom: 20 });
    } else {
      _markerLayer = L.marker([lat, lon]).addTo(_sixMap);
      _sixMap.setView([lat, lon], 18);
    }
  }, 60);
}

// ----------------------------------------------------------------------------
// UI wiring
// ----------------------------------------------------------------------------
const $ = (id) => document.getElementById(id);
let mode = "lot";

$("modeSeg").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-mode]");
  if (!btn) return;
  mode = btn.dataset.mode;
  [...$("modeSeg").children].forEach((b) => b.classList.toggle("active", b === btn));
  $("in-lot").style.display = mode === "lot" ? "" : "none";
  $("in-coords").style.display = mode === "coords" ? "" : "none";
  $("in-address").style.display = mode === "address" ? "" : "none";
});

async function resolveSite() {
  if (mode === "lot") {
    const v = $("lot").value.trim();
    if (!v) throw new Error("enter a lot/DP reference, e.g. 3/DP24994");
    return fromLot(v);
  }
  if (mode === "coords") {
    const lon = parseFloat($("lon").value);
    const lat = parseFloat($("lat").value);
    if (!isFinite(lon) || !isFinite(lat)) throw new Error("enter valid longitude and latitude");
    return fromCoords(lon, lat);
  }
  const a = $("address").value.trim();
  if (!a) throw new Error("enter a street address");
  return fromAddress(a);
}

async function run() {
  const sheet = $("sheet");
  const status = $("status");
  $("go").disabled = true;
  status.textContent = "Querying NSW planning data…";
  sheet.style.display = "none";
  try {
    const site = await resolveSite();
    status.textContent = "Reading planning layers…";
    const env = await buildEnvelope(site);
    let dcp = null;
    const dt = $("devType").value;
    if (dt) {
      try { dcp = controlsFor(dt, $("council").value); } catch (e) { /* dev-type not in DCP — skip section */ }
    }
    sheet.innerHTML = renderSheet(site, env, dcp);
    sheet.style.display = "block";
    renderMaps(site);
    status.textContent = "";
  } catch (exc) {
    sheet.innerHTML = `<div class="err">Error: ${esc(exc.message || exc)}</div>`;
    sheet.style.display = "block";
    document.getElementById("maps").style.display = "none";
    status.textContent = "";
  } finally {
    $("go").disabled = false;
  }
}

// Council + dev-type dropdowns are driven by the COUNCILS registry, so adding a
// council in the data above makes it appear here with no UI code change.
function populateDevTypes() {
  const dSel = $("devType");
  const opts = ['<option value="">— none (envelope only) —</option>'];
  for (const d of availableDevTypes($("council").value)) {
    opts.push(`<option value="${esc(d.key)}">${esc(d.label)}</option>`);
  }
  dSel.innerHTML = opts.join("");
}

function initCouncilUi() {
  const cSel = $("council");
  cSel.innerHTML = availableCouncils()
    .map((c) => `<option value="${esc(c.slug)}">${esc(c.name)}</option>`)
    .join("");
  cSel.value = DEFAULT_COUNCIL;
  cSel.addEventListener("change", populateDevTypes);
  populateDevTypes();
}

initCouncilUi();

$("go").addEventListener("click", run);
document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.target.tagName === "INPUT")) run();
});
