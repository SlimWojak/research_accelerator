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
};

/* ── Constants ─────────────────────────────────────────────────────────────── */

/* Day keys for the 5-day EURUSD dataset (Jan 8-12, 2024) */
const DAY_KEYS = ['2024-01-08','2024-01-09','2024-01-10','2024-01-11','2024-01-12'];
const DAY_LABELS = ['Mon Jan 8','Tue Jan 9','Wed Jan 10','Thu Jan 11','Fri Jan 12'];
const DAYS = DAY_KEYS.map((k, i) => ({ key: k, label: DAY_LABELS[i] }));

const SES_LABELS = {
  asia:  'Asia 19:00–00:00',
  lokz:  'LOKZ 02:00–05:00',
  nyokz: 'NYOKZ 07:00–10:00',
  other: 'Other',
};

const PRIMITIVES = [
  'displacement', 'fvg', 'mss', 'order_block', 'liquidity_sweep'
];

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

/* ── Utility Functions ─────────────────────────────────────────────────────── */

/**
 * Convert a NY-time ISO string to a Unix timestamp (seconds).
 * Treats the string as UTC so Lightweight Charts displays NY time on the axis.
 */
function toTS(s) {
  if (!s) return null;
  const clean = s.includes('T') ? s : s.replace(' ', 'T');
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
    const resp = await fetch(url);
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
  { key: 'default',  url: 'eval/evaluation_run.json',         label: 'Default (Phase 3)' },
  { key: 'variant',  url: 'eval/evaluation_run_variant.json',  label: 'Variant Comparison' },
  { key: 'winner',   url: 'eval/search_winner.json',           label: 'Search Winner' },
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
  if (fixtureKey === app.activeVariantFixture) return;

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
 * Marks unavailable fixtures so the UI can hide them.
 */
async function probeAvailableFixtures() {
  for (const fixture of FIXTURE_FILES) {
    if (fixture.key === 'default') {
      fixture.available = true; // Already loaded
      continue;
    }
    try {
      const resp = await fetch(fixture.url, { method: 'HEAD' });
      fixture.available = resp.ok;
    } catch {
      fixture.available = false;
    }
  }
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

    // Extract variant info from loaded data
    extractVariantInfo();

    // Probe which fixture files are actually available (for the fixture selector)
    await probeAvailableFixtures();

    // Pre-load candle data for default day
    await loadCandles(app.day);

    // Render metadata header
    renderMetadata();

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
