/* ═══════════════════════════════════════════════════════════════════════════════
 * strategy-app.js — Global state, data loading, and week management
 *                   for the Strategy Designer page
 * ═══════════════════════════════════════════════════════════════════════════════ */

/* ── Global App State ──────────────────────────────────────────────────────── */

const sApp = {
  // Manifest
  weeks: [],              // weeks.json manifest array

  // Current selection
  currentWeek: null,      // week manifest entry object
  tf: '5m',              // active timeframe (5m, 15m, 1H, 4H)
  day: null,             // active forex day (YYYY-MM-DD)
  direction: 'bearish',  // Default direction

  // Loaded data (per-week)
  candleData: null,       // { "5m": [...], "15m": [...] }
  detectionData: null,    // { detections_by_primitive: { prim: { tf: [...] } } }
  sessionData: null,      // array of session boundary objects

  // Chain state
  steps: [],             // Array of step objects
  gates: {
    kill_zone: ['lokz', 'nyokz'],
    asia_range_tier: ['tight', 'mid'],
  },

  // Evaluation results
  chainResults: null,    // Array of ChainMatch objects from evaluator
  selectedMatch: null,   // Currently selected match for drill-down

  // Template
  templateName: '',

  // Chart refs (set by strategy-chart.js)
  chart: null,
  candleSeries: null,
};

/* ── Primitive Palette (LOCKED L1 only) ────────────────────────────────────── */

const S_PRIMITIVES = [
  { key: 'liquidity_sweep', label: 'Liquidity Sweep', color: '#ef5350', defaults: { qualified_sweep: true } },
  { key: 'mss', label: 'MSS', color: '#f7c548', defaults: { break_type: 'REVERSAL', displacement_grade_min: 'VALID' } },
  { key: 'displacement', label: 'Displacement', color: '#26a69a', defaults: { quality_grade_min: 'VALID' } },
  { key: 'fvg', label: 'FVG', color: '#2962ff', defaults: { state: 'ACTIVE' } },
  { key: 'order_block', label: 'Order Block', color: '#9c27b0', defaults: { state: 'ACTIVE', zone_type: 'body' } },
  { key: 'ote', label: 'OTE Zone', color: '#ff9800', defaults: { fib_range: [0.618, 0.79] } },
  { key: 'session_liquidity', label: 'Session Liquidity', color: '#795548', defaults: { classification: 'CONSOLIDATION_BOX' } },
  { key: 'asia_range', label: 'Asia Range', color: '#e91e63', defaults: { tier: ['tight', 'mid'] } },
  { key: 'htf_eqh_eql', label: 'HTF EQH/EQL', color: '#8bc34a', defaults: { status: 'UNTOUCHED', min_touches: 2 } },
  { key: 'kill_zone', label: 'Kill Zone', color: '#00bcd4', defaults: { window: ['lokz', 'nyokz'] } },
  { key: 'reference_levels', label: 'Ref Levels', color: '#607d8b', defaults: {} },
];

/* ── Timing Options ─────────────────────────────────────────────────────────── */

const S_TIMING_OPTIONS = [
  { value: 'same_kill_zone', label: 'Same Kill Zone' },
  { value: 'same_session', label: 'Same Session' },
  { value: 'same_day', label: 'Same Day' },
  { value: 'same_bar', label: 'Same Bar' },
  { value: 'within_bars_5', label: 'Within 5 bars' },
  { value: 'within_bars_10', label: 'Within 10 bars' },
  { value: 'within_bars_20', label: 'Within 20 bars' },
];

/* ── Session Legend Metadata ────────────────────────────────────────────────── */

const S_SESSION_META = [
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
    sApp.weeks = await resp.json();
  } catch (e) {
    console.error('Failed to load weeks.json:', e);
    sApp.weeks = [];
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

    sApp.candleData = candleResp.ok ? await candleResp.json() : null;
    sApp.detectionData = detResp.ok ? await detResp.json() : null;
    sApp.sessionData = sessResp.ok ? await sessResp.json() : null;
  } catch (e) {
    console.error('Failed to load week data:', e);
    sApp.candleData = null;
    sApp.detectionData = null;
    sApp.sessionData = null;
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

  if (sApp.weeks.length === 0) {
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

  for (const w of sApp.weeks) {
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
  const weekEntry = sApp.weeks.find(w => w.week === weekId);
  if (!weekEntry) return;

  // Clear previous state
  sApp.currentWeek = weekEntry;
  sApp.candleData = null;
  sApp.detectionData = null;
  sApp.sessionData = null;
  sApp.chainResults = null;
  sApp.selectedMatch = null;

  // Default to first forex day
  const days = weekEntry.forex_days || [];
  sApp.day = days.length > 0 ? days[0] : null;

  // Reset TF to 5m (execution TF)
  sApp.tf = '5m';

  // Load data for this week
  await loadWeekData(weekId);

  // Hide empty state
  const emptyState = document.getElementById('empty-state');
  if (emptyState) emptyState.style.display = 'none';

  // Update all UI
  renderDayTabs();
  renderTFButtons();
  updateMetadata();

  // Create or refresh chart
  initOrRefreshStrategyChart();

  // Re-evaluate chain if steps exist
  if (sApp.steps.length > 0) {
    evaluateChain();
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Day Tabs
 * ═══════════════════════════════════════════════════════════════════════════════ */

function renderDayTabs() {
  const container = document.getElementById('day-tabs');
  if (!container) return;
  container.innerHTML = '';

  if (!sApp.currentWeek) return;

  const htf = isHTF(sApp.tf);

  // "All" tab — visible when HTF is active
  if (htf) {
    const allBtn = document.createElement('button');
    allBtn.className = 'day-tab' + (sApp.day === null ? ' active' : '');
    allBtn.textContent = 'All';
    allBtn.addEventListener('click', () => {
      if (sApp.day === null) return;
      sApp.day = null;
      renderDayTabs();
      refreshStrategyChart();
    });
    container.appendChild(allBtn);
  }

  const days = sApp.currentWeek.forex_days || [];
  for (const d of days) {
    const btn = document.createElement('button');
    btn.className = 'day-tab' + (d === sApp.day ? ' active' : '');
    btn.textContent = dayLabel(d);
    btn.dataset.day = d;
    btn.addEventListener('click', () => {
      if (d === sApp.day) return;
      sApp.day = d;
      renderDayTabs();
      refreshStrategyChart();
    });
    container.appendChild(btn);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * TF Buttons (5m, 15m, 1H, 4H)
 * ═══════════════════════════════════════════════════════════════════════════════ */

const S_TF_OPTIONS = ['5m', '15m', '1H', '4H'];

function isHTF(tf) { return ['1H', '4H', '1D'].includes(tf); }

function renderTFButtons() {
  const container = document.getElementById('tf-group');
  if (!container) return;
  container.innerHTML = '';

  for (const tf of S_TF_OPTIONS) {
    const btn = document.createElement('button');
    btn.className = 'tf-btn' + (tf === sApp.tf ? ' active' : '');
    btn.textContent = tf;
    btn.dataset.tf = tf;
    btn.addEventListener('click', () => {
      if (tf === sApp.tf) return;
      const wasHTF = isHTF(sApp.tf);
      const nowHTF = isHTF(tf);
      sApp.tf = tf;

      // Transition HTF ↔ LTF day selection
      if (!wasHTF && nowHTF) {
        // Switching TO HTF: show all days (week view)
        sApp.day = null;
      } else if (wasHTF && !nowHTF) {
        // Switching FROM HTF to LTF: select first forex day
        const days = sApp.currentWeek ? (sApp.currentWeek.forex_days || []) : [];
        sApp.day = days.length > 0 ? days[0] : null;
      }

      renderTFButtons();
      renderDayTabs();
      refreshStrategyChart();
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
  for (const s of S_SESSION_META) {
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
  const w = sApp.currentWeek;
  if (!w) return;

  const weekEl = document.getElementById('meta-week');
  const rangeEl = document.getElementById('meta-range');
  const detsEl = document.getElementById('meta-detections');

  if (weekEl) weekEl.textContent = w.week;
  if (rangeEl) rangeEl.textContent = `${w.start} → ${w.end}`;
  if (detsEl) detsEl.textContent = w.detection_count.toLocaleString();

  // Update matches and near-misses from chain results
  const matchesEl = document.getElementById('meta-matches');
  const nearMissesEl = document.getElementById('meta-near-misses');

  if (matchesEl) matchesEl.textContent = '—';
  if (nearMissesEl) nearMissesEl.textContent = '—';

  if (sApp.chainResults) {
    const matches = sApp.chainResults.filter(r => r.type === 'FULL_MATCH').length;
    const nearMisses = sApp.chainResults.filter(r => r.type === 'NEAR_MISS').length;
    if (matchesEl) matchesEl.textContent = matches.toString();
    if (nearMissesEl) nearMissesEl.textContent = nearMisses.toString();
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Boot Sequence
 * ═══════════════════════════════════════════════════════════════════════════════ */

(async function boot() {
  await loadManifest();
  populateWeekPicker();
  renderSessionLegend();

  // Wire direction buttons
  const btnBull = document.getElementById('btn-bull');
  const btnBear = document.getElementById('btn-bear');

  if (btnBull) {
    btnBull.addEventListener('click', () => {
      if (sApp.direction === 'bullish') return;
      sApp.direction = 'bullish';
      btnBull.classList.add('active-bull');
      btnBull.classList.remove('active-bear');
      btnBear.classList.remove('active-bull');
      btnBear.classList.remove('active-bear');
      // Re-render chain and re-evaluate
      if (typeof renderChainBuilder === 'function') renderChainBuilder();
      if (typeof evaluateChain === 'function') evaluateChain();
    });
  }

  if (btnBear) {
    btnBear.addEventListener('click', () => {
      if (sApp.direction === 'bearish') return;
      sApp.direction = 'bearish';
      btnBear.classList.add('active-bear');
      btnBear.classList.remove('active-bull');
      btnBull.classList.remove('active-bull');
      btnBull.classList.remove('active-bear');
      // Re-render chain and re-evaluate
      if (typeof renderChainBuilder === 'function') renderChainBuilder();
      if (typeof evaluateChain === 'function') evaluateChain();
    });
  }

  // Wire add step button
  const addStepBtn = document.getElementById('btn-add-step');
  if (addStepBtn) {
    addStepBtn.addEventListener('click', () => {
      if (typeof addStep === 'function') addStep();
    });
  }

  // Wire template buttons
  const saveBtn = document.getElementById('btn-save-template');
  const loadBtn = document.getElementById('btn-load-template');

  if (saveBtn) {
    saveBtn.addEventListener('click', () => {
      if (typeof saveTemplate === 'function') saveTemplate();
    });
  }

  if (loadBtn) {
    loadBtn.addEventListener('click', () => {
      if (typeof showLoadDialog === 'function') showLoadDialog();
    });
  }

  // Wire export/import strategy buttons
  const exportStrBtn = document.getElementById('btn-export-strategies');
  if (exportStrBtn) {
    exportStrBtn.addEventListener('click', () => {
      if (typeof exportStrategies === 'function') exportStrategies();
    });
  }

  const importStrBtn = document.getElementById('btn-import-strategies');
  if (importStrBtn) {
    importStrBtn.addEventListener('click', () => {
      if (typeof importStrategies === 'function') importStrategies();
    });
  }

  // Wire drill-down close button
  const drillDownClose = document.getElementById('drill-down-close');
  if (drillDownClose) {
    drillDownClose.addEventListener('click', () => {
      if (typeof closeDrillDown === 'function') {
        closeDrillDown();
      } else {
        const panel = document.getElementById('drill-down-panel');
        if (panel) panel.classList.remove('visible');
      }
    });
  }

  // Initial render of gates
  if (typeof renderGates === 'function') renderGates();
})();
