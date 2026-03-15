/* ═══════════════════════════════════════════════════════════════════════════════
 * shared.js — Shared utilities, state, and data loading for the comparison page
 * ═══════════════════════════════════════════════════════════════════════════════ */

/* ── Global App State ──────────────────────────────────────────────────────── */
const app = {
  // Data state
  evalData: null,           // Schema 4A: evaluation_run.json
  sweepData: null,          // Schema 4D: sweep JSON
  walkForwardData: null,    // Schema 4E: walk-forward JSON
  candlesByDay: {},         // keyed by day key → { 1m: [...], 5m: [...], 15m: [...] }
  sessionBoundaries: null,  // session_boundaries.json

  // Variant state
  availableVariants: [],    // e.g. ['a8ra_v1', 'luxalgo_v1'] — extracted from fixture data
  variantByConfig: {},      // config name → variant name (e.g. 'locked_a8ra_v1' → 'a8ra_v1')
  hasVariantData: false,    // true when fixture includes variant fields
  activeVariantFixture: null, // name of the active fixture file ('default' or 'variant')

  // UI state
  activeTab: 'chart',
  tf: '5m',
  day: '2024-01-09',
  selectedConfigs: [],      // config names currently selected for display
  selectedPrimitive: 'displacement',

  // Toggle state (set by chart-tab.js controls)
  configToggles: {},        // keyed by config name → boolean (visible)
  primitiveToggles: {},     // keyed by primitive name → boolean (visible)

  // Chart refs (set by chart-tab.js)
  chart: null,
  candleSeries: null,

  // Detection week mode state (compare.html week browsing)
  weekMode: false,          // true when viewing a walk-forward week
  weekData: null,           // { candleData, detectionData, sessionData }
  weekManifest: [],         // weeks.json content
  currentCompareWeek: null, // current week manifest entry
};

/* ── Constants ─────────────────────────────────────────────────────────────── */

/* Day keys / labels — derived dynamically from fixture data via deriveDaysFromData() */
let DAY_KEYS = [];
let DAY_LABELS = [];
let DAYS = [];

/**
 * Derive DAY_KEYS, DAY_LABELS, and DAYS from loaded evaluation data.
 * Scans all detections across configs/primitives/tfs for unique forex_day values,
 * filters to weekdays (Mon–Fri), sorts chronologically, and formats labels.
 * Also sets app.day to the second day key (matching the original default index)
 * or the first if only one day exists.
 */
function deriveDaysFromData(evalData) {
  if (!evalData || !evalData.per_config) return;

  const SHORT_DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const SHORT_MONTHS = ['Jan','Feb','Mar','Apr','May','Jun',
                        'Jul','Aug','Sep','Oct','Nov','Dec'];

  // Collect unique forex_day values from all detections
  const fdSet = new Set();
  for (const cfgData of Object.values(evalData.per_config)) {
    const pp = cfgData.per_primitive;
    if (!pp) continue;
    for (const primData of Object.values(pp)) {
      const ptf = primData.per_tf;
      if (!ptf) continue;
      for (const tfData of Object.values(ptf)) {
        const dets = tfData.detections;
        if (!dets) continue;
        for (const det of dets) {
          const fd = (det.tags && det.tags.forex_day) ||
                     (det.properties && det.properties.forex_day);
          if (fd) fdSet.add(fd);
        }
      }
    }
  }

  // Sort chronologically
  let days = Array.from(fdSet).sort();

  // Filter to weekdays (Mon=1 .. Fri=5). Parse "YYYY-MM-DD" treating as UTC.
  days = days.filter(d => {
    const dt = new Date(d + 'T00:00:00Z');
    const dow = dt.getUTCDay(); // 0=Sun, 6=Sat
    return dow >= 1 && dow <= 5;
  });

  if (days.length === 0) {
    // Fallback: generate weekdays from dataset.range
    const range = (evalData.dataset && evalData.dataset.range) || [];
    if (range.length === 2) {
      const start = new Date(range[0] + 'T00:00:00Z');
      const end = new Date(range[1] + 'T00:00:00Z');
      for (let dt = new Date(start); dt <= end; dt.setUTCDate(dt.getUTCDate() + 1)) {
        const dow = dt.getUTCDay();
        if (dow >= 1 && dow <= 5) {
          days.push(dt.toISOString().slice(0, 10));
        }
      }
    }
  }

  // Build DAY_KEYS, DAY_LABELS, DAYS
  DAY_KEYS = days;
  DAY_LABELS = days.map(d => {
    const dt = new Date(d + 'T00:00:00Z');
    const dow = SHORT_DAYS[dt.getUTCDay()];
    const mon = SHORT_MONTHS[dt.getUTCMonth()];
    const day = dt.getUTCDate();
    return `${dow} ${mon} ${day}`;
  });
  DAYS = DAY_KEYS.map((k, i) => ({ key: k, label: DAY_LABELS[i] }));

  // Set app.day to a valid day from the derived set.
  // Default to second day (index 1) if available, matching the original pattern.
  if (DAYS.length > 0) {
    const currentDayValid = DAY_KEYS.includes(app.day);
    if (!currentDayValid) {
      app.day = DAY_KEYS.length > 1 ? DAY_KEYS[1] : DAY_KEYS[0];
    }
  }
}

const SES_LABELS = {
  asia:  'Asia 19:00–00:00',
  lokz:  'LOKZ 02:00–05:00',
  nyokz: 'NYOKZ 07:00–10:00',
  other: 'Other',
};

/**
 * Primitives available for the chart. Derived dynamically from fixture data
 * via derivePrimitivesFromData(). Only includes primitives that have per-TF
 * detections (excludes global-only like asia_range, reference_levels).
 */
let PRIMITIVES = [
  'displacement', 'fvg', 'mss', 'order_block', 'liquidity_sweep'
];

const TF_KEYS = new Set(['1m', '5m', '15m', '1H', '4H']);

function derivePrimitivesFromData(evalData) {
  if (!evalData || !evalData.per_config) return;
  const primSet = new Set();
  let hasContinuations = false;
  for (const cfgData of Object.values(evalData.per_config)) {
    const pp = cfgData.per_primitive;
    if (!pp) continue;
    for (const [prim, primData] of Object.entries(pp)) {
      const ptf = primData.per_tf;
      if (!ptf) continue;
      for (const tf of Object.keys(ptf)) {
        if (TF_KEYS.has(tf) && ptf[tf].detections && ptf[tf].detections.length > 0) {
          primSet.add(prim);
          // Check if liquidity_sweep has any CONTINUATION type detections
          if (prim === 'liquidity_sweep' && !hasContinuations) {
            hasContinuations = ptf[tf].detections.some(
              d => d.properties && d.properties.type === 'CONTINUATION'
            );
          }
          break;
        }
      }
    }
  }
  if (hasContinuations) {
    primSet.add('sweep_continuation');
  }
  if (primSet.size > 0) {
    PRIMITIVES = Array.from(primSet).sort();
  }
}

/* ── Per-Primitive Marker Styles (shape + colour for chart distinguishability) ── */

const PRIMITIVE_MARKERS = {
  swing_points:        { shape_high: 'arrowDown', shape_low: 'arrowUp',  color: '#00e5ff', label: 'Swing Points' },
  liquidity_sweep:     { shape_high: 'arrowDown', shape_low: 'arrowUp',  color: '#ff9800', label: 'Liquidity Sweep' },
  sweep_continuation:  { shape_high: 'square',    shape_low: 'square',   color: '#9e9e9e', label: 'Continuation' },
  mss:                 { shape_high: 'arrowDown', shape_low: 'arrowUp',  color: '#ffeb3b', label: 'MSS' },
  displacement:        { shape_high: 'square',    shape_low: 'square',   color: '#e040fb', label: 'Displacement' },
  order_block:         { shape_high: 'square',    shape_low: 'square',   color: '#448aff', label: 'Order Block' },
  fvg:                 { shape_high: 'circle',    shape_low: 'circle',   color: '#69f0ae', label: 'FVG' },
  ote:                 { shape_high: 'circle',    shape_low: 'circle',   color: '#ffb74d', label: 'OTE' },
  asia_range:          { shape_high: 'square',    shape_low: 'square',   color: '#e91e63', label: 'Asia Range' },
  htf_liquidity:       { shape_high: 'arrowDown', shape_low: 'arrowUp',  color: '#8bc34a', label: 'HTF Liquidity' },
  session_liquidity:   { shape_high: 'square',    shape_low: 'square',   color: '#795548', label: 'Session Liquidity' },
  reference_levels:    { shape_high: 'circle',    shape_low: 'circle',   color: '#607d8b', label: 'Ref Levels' },
};

/* ── Multi-Config Color Palettes ───────────────────────────────────────────── */

const CONFIG_COLORS = [
  {
    name: 'Config A',
    base: '#26a69a',
    light: '#4db6ac',
    dark: '#00897b',
    fill: 'rgba(38,166,154,0.22)',
    fillLight: 'rgba(38,166,154,0.10)',
    marker: '#00e5d4',
  },
  {
    name: 'Config B',
    base: '#f7c548',
    light: '#ffd54f',
    dark: '#f9a825',
    fill: 'rgba(247,197,72,0.22)',
    fillLight: 'rgba(247,197,72,0.10)',
    marker: '#ffe082',
  },
  {
    name: 'Config C',
    base: '#9c27b0',
    light: '#ba68c8',
    dark: '#7b1fa2',
    fill: 'rgba(156,39,176,0.22)',
    fillLight: 'rgba(156,39,176,0.10)',
    marker: '#ce93d8',
  },
];

/* ── Plotly Dark Theme Defaults ────────────────────────────────────────────── */

const PLOTLY_DARK_LAYOUT = {
  paper_bgcolor: '#0a0e17',
  plot_bgcolor: '#131722',
  font: {
    color: '#d1d4dc',
    family: "'IBM Plex Mono', monospace",
    size: 11,
  },
  xaxis: {
    gridcolor: '#1e222d',
    linecolor: '#2a2e39',
    zerolinecolor: '#2a2e39',
  },
  yaxis: {
    gridcolor: '#1e222d',
    linecolor: '#2a2e39',
    zerolinecolor: '#2a2e39',
  },
  margin: { l: 60, r: 20, t: 40, b: 40 },
};

const PLOTLY_CONFIG = { responsive: true, displayModeBar: false };

/**
 * Create a full Plotly layout by merging dark theme defaults with overrides.
 * @param {Object} overrides - Layout overrides to merge
 * @returns {Object} Complete Plotly layout object
 */
function plotlyLayout(overrides) {
  const layout = JSON.parse(JSON.stringify(PLOTLY_DARK_LAYOUT));
  if (overrides) {
    for (const key of Object.keys(overrides)) {
      if (typeof overrides[key] === 'object' && !Array.isArray(overrides[key]) && layout[key]) {
        Object.assign(layout[key], overrides[key]);
      } else {
        layout[key] = overrides[key];
      }
    }
  }
  return layout;
}

/* ── Forex Day Utility ─────────────────────────────────────────────────────── */

/**
 * Compute the forex day (YYYY-MM-DD) a timestamp belongs to.
 * Forex day starts at 17:00 NY — a candle at/after 17:00 belongs to the NEXT day.
 * @param {string} rawTimeStr — e.g. "2025-09-28T20:00:00-04:00" or "2025-09-28T20:00:00"
 * @returns {string} YYYY-MM-DD forex day
 */
function getForexDay(rawTimeStr) {
  if (!rawTimeStr) return '';
  // Strip TZ offset to get local NY time
  const clean = rawTimeStr.replace(/[+-]\d{2}:\d{2}$/, '');
  const tPart = (clean.split('T')[1]) || '';
  const hour = parseInt(tPart.split(':')[0], 10);
  const datePart = clean.split('T')[0];

  if (hour >= 17) {
    // After 17:00 NY → belongs to NEXT forex day
    const d = new Date(datePart + 'T12:00:00Z');
    d.setUTCDate(d.getUTCDate() + 1);
    return d.toISOString().split('T')[0];
  }
  return datePart;
}

/* ── Utility Functions ─────────────────────────────────────────────────────── */

/**
 * Convert a NY-time ISO string to a Unix timestamp (seconds).
 * Treats the string as UTC so Lightweight Charts displays NY time on the axis.
 */
function toTS(s) {
  if (!s) return null;
  // Strip timezone offset if present (e.g., -04:00, +00:00)
  let clean = s.replace(/[+-]\d{2}:\d{2}$/, '');
  clean = clean.includes('T') ? clean : clean.replace(' ', 'T');
  const noZ = clean.endsWith('Z') ? clean.slice(0, -1) : clean;
  return Math.floor(new Date(noZ + 'Z').getTime() / 1000);
}

/** Format a 5-decimal price. */
function p5(n) { return Number(n).toFixed(5); }

/** Get display label for a day key. */
function dayLabel(k) { return DAYS.find(d => d.key === k)?.label || k; }

/** Format a number with commas. */
function fmtNum(n) {
  if (n == null) return '—';
  return Number(n).toLocaleString('en-US');
}

/** Format a percentage. */
function fmtPct(n) {
  if (n == null) return '—';
  return Number(n).toFixed(1) + '%';
}

/** Format mean ± std */
function fmtMeanStd(mean, std) {
  if (mean == null) return '—';
  const m = Number(mean).toFixed(1);
  const s = std != null ? Number(std).toFixed(1) : '0.0';
  return `${m} ± ${s}`;
}

/** Capitalize first letter */
function capitalize(s) {
  if (!s) return '';
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Format primitive name for display */
function primLabel(s) {
  if (!s) return '';
  return s.replace(/_/g, ' ').split(' ').map(capitalize).join(' ');
}

/* ── Variant Helpers ────────────────────────────────────────────────────────── */

/**
 * Extract variant information from loaded eval data.
 * Populates app.availableVariants, app.variantByConfig, app.hasVariantData.
 */
function extractVariantInfo() {
  app.availableVariants = [];
  app.variantByConfig = {};
  app.hasVariantData = false;

  if (!app.evalData || !app.evalData.per_config) return;

  const variants = new Set();
  for (const [cfgName, cfgData] of Object.entries(app.evalData.per_config)) {
    const v = cfgData.variant;
    if (v) {
      variants.add(v);
      app.variantByConfig[cfgName] = v;
      app.hasVariantData = true;
    }
  }

  // Also check pairwise for variant info
  if (app.evalData.pairwise) {
    for (const pw of Object.values(app.evalData.pairwise)) {
      if (pw.variant_a) variants.add(pw.variant_a);
      if (pw.variant_b) variants.add(pw.variant_b);
    }
  }

  app.availableVariants = Array.from(variants).sort();
}

/**
 * Get the variant name for a config. Returns '' if no variant info.
 */
function getConfigVariant(configName) {
  return app.variantByConfig[configName] || '';
}

/**
 * Get display label for a config, including variant name if available.
 * e.g. "locked_a8ra_v1" with variant "a8ra_v1" → "locked_a8ra_v1 (a8ra_v1)"
 * or just the config name if no variant info.
 */
function configDisplayLabel(configName) {
  const variant = getConfigVariant(configName);
  if (variant) return `${configName}`;
  return configName;
}

/**
 * Get variant-qualified primitive label.
 * e.g. "MSS (luxalgo_v1)" when variant present, or just "MSS" otherwise.
 */
function primVariantLabel(primName, configName) {
  const variant = getConfigVariant(configName);
  const base = primLabel(primName);
  if (variant) return `${base} (${variant})`;
  return base;
}

/* ── Data Loading ──────────────────────────────────────────────────────────── */

/** Show or hide the loading overlay */
function setLoading(visible) {
  const el = document.getElementById('loading-overlay');
  if (el) {
    el.classList.toggle('hidden', !visible);
  }
}

/** Show an error message in the error container */
function showError(msg) {
  const el = document.getElementById('error-message');
  if (el) {
    el.textContent = msg;
    el.classList.remove('hidden');
  }
}

/** Hide the error message */
function hideError() {
  const el = document.getElementById('error-message');
  if (el) {
    el.classList.add('hidden');
  }
}

/**
 * Fetch JSON with error handling. Returns null on failure.
 */
async function fetchJSON(url) {
  try {
    const sep = url.includes('?') ? '&' : '?';
    const resp = await fetch(url + sep + '_cb=' + Date.now());
    if (!resp.ok) {
      console.warn(`Failed to fetch ${url}: ${resp.status} ${resp.statusText}`);
      return null;
    }
    return await resp.json();
  } catch (e) {
    console.warn(`Error fetching ${url}:`, e.message);
    return null;
  }
}

/**
 * Available fixture files for the fixture/variant selector.
 * Each entry has a url and label. Populated during boot.
 */
const FIXTURE_FILES = [
  { key: 'default',      url: 'eval/evaluation_run.json',              label: 'Default (Phase 3)' },
  { key: 'calibration',  url: 'eval/evaluation_run_calibration.json',  label: 'Calibration Week (Olya Locked)' },
  { key: 'variant',      url: 'eval/evaluation_run_variant.json',      label: 'Variant Comparison' },
  { key: 'winner',       url: 'eval/search_winner.json',               label: 'Search Winner' },
];

/**
 * Load Schema 4A evaluation data (the main data file).
 * Returns the parsed object or null.
 */
async function loadEvalData() {
  const data = await fetchJSON('eval/evaluation_run.json');
  if (!data) {
    showError('Could not load evaluation data (eval/evaluation_run.json). Please run generate_eval_data.sh first.');
    return null;
  }
  // Validate minimum structure
  if (!data.schema_version || !data.per_config) {
    showError('Evaluation data is malformed (missing schema_version or per_config).');
    return null;
  }
  return data;
}

/**
 * Load a specific fixture file by key.
 * Returns the parsed object or null.
 */
async function loadFixtureByKey(fixtureKey) {
  const fixture = FIXTURE_FILES.find(f => f.key === fixtureKey);
  if (!fixture) {
    console.warn('Unknown fixture key:', fixtureKey);
    return null;
  }
  const data = await fetchJSON(fixture.url);
  if (!data) {
    console.warn(`Could not load fixture: ${fixture.url}`);
    return null;
  }
  if (!data.schema_version || !data.per_config) {
    console.warn(`Fixture ${fixture.url} is malformed.`);
    return null;
  }
  return data;
}

/**
 * Switch to a different fixture file. Reloads all data and re-renders the active tab.
 */
async function switchFixture(fixtureKey) {
  if (fixtureKey === app.activeVariantFixture && !app.weekMode) return;

  // Clear week mode when switching to a fixture
  if (app.weekMode) {
    app.weekMode = false;
    app.weekData = null;
    app.currentCompareWeek = null;
    const badge = document.getElementById('week-mode-badge');
    if (badge) badge.style.display = 'none';
    const weekPicker = document.getElementById('week-picker-compare');
    if (weekPicker) weekPicker.value = '';
  }

  setLoading(true);
  hideError();

  const data = await loadFixtureByKey(fixtureKey);
  if (!data) {
    showError(`Could not load fixture "${fixtureKey}". Keeping current data.`);
    setLoading(false);
    return;
  }

  app.evalData = data;
  app.activeVariantFixture = fixtureKey;
  app.selectedConfigs = [...(data.configs || [])];

  // Re-derive day tabs and primitives from the new fixture data
  deriveDaysFromData(data);
  derivePrimitivesFromData(data);

  // Re-extract variant info
  extractVariantInfo();

  // Update metadata
  renderMetadata();

  // Reset chart and stats initialization flags so they rebuild on next visit.
  // These globals are defined in chart-tab.js / stats-tab.js respectively.
  if (typeof resetChartTab === 'function') resetChartTab();
  if (typeof resetStatsTab === 'function') resetStatsTab();

  // Re-render current tab
  switchTab(app.activeTab);

  setLoading(false);
}

/**
 * Probe which fixture files are actually available on disk.
 * Fetches each fixture to check availability and extract date range for display.
 */
async function probeAvailableFixtures() {
  // Default fixture is already loaded — extract its date range
  const defaultFixture = FIXTURE_FILES.find(f => f.key === 'default');
  if (defaultFixture && app.evalData) {
    defaultFixture.available = true;
    const range = app.evalData.dataset && app.evalData.dataset.range;
    if (range && range.length === 2) {
      defaultFixture.displayLabel = `${defaultFixture.label} [${range[0]} → ${range[1]}]`;
    }
  }

  // Probe other fixtures with a full fetch to extract date range
  const others = FIXTURE_FILES.filter(f => f.key !== 'default');
  await Promise.all(others.map(async (fixture) => {
    try {
      const data = await fetchJSON(fixture.url);
      if (data && data.schema_version && data.per_config) {
        fixture.available = true;
        const range = data.dataset && data.dataset.range;
        if (range && range.length === 2) {
          fixture.displayLabel = `${fixture.label} [${range[0]} → ${range[1]}]`;
        }
      } else {
        fixture.available = false;
      }
    } catch {
      fixture.available = false;
    }
  }));
}

/**
 * Get available fixture files for the UI selector.
 */
function getAvailableFixtures() {
  return FIXTURE_FILES.filter(f => f.available !== false);
}

/**
 * Load Schema 4D sweep data.
 * Tries sweep files matching common naming patterns.
 */
async function loadSweepData() {
  // Try known filenames (2D grid sweep, then 1D single-param sweep)
  const candidates = [
    'eval/sweep_displacement_ltf_atr_multiplier.json',
    'eval/sweep_displacement_1d_atr_multiplier.json',
  ];
  for (const url of candidates) {
    const data = await fetchJSON(url);
    if (data && data.axes) return data;
  }
  console.info('No sweep data file found — Heatmap tab will show empty state.');
  return null;
}

/**
 * Load Schema 4E walk-forward data.
 */
async function loadWalkForwardData() {
  const candidates = [
    'eval/walk_forward_displacement.json',
  ];
  for (const url of candidates) {
    const data = await fetchJSON(url);
    if (data && data.summary) return data;
  }
  console.info('No walk-forward data file found — Walk-Forward tab will show empty state.');
  return null;
}

/**
 * Load candle data for a specific day. Uses caching.
 */
async function loadCandles(dayKey) {
  if (app.candlesByDay[dayKey]) return app.candlesByDay[dayKey];
  const data = await fetchJSON(`candles_${dayKey}.json`);
  if (data) {
    app.candlesByDay[dayKey] = data;
  }
  return data;
}

/**
 * Load session boundaries (once).
 */
async function loadSessionBoundaries() {
  if (app.sessionBoundaries) return app.sessionBoundaries;
  const data = await fetchJSON('session_boundaries.json');
  if (data) {
    app.sessionBoundaries = data;
  }
  return data;
}

/* ── Page-Level TF Selector ─────────────────────────────────────────────────── */

const COMPARE_TF_OPTIONS = ['1m', '5m', '15m', '1H', '4H'];

function isHTF(tf) { return ['1H', '4H', '1D'].includes(tf); }

/**
 * Render TF buttons in the page-level compare-tf-group container.
 * Syncs with app.tf and triggers chart + stats refresh on change.
 */
function renderCompareTFButtons() {
  const container = document.getElementById('compare-tf-group');
  if (!container) return;
  container.innerHTML = '';
  for (const tf of COMPARE_TF_OPTIONS) {
    const btn = document.createElement('button');
    btn.className = 'tf-btn' + (tf === app.tf ? ' active' : '');
    btn.textContent = tf;
    btn.addEventListener('click', async () => {
      if (tf === app.tf) return;
      const wasHTF = isHTF(app.tf);
      const nowHTF = isHTF(tf);
      app.tf = tf;

      if (!wasHTF && nowHTF && app.weekManifest.length > 0) {
        app.day = null;
        renderCompareTFButtons();
        const chartTFGroup = document.getElementById('chart-tf-group');
        if (chartTFGroup && typeof renderTFButtons === 'function') renderTFButtons(chartTFGroup);
        const dayTabsEl = document.getElementById('chart-day-tabs');
        if (dayTabsEl && typeof renderDayTabs === 'function') renderDayTabs(dayTabsEl);
        await loadAllWeeksHTF_compare();
        if (typeof resetChartTab === 'function') resetChartTab();
        if (typeof switchTab === 'function') switchTab(app.activeTab);
      } else if (wasHTF && !nowHTF) {
        app.day = DAY_KEYS.length > 0 ? DAY_KEYS[0] : null;
        // Restore single-week or fixture mode
        if (app.currentCompareWeek) {
          await onCompareWeekSelect();
        } else if (app.evalData) {
          app.weekMode = false;
          app.weekData = null;
          deriveDaysFromData(app.evalData);
          derivePrimitivesFromData(app.evalData);
          if (typeof resetChartTab === 'function') resetChartTab();
        }
        renderCompareTFButtons();
        const chartTFGroup = document.getElementById('chart-tf-group');
        if (chartTFGroup && typeof renderTFButtons === 'function') renderTFButtons(chartTFGroup);
        const dayTabsEl = document.getElementById('chart-day-tabs');
        if (dayTabsEl && typeof renderDayTabs === 'function') renderDayTabs(dayTabsEl);
        if (typeof switchTab === 'function') switchTab(app.activeTab);
      } else {
        renderCompareTFButtons();
        const chartTFGroup = document.getElementById('chart-tf-group');
        if (chartTFGroup && typeof renderTFButtons === 'function') renderTFButtons(chartTFGroup);
        const dayTabsEl = document.getElementById('chart-day-tabs');
        if (dayTabsEl && typeof renderDayTabs === 'function') renderDayTabs(dayTabsEl);
        if (typeof refreshChart === 'function') refreshChart();
        if (typeof resetStatsTab === 'function') {
          resetStatsTab();
          if (app.activeTab === 'stats' && typeof initStatsTab === 'function') initStatsTab();
        }
      }
    });
    container.appendChild(btn);
  }
}

/**
 * Boot: load all data, populate state, update UI.
 */
async function bootApp() {
  setLoading(true);
  hideError();

  try {
    // Load primary data in parallel
    const [evalData, sweepData, wfData, sessionBounds] = await Promise.all([
      loadEvalData(),
      loadSweepData(),
      loadWalkForwardData(),
      loadSessionBoundaries(),
    ]);

    app.evalData = evalData;
    app.sweepData = sweepData;
    app.walkForwardData = wfData;

    if (!evalData) {
      setLoading(false);
      return;
    }

    // Track active fixture
    app.activeVariantFixture = 'default';

    // Set selected configs from evalData
    app.selectedConfigs = [...(evalData.configs || [])];

    // Derive day tabs and primitives from fixture data
    deriveDaysFromData(evalData);
    derivePrimitivesFromData(evalData);

    // Extract variant info from loaded data
    extractVariantInfo();

    // Probe which fixture files are actually available (for the fixture selector)
    await probeAvailableFixtures();

    // Pre-load candle data for default day
    await loadCandles(app.day);

    // Render metadata header
    renderMetadata();

    // Render page-level TF selector
    renderCompareTFButtons();

    // Load week manifest for detection mode (non-blocking)
    loadCompareWeekManifest();

    // Render initial tab
    switchTab(app.activeTab);

  } catch (err) {
    console.error('Boot error:', err);
    showError('An unexpected error occurred during data loading: ' + err.message);
  } finally {
    setLoading(false);
  }
}

/* ── Tab Navigation ────────────────────────────────────────────────────────── */

/**
 * Switch to a tab and render its content.
 */
function switchTab(tabId) {
  app.activeTab = tabId;

  // Update tab button styling
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabId);
  });

  // Show/hide content panels
  document.querySelectorAll('.tab-content').forEach(panel => {
    panel.classList.toggle('hidden', panel.id !== `tab-${tabId}`);
  });

  // In week mode, non-chart tabs show a message since they need Schema 4A data
  if (app.weekMode && tabId !== 'chart') {
    const panel = document.getElementById(`tab-${tabId}`);
    if (panel) {
      panel.innerHTML = `
        <div class="tab-placeholder">
          <div class="ph-icon">📊</div>
          <div class="ph-title">Week Mode</div>
          <div class="ph-desc">This tab requires calibration fixture data (Schema 4A). Select "— Calibration fixtures —" from the week picker to view ${tabId} data.</div>
        </div>
      `;
    }
    return;
  }

  // Fire tab init (future workers implement these)
  if (tabId === 'chart' && typeof initChartTab === 'function') {
    initChartTab();
  } else if (tabId === 'stats' && typeof initStatsTab === 'function') {
    initStatsTab();
  } else if (tabId === 'heatmap' && typeof initHeatmapTab === 'function') {
    initHeatmapTab();
  } else if (tabId === 'walkforward' && typeof initWalkForwardTab === 'function') {
    initWalkForwardTab();
  }
}

/* ── Metadata Rendering ────────────────────────────────────────────────────── */

function renderMetadata() {
  const el = document.getElementById('run-metadata');
  if (!el || !app.evalData) return;

  const d = app.evalData;
  const dataset = d.dataset || {};
  const range = dataset.range || [];
  const sv = d.schema_version || '?';

  let variantMeta = '';
  if (app.hasVariantData && app.availableVariants.length > 0) {
    variantMeta = `
      <span class="meta-sep">·</span>
      <span class="meta-item" title="Variants"><span class="meta-label">Variants</span> ${app.availableVariants.join(', ')}</span>
    `;
  }

  el.innerHTML = `
    <span class="meta-item" title="Schema version"><span class="meta-label">Schema</span> v${sv}</span>
    <span class="meta-sep">·</span>
    <span class="meta-item" title="Run ID"><span class="meta-label">Run</span> ${d.run_id || '—'}</span>
    <span class="meta-sep">·</span>
    <span class="meta-item" title="Dataset"><span class="meta-label">Dataset</span> ${range[0] || '?'} → ${range[1] || '?'}</span>
    <span class="meta-sep">·</span>
    <span class="meta-item" title="Configs"><span class="meta-label">Configs</span> ${(d.configs || []).join(', ')}</span>
    ${variantMeta}
  `;
}

/**
 * Render week-mode metadata when in detection mode (replaces fixture metadata).
 */
function renderWeekModeMetadata() {
  const el = document.getElementById('run-metadata');
  if (!el || !app.currentCompareWeek) return;

  const w = app.currentCompareWeek;
  el.innerHTML = `
    <span class="meta-item" title="Mode"><span class="meta-label">Mode</span> Detection</span>
    <span class="meta-sep">·</span>
    <span class="meta-item" title="Week"><span class="meta-label">Week</span> ${w.week}</span>
    <span class="meta-sep">·</span>
    <span class="meta-item" title="Range"><span class="meta-label">Range</span> ${w.start} → ${w.end}</span>
    <span class="meta-sep">·</span>
    <span class="meta-item" title="Detections"><span class="meta-label">Detections</span> ${w.detection_count.toLocaleString()}</span>
    <span class="meta-sep">·</span>
    <span class="meta-item" title="Config"><span class="meta-label">Config</span> locked_a8ra_v1</span>
  `;
}

/* ── Week Mode (Detection Browsing) ────────────────────────────────────────── */

/**
 * Load the week manifest (data/weeks.json) and populate the compare week picker.
 */
async function loadCompareWeekManifest() {
  try {
    const resp = await fetch('data/weeks.json?_cb=' + Date.now());
    if (resp.ok) {
      app.weekManifest = await resp.json();
      populateCompareWeekPicker();
    }
  } catch (e) {
    /* weeks.json not available — no week mode */
    console.info('Week manifest not found — week mode disabled.');
  }
}

let _cHTFAllWeeksLoaded = false;

async function loadAllWeeksHTF_compare() {
  if (_cHTFAllWeeksLoaded) return;
  setLoading(true);
  try {
    const fetches = app.weekManifest.map(w => Promise.all([
      fetchJSON(`data/candles/${w.week}.json`),
      fetchJSON(`data/detections/${w.week}.json`),
      fetchJSON(`data/sessions/${w.week}.json`),
    ]));
    const results = await Promise.all(fetches);

    const merged = {};
    for (const tf of ['1H', '4H']) { merged[tf] = []; }
    const mergedDets = {};
    const mergedSessions = [];

    for (const [candles, dets, sessions] of results) {
      if (candles) {
        for (const tf of ['1H', '4H']) {
          if (candles[tf]) merged[tf].push(...candles[tf]);
        }
      }
      if (dets && dets.detections_by_primitive) {
        for (const [prim, byTf] of Object.entries(dets.detections_by_primitive)) {
          if (!mergedDets[prim]) mergedDets[prim] = {};
          for (const [tf, arr] of Object.entries(byTf)) {
            if (!mergedDets[prim][tf]) mergedDets[prim][tf] = [];
            mergedDets[prim][tf].push(...arr);
          }
        }
      }
      if (sessions) mergedSessions.push(...sessions);
    }

    app.weekMode = true;
    app.weekData = {
      candleData: merged,
      detectionData: { detections_by_primitive: mergedDets },
      sessionData: mergedSessions,
    };

    // Derive all days/primitives from the merged data
    const allDays = [];
    for (const w of app.weekManifest) {
      if (w.forex_days) allDays.push(...w.forex_days);
    }
    DAY_KEYS = [...new Set(allDays)].sort();
    const SHORT_DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
    const SHORT_MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    DAY_LABELS = DAY_KEYS.map(d => {
      const dt = new Date(d + 'T00:00:00Z');
      return `${SHORT_DAYS[dt.getUTCDay()]} ${SHORT_MONTHS[dt.getUTCMonth()]} ${dt.getUTCDate()}`;
    });
    DAYS = DAY_KEYS.map((k, i) => ({ key: k, label: DAY_LABELS[i] }));

    deriveWeekModePrimitives(app.weekData.detectionData);
    _cHTFAllWeeksLoaded = true;
  } catch (e) {
    console.error('Failed to load all weeks for HTF:', e);
  }
  setLoading(false);
}

/**
 * Populate the compare week picker dropdown from the manifest.
 */
function populateCompareWeekPicker() {
  const picker = document.getElementById('week-picker-compare');
  if (!picker) return;

  picker.innerHTML = '';

  // Default option: back to calibration fixtures
  const placeholder = document.createElement('option');
  placeholder.value = '';
  placeholder.textContent = '— Calibration fixtures —';
  picker.appendChild(placeholder);

  if (app.weekManifest.length === 0) return;

  for (const w of app.weekManifest) {
    const opt = document.createElement('option');
    opt.value = w.week;
    opt.textContent = `${w.week} (${w.start} → ${w.end}) · ${w.detection_count.toLocaleString()} dets`;
    picker.appendChild(opt);
  }

  picker.addEventListener('change', onCompareWeekSelect);
}

/**
 * Handle week picker change: switch to week mode or back to fixture mode.
 */
async function onCompareWeekSelect() {
  const picker = document.getElementById('week-picker-compare');
  const weekId = picker.value;

  if (!weekId) {
    // Switching back to fixture mode
    exitWeekMode();
    return;
  }

  // Find manifest entry
  const weekEntry = app.weekManifest.find(w => w.week === weekId);
  if (!weekEntry) return;

  setLoading(true);
  hideError();

  try {
    // Load week data in parallel
    const [candleData, detectionData, sessionData] = await Promise.all([
      fetchJSON(`data/candles/${weekId}.json`),
      fetchJSON(`data/detections/${weekId}.json`),
      fetchJSON(`data/sessions/${weekId}.json`),
    ]);

    app.weekMode = true;
    app.currentCompareWeek = weekEntry;
    app.weekData = {
      candleData: candleData,
      detectionData: detectionData,
      sessionData: sessionData,
    };

    // Derive primitives from detection data for week mode
    deriveWeekModePrimitives(detectionData);

    // Derive day tabs from the week's forex_days
    deriveWeekModeDays(weekEntry);

    // Update UI indicators
    const badge = document.getElementById('week-mode-badge');
    if (badge) badge.style.display = '';

    // Update metadata bar
    renderWeekModeMetadata();

    // Reset chart so it re-initializes with new data
    if (typeof resetChartTab === 'function') resetChartTab();
    if (typeof resetStatsTab === 'function') resetStatsTab();

    // Switch to chart tab (primary view for week mode)
    switchTab('chart');

  } catch (err) {
    console.error('Error loading week data:', err);
    showError('Failed to load week data: ' + err.message);
  } finally {
    setLoading(false);
  }
}

/**
 * Exit week mode and return to fixture mode.
 */
function exitWeekMode() {
  if (!app.weekMode) return;

  app.weekMode = false;
  app.weekData = null;
  app.currentCompareWeek = null;

  // Hide week mode badge
  const badge = document.getElementById('week-mode-badge');
  if (badge) badge.style.display = 'none';

  // Re-derive days and primitives from fixture data
  if (app.evalData) {
    deriveDaysFromData(app.evalData);
    derivePrimitivesFromData(app.evalData);
  }

  // Restore fixture metadata
  renderMetadata();

  // Reset chart and stats tabs to rebuild
  if (typeof resetChartTab === 'function') resetChartTab();
  if (typeof resetStatsTab === 'function') resetStatsTab();

  // Re-render current tab
  switchTab(app.activeTab);
}

/**
 * Derive PRIMITIVES list from week detection data (detection mode).
 */
function deriveWeekModePrimitives(detectionData) {
  if (!detectionData || !detectionData.detections_by_primitive) return;

  const primSet = new Set();
  const dbp = detectionData.detections_by_primitive;
  let hasContinuations = false;

  for (const [prim, byTf] of Object.entries(dbp)) {
    for (const [tf, dets] of Object.entries(byTf)) {
      if (TF_KEYS.has(tf) && dets && dets.length > 0) {
        primSet.add(prim);
        // Check for continuations in liquidity_sweep
        if (prim === 'liquidity_sweep' && !hasContinuations) {
          hasContinuations = dets.some(
            d => d.properties && d.properties.type === 'CONTINUATION'
          );
        }
        break;
      }
    }
  }

  if (hasContinuations) {
    primSet.add('sweep_continuation');
  }

  if (primSet.size > 0) {
    PRIMITIVES = Array.from(primSet).sort();
  }
}

/**
 * Derive DAY_KEYS / DAYS from a week manifest entry's forex_days.
 */
function deriveWeekModeDays(weekEntry) {
  const SHORT_DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const SHORT_MONTHS = ['Jan','Feb','Mar','Apr','May','Jun',
                        'Jul','Aug','Sep','Oct','Nov','Dec'];

  let days = (weekEntry.forex_days || []).slice();

  // Filter to weekdays
  days = days.filter(d => {
    const dt = new Date(d + 'T00:00:00Z');
    const dow = dt.getUTCDay();
    return dow >= 1 && dow <= 5;
  });

  DAY_KEYS = days;
  DAY_LABELS = days.map(d => {
    const dt = new Date(d + 'T00:00:00Z');
    const dow = SHORT_DAYS[dt.getUTCDay()];
    const mon = SHORT_MONTHS[dt.getUTCMonth()];
    const day = dt.getUTCDate();
    return `${dow} ${mon} ${day}`;
  });
  DAYS = DAY_KEYS.map((k, i) => ({ key: k, label: DAY_LABELS[i] }));

  if (DAYS.length > 0) {
    app.day = DAY_KEYS.length > 1 ? DAY_KEYS[1] : DAY_KEYS[0];
  }
}
