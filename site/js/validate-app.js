/* ═══════════════════════════════════════════════════════════════════════════════
 * validate-app.js — Global state, data loading, and week management
 *                   for the Phase 3.5 Validation Mode page
 * ═══════════════════════════════════════════════════════════════════════════════ */

/* ── Global App State ──────────────────────────────────────────────────────── */

const vApp = {
  // Manifest
  weeks: [],              // weeks.json manifest array

  // Current selection
  currentWeek: null,      // week manifest entry object
  tf: '5m',              // active timeframe
  day: null,             // active forex day (YYYY-MM-DD)

  // Loaded data (per-week, cleared on week switch)
  candleData: null,       // { "1m": [...], "5m": [...], "15m": [...] }
  detectionData: null,    // { detections_by_primitive: { prim: { tf: [...] } } }
  sessionData: null,      // array of session boundary objects
  labelsData: null,       // array of label objects (from disk)

  // Primitive toggle state: { primName: boolean }
  primitiveToggles: {},

  // Chart refs (set by validate-chart.js)
  chart: null,
  candleSeries: null,
};

/* ── Primitives Config ─────────────────────────────────────────────────────── */

const V_PRIMITIVES = [
  { key: 'displacement',    label: 'Displacement',    color: '#26a69a' },
  { key: 'fvg',             label: 'FVG',             color: '#2962ff' },
  { key: 'mss',             label: 'MSS',             color: '#f7c548' },
  { key: 'order_block',     label: 'Order Block',     color: '#9c27b0' },
  { key: 'liquidity_sweep', label: 'Liq Sweep',       color: '#ef5350' },
  { key: 'swing_points',    label: 'Swing Points',    color: '#00bcd4' },
  { key: 'ote',             label: 'OTE',             color: '#ff9800' },
  { key: 'asia_range',      label: 'Asia Range',      color: '#e91e63' },
  { key: 'htf_liquidity',   label: 'HTF Liq',         color: '#8bc34a' },
  { key: 'session_liquidity', label: 'Session Liq',   color: '#795548' },
  { key: 'reference_levels',  label: 'Ref Levels',    color: '#607d8b' },
];

/* Lookup helpers */
function vPrimLabel(key) {
  const p = V_PRIMITIVES.find(x => x.key === key);
  return p ? p.label : key;
}

function vPrimColor(key) {
  const p = V_PRIMITIVES.find(x => x.key === key);
  return p ? p.color : '#787b86';
}

/* ── Session Legend Metadata ────────────────────────────────────────────────── */

const V_SESSION_META = [
  { key: 'asia',  label: 'Asia 19:00–00:00', color: 'rgba(156,39,176,0.5)' },
  { key: 'lokz',  label: 'LOKZ 02:00–05:00', color: 'rgba(41,98,255,0.5)' },
  { key: 'nyokz', label: 'NYOKZ 07:00–10:00', color: 'rgba(247,197,72,0.5)' },
];

/* ── Timestamp Conversion ──────────────────────────────────────────────────── */

function toTS(s) {
  if (!s) return null;
  // Strip timezone offset if present (e.g., -04:00, +00:00)
  let clean = s;
  // Remove tz offset like -04:00 or +00:00
  clean = clean.replace(/[+-]\d{2}:\d{2}$/, '');
  // Ensure T separator
  clean = clean.includes('T') ? clean : clean.replace(' ', 'T');
  // Remove trailing Z
  const noZ = clean.endsWith('Z') ? clean.slice(0, -1) : clean;
  return Math.floor(new Date(noZ + 'Z').getTime() / 1000);
}

/* ── Day Label Formatting ──────────────────────────────────────────────────── */

function dayLabel(dateStr) {
  const d = new Date(dateStr + 'T12:00:00Z');
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${days[d.getUTCDay()]} ${months[d.getUTCMonth()]} ${d.getUTCDate()}`;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Data Loading
 * ═══════════════════════════════════════════════════════════════════════════════ */

async function loadManifest() {
  try {
    const resp = await fetch('data/weeks.json');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    vApp.weeks = await resp.json();
  } catch (e) {
    console.error('Failed to load weeks.json:', e);
    vApp.weeks = [];
  }
}

async function loadWeekData(weekId) {
  const loading = document.getElementById('loading-overlay');
  if (loading) loading.classList.remove('hidden');

  try {
    const [candleResp, detResp, sessResp] = await Promise.all([
      fetch(`data/candles/${weekId}.json`),
      fetch(`data/detections/${weekId}.json`),
      fetch(`data/sessions/${weekId}.json`),
    ]);

    vApp.candleData = candleResp.ok ? await candleResp.json() : null;
    vApp.detectionData = detResp.ok ? await detResp.json() : null;
    vApp.sessionData = sessResp.ok ? await sessResp.json() : null;

    // Try loading labels (may 404 if no labels yet)
    try {
      const labelsResp = await fetch(`data/labels/${weekId}.json`);
      vApp.labelsData = labelsResp.ok ? await labelsResp.json() : [];
    } catch (_) {
      vApp.labelsData = [];
    }
  } catch (e) {
    console.error('Failed to load week data:', e);
    vApp.candleData = null;
    vApp.detectionData = null;
    vApp.sessionData = null;
    vApp.labelsData = [];
  }

  if (loading) loading.classList.add('hidden');
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Week Picker
 * ═══════════════════════════════════════════════════════════════════════════════ */

function populateWeekPicker() {
  const picker = document.getElementById('week-picker');
  if (!picker) return;

  picker.innerHTML = '';

  if (vApp.weeks.length === 0) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = 'No weeks available';
    picker.appendChild(opt);
    return;
  }

  // Placeholder option
  const placeholder = document.createElement('option');
  placeholder.value = '';
  placeholder.textContent = 'Select a week…';
  picker.appendChild(placeholder);

  for (const w of vApp.weeks) {
    const opt = document.createElement('option');
    opt.value = w.week;
    opt.textContent = `${w.week} (${w.start} → ${w.end}) · ${w.detection_count.toLocaleString()} dets`;
    picker.appendChild(opt);
  }

  picker.addEventListener('change', onWeekSelect);
}

async function onWeekSelect() {
  const picker = document.getElementById('week-picker');
  const weekId = picker.value;
  if (!weekId) return;

  // Find manifest entry
  const weekEntry = vApp.weeks.find(w => w.week === weekId);
  if (!weekEntry) return;

  // Clear previous state completely
  vApp.currentWeek = weekEntry;
  vApp.candleData = null;
  vApp.detectionData = null;
  vApp.sessionData = null;
  vApp.labelsData = null;

  // Default to first forex day
  const days = weekEntry.forex_days || [];
  vApp.day = days.length > 0 ? days[0] : null;

  // Reset TF to 5m
  vApp.tf = '5m';

  // Initialize all primitive toggles to ON
  initPrimitiveToggles();

  // Load data for this week
  await loadWeekData(weekId);

  // Hide empty state
  const emptyState = document.getElementById('empty-state');
  if (emptyState) emptyState.style.display = 'none';

  // Update all UI
  renderDayTabs();
  renderTFButtons();
  renderPrimitiveToggles();
  updateMetadata();
  renderSessionLegend();

  // Create or refresh chart
  initOrRefreshChart();

  // Load labels from disk and rebuild rings for the new week
  if (typeof onVGTWeekChange === 'function') {
    await onVGTWeekChange();
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Primitive Toggles
 * ═══════════════════════════════════════════════════════════════════════════════ */

function initPrimitiveToggles() {
  vApp.primitiveToggles = {};
  // Only enable toggles for primitives actually present in the data
  for (const p of V_PRIMITIVES) {
    vApp.primitiveToggles[p.key] = true;
  }
}

function renderPrimitiveToggles() {
  const container = document.getElementById('prim-toggles');
  if (!container) return;
  container.innerHTML = '';

  // Only show primitives present in the detection data
  const presentPrimitives = getPresentPrimitives();

  for (const p of V_PRIMITIVES) {
    if (!presentPrimitives.has(p.key)) continue;
    const isOn = vApp.primitiveToggles[p.key] !== false;
    const btn = document.createElement('button');
    btn.className = 'prim-toggle' + (isOn ? ' active' : '');
    btn.dataset.primitive = p.key;
    btn.innerHTML = `<span class="prim-swatch" style="background:${isOn ? p.color : 'var(--faint)'}"></span>${p.label}`;
    btn.addEventListener('click', () => {
      vApp.primitiveToggles[p.key] = !vApp.primitiveToggles[p.key];
      renderPrimitiveToggles();
      rebuildValidateMarkers();
      updateDetectionCounts();
    });
    container.appendChild(btn);
  }
}

function getPresentPrimitives() {
  const present = new Set();
  if (!vApp.detectionData || !vApp.detectionData.detections_by_primitive) return present;
  for (const key of Object.keys(vApp.detectionData.detections_by_primitive)) {
    present.add(key);
  }
  return present;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Day Tabs
 * ═══════════════════════════════════════════════════════════════════════════════ */

function renderDayTabs() {
  const container = document.getElementById('day-tabs');
  if (!container) return;
  container.innerHTML = '';

  if (!vApp.currentWeek) return;

  const days = vApp.currentWeek.forex_days || [];
  for (const d of days) {
    const btn = document.createElement('button');
    btn.className = 'day-tab' + (d === vApp.day ? ' active' : '');
    btn.textContent = dayLabel(d);
    btn.dataset.day = d;
    btn.addEventListener('click', () => {
      if (d === vApp.day) return;
      vApp.day = d;
      renderDayTabs();
      refreshValidateChart();
    });
    container.appendChild(btn);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * TF Buttons
 * ═══════════════════════════════════════════════════════════════════════════════ */

const V_TF_OPTIONS = ['1m', '5m', '15m'];

function renderTFButtons() {
  const container = document.getElementById('tf-group');
  if (!container) return;
  container.innerHTML = '';

  for (const tf of V_TF_OPTIONS) {
    const btn = document.createElement('button');
    btn.className = 'tf-btn' + (tf === vApp.tf ? ' active' : '');
    btn.textContent = tf;
    btn.dataset.tf = tf;
    btn.addEventListener('click', () => {
      if (tf === vApp.tf) return;
      vApp.tf = tf;
      renderTFButtons();
      refreshValidateChart();
    });
    container.appendChild(btn);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Session Legend
 * ═══════════════════════════════════════════════════════════════════════════════ */

function renderSessionLegend() {
  const container = document.getElementById('session-legend');
  if (!container) return;
  let html = '';
  for (const s of V_SESSION_META) {
    html += `<span class="session-legend-item">
      <span class="session-swatch" style="background:${s.color}"></span>
      <span>${s.label}</span>
    </span>`;
  }
  container.innerHTML = html;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Metadata
 * ═══════════════════════════════════════════════════════════════════════════════ */

function updateMetadata() {
  const w = vApp.currentWeek;
  if (!w) return;

  const weekEl = document.getElementById('meta-week');
  const rangeEl = document.getElementById('meta-range');
  const detsEl = document.getElementById('meta-detections');

  if (weekEl) weekEl.textContent = w.week;
  if (rangeEl) rangeEl.textContent = `${w.start} → ${w.end}`;
  if (detsEl) detsEl.textContent = w.detection_count.toLocaleString();

  updateDetectionCounts();
}

function updateDetectionCounts() {
  const container = document.getElementById('detection-summary');
  if (!container) return;

  if (!vApp.detectionData || !vApp.detectionData.detections_by_primitive) {
    container.innerHTML = '';
    return;
  }

  const presentPrimitives = getPresentPrimitives();
  let html = '';

  for (const p of V_PRIMITIVES) {
    if (!presentPrimitives.has(p.key)) continue;
    if (vApp.primitiveToggles[p.key] === false) continue;

    const count = getDetCountForPrimitive(p.key);
    html += `<span class="det-count-item">
      <span class="det-count-label">${p.label}:</span>
      <span class="det-count-value" style="color:${p.color}">${count}</span>
    </span>`;
  }

  container.innerHTML = html;
}

function getDetCountForPrimitive(primKey) {
  if (!vApp.detectionData || !vApp.detectionData.detections_by_primitive) return 0;
  const primData = vApp.detectionData.detections_by_primitive[primKey];
  if (!primData) return 0;

  const tf = vApp.tf;
  let count = 0;

  // Some primitives have 'global' key instead of tf-specific keys
  const tfData = primData[tf] || primData['global'] || [];
  const dayDets = filterValidateDetectionsByDay(tfData, vApp.day);
  count = dayDets.length;

  return count;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Detection Filtering by Day
 * ═══════════════════════════════════════════════════════════════════════════════ */

function filterValidateDetectionsByDay(detections, dayKey) {
  if (!detections || !detections.length || !dayKey) return [];
  return detections.filter(det => {
    // Primary: use properties.forex_day
    const fd = det.properties && det.properties.forex_day;
    if (fd) return fd === dayKey;
    // Fallback: parse date from time string (strip timezone)
    const t = det.time || '';
    const clean = t.replace(/[+-]\d{2}:\d{2}$/, '');
    return clean.startsWith(dayKey);
  });
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Boot Sequence
 * ═══════════════════════════════════════════════════════════════════════════════ */

(async function boot() {
  await loadManifest();
  populateWeekPicker();
  renderSessionLegend();
  initPrimitiveToggles();

  // Wire up GT action bar buttons
  var exportBtn = document.getElementById('btn-export-labels-bar');
  if (exportBtn) {
    exportBtn.addEventListener('click', function() {
      if (typeof exportVGTLabels === 'function') exportVGTLabels();
    });
  }

  var lockBtn = document.getElementById('btn-lock-panel');
  if (lockBtn) {
    lockBtn.addEventListener('click', function() {
      if (typeof toggleLockPanel === 'function') toggleLockPanel();
    });
  }

  var lockCloseBtn = document.getElementById('lock-panel-close-btn');
  if (lockCloseBtn) {
    lockCloseBtn.addEventListener('click', function() {
      if (typeof toggleLockPanel === 'function') toggleLockPanel();
    });
  }
})();
