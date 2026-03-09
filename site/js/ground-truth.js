/* ═══════════════════════════════════════════════════════════════════════════════
 * ground-truth.js — Ground Truth Annotation system + Lock Panel
 *
 * GROUND TRUTH ANNOTATION:
 *   Click detection marker on chart → label popover (CORRECT/NOISE/BORDERLINE)
 *   Selecting label updates marker with colored ring, persists to localStorage
 *   Labels scoped per-primitive per-TF, load on refresh
 *   Export Labels button downloads ground_truth_labels.json
 *
 * LOCK PANEL:
 *   Shows lock parameters, comparison summary, WF verdict
 *   Notes text input, Record Lock button (disabled when UNSTABLE)
 *   Lock records persist to localStorage, export to lock_records.json
 * ═══════════════════════════════════════════════════════════════════════════════ */

/* ── Ground Truth State ────────────────────────────────────────────────────── */

let _gtLabels = {};         // Loaded labels keyed by detection_id
let _gtRunId = '';          // Run ID for localStorage key scoping
let _gtPopoverEl = null;    // Current popover DOM element
let _gtInitialized = false; // Initialization flag
let _lockInitialized = false;

/* ── Label Constants ───────────────────────────────────────────────────────── */

const GT_LABEL_OPTIONS = [
  { value: 'CORRECT',     color: '#26a69a', icon: '✓', ring: 'rgba(38,166,154,0.85)' },
  { value: 'NOISE',       color: '#ef5350', icon: '✗', ring: 'rgba(239,83,80,0.85)' },
  { value: 'BORDERLINE',  color: '#f7c548', icon: '?', ring: 'rgba(247,197,72,0.85)' },
];

/* ═══════════════════════════════════════════════════════════════════════════════
 * localStorage Persistence — Ground Truth Labels
 * ═══════════════════════════════════════════════════════════════════════════════ */

function _gtStorageKey() {
  return `gt_labels_${_gtRunId}`;
}

function loadGTLabels() {
  try {
    const raw = localStorage.getItem(_gtStorageKey());
    if (raw) {
      const parsed = JSON.parse(raw);
      if (typeof parsed === 'object' && parsed !== null) {
        _gtLabels = parsed;
        return;
      }
    }
  } catch (e) {
    console.warn('Failed to load ground truth labels from localStorage:', e.message);
  }
  _gtLabels = {};
}

function saveGTLabels() {
  try {
    localStorage.setItem(_gtStorageKey(), JSON.stringify(_gtLabels));
  } catch (e) {
    console.warn('Failed to save ground truth labels to localStorage:', e.message);
  }
}

/**
 * Set a label for a detection.
 * @param {string} detectionId - Detection ID
 * @param {string} primitive - Primitive name
 * @param {string} timeframe - Timeframe (e.g., "5m")
 * @param {string} label - One of CORRECT, NOISE, BORDERLINE
 */
function setGTLabel(detectionId, primitive, timeframe, label) {
  _gtLabels[detectionId] = {
    detection_id: detectionId,
    primitive: primitive,
    timeframe: timeframe,
    label: label,
    labelled_date: new Date().toISOString(),
  };
  saveGTLabels();
}

/**
 * Get the label for a detection, or null if not labeled.
 */
function getGTLabel(detectionId) {
  return _gtLabels[detectionId] || null;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Export Labels
 * ═══════════════════════════════════════════════════════════════════════════════ */

function exportGTLabels() {
  const labels = Object.values(_gtLabels);
  const blob = new Blob([JSON.stringify(labels, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'ground_truth_labels.json';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Marker Visual Update — Colored Rings via Custom Series Primitive
 *
 * Since Lightweight Charts markers don't support rings/borders natively,
 * we use a custom ISeriesPrimitive to draw colored rings around labeled markers.
 * ═══════════════════════════════════════════════════════════════════════════════ */

class GTRingRenderer {
  constructor() { this._rings = []; }
  setData(rings) { this._rings = rings; }
  draw(target) {
    target.useMediaCoordinateSpace(scope => {
      const ctx = scope.context;
      for (const ring of this._rings) {
        if (ring.x == null || ring.y == null) continue;
        // Draw ring circle
        ctx.beginPath();
        ctx.arc(ring.x, ring.y, 8, 0, Math.PI * 2);
        ctx.strokeStyle = ring.color;
        ctx.lineWidth = 2.5;
        ctx.stroke();
        // Inner glow
        ctx.beginPath();
        ctx.arc(ring.x, ring.y, 10, 0, Math.PI * 2);
        ctx.strokeStyle = ring.color.replace('0.85', '0.3');
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    });
  }
}

class GTRingPaneView {
  constructor() { this._renderer = new GTRingRenderer(); }
  renderer() { return this._renderer; }
  zOrder() { return 'top'; }
}

class GTRingPrimitive {
  constructor() {
    this._paneView = new GTRingPaneView();
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;
    this._rawRings = []; // { time, price, color, isBullish }
  }
  attached({ chart, series, requestUpdate }) {
    this._chart = chart;
    this._series = series;
    this._requestUpdate = requestUpdate;
  }
  detached() {
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;
  }
  paneViews() { return [this._paneView]; }
  updateAllViews() {
    if (!this._chart || !this._series) return;
    const ts = this._chart.timeScale();
    const computed = [];
    for (const ring of this._rawRings) {
      const x = ts.timeToCoordinate(ring.time);
      if (x == null) continue;
      // Get price coordinate for the marker position
      const y = this._series.priceToCoordinate(ring.price);
      if (y == null) continue;
      // Offset y based on bullish/bearish positioning
      const yOffset = ring.isBullish ? 12 : -12;
      computed.push({ x, y: y + yOffset, color: ring.color });
    }
    this._paneView._renderer.setData(computed);
  }
  setRings(rings) {
    this._rawRings = rings;
    if (this._requestUpdate) this._requestUpdate();
  }
}

let _gtRingPrimitive = null;

/**
 * Rebuild ring overlays from current labels and markers.
 * Called after labeling, after chart refresh, and on init.
 */
function rebuildGTRings() {
  if (!_gtRingPrimitive || !app.chart || !app.candleSeries) return;

  const rings = [];

  // Iterate over all current markers that have labels
  for (const marker of _allMarkers) {
    const label = getGTLabel(marker._detId);
    if (!label) continue;

    const opt = GT_LABEL_OPTIONS.find(o => o.value === label.label);
    if (!opt) continue;

    // Get the candle data at this time to determine price for ring position
    const isBullish = marker.position === 'belowBar';

    // For price coordinate, we need the low (bullish) or high (bearish) of the candle
    // Use the marker time to find the candle
    let price = null;
    if (_candleTimesArr && _candleTimeSet) {
      // Find the candle data for this time
      const candleData = app.candlesByDay[app.day];
      if (candleData && candleData[app.tf]) {
        const candle = candleData[app.tf].find(c => toTS(c.time) === marker.time);
        if (candle) {
          price = isBullish ? candle.low : candle.high;
        }
      }
    }

    if (price != null) {
      rings.push({
        time: marker.time,
        price: price,
        color: opt.ring,
        isBullish: isBullish,
      });
    }
  }

  _gtRingPrimitive.setRings(rings);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Popover — Label Selection UI
 * ═══════════════════════════════════════════════════════════════════════════════ */

function closeGTPopover() {
  if (_gtPopoverEl) {
    _gtPopoverEl.remove();
    _gtPopoverEl = null;
  }
}

/**
 * Show the label popover near a marker at the given screen coordinates.
 * @param {number} screenX - X position on screen
 * @param {number} screenY - Y position on screen
 * @param {Object} markerInfo - { detId, primitive, config, time }
 */
function showGTPopover(screenX, screenY, markerInfo) {
  closeGTPopover();

  const existingLabel = getGTLabel(markerInfo.detId);

  const popover = document.createElement('div');
  popover.className = 'gt-popover';

  let html = '<div class="gt-popover-title">Label Detection</div>';
  html += '<div class="gt-popover-options">';

  for (const opt of GT_LABEL_OPTIONS) {
    const isActive = existingLabel && existingLabel.label === opt.value;
    html += `<button class="gt-popover-btn${isActive ? ' gt-popover-btn-active' : ''}"
      data-label="${opt.value}"
      style="--btn-color: ${opt.color}">
      <span class="gt-popover-icon" style="color:${opt.color}">${opt.icon}</span>
      <span class="gt-popover-label">${opt.value}</span>
    </button>`;
  }

  html += '</div>';
  popover.innerHTML = html;

  // Position within viewport bounds
  document.body.appendChild(popover);

  // Measure popover size
  const pw = popover.offsetWidth;
  const ph = popover.offsetHeight;
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  let left = screenX - pw / 2;
  let top = screenY - ph - 12; // Above marker by default

  // Clamp horizontal
  if (left < 8) left = 8;
  if (left + pw > vw - 8) left = vw - pw - 8;

  // If too close to top, position below
  if (top < 8) {
    top = screenY + 12;
  }

  // Clamp vertical
  if (top + ph > vh - 8) top = vh - ph - 8;

  popover.style.left = left + 'px';
  popover.style.top = top + 'px';

  _gtPopoverEl = popover;

  // Button click handlers
  popover.querySelectorAll('.gt-popover-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const labelValue = btn.dataset.label;
      setGTLabel(markerInfo.detId, markerInfo.primitive, app.tf, labelValue);
      closeGTPopover();
      rebuildGTRings();
    });
  });

  // Close on outside click (with delay to avoid immediate close)
  setTimeout(() => {
    const handler = (e) => {
      if (_gtPopoverEl && !_gtPopoverEl.contains(e.target)) {
        closeGTPopover();
        document.removeEventListener('mousedown', handler);
      }
    };
    document.addEventListener('mousedown', handler);
  }, 50);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Chart Click → Marker Hit Detection → Popover
 *
 * Uses Lightweight Charts' subscribeCrosshairMove and click events
 * to detect when a user clicks near a marker position.
 * ═══════════════════════════════════════════════════════════════════════════════ */

let _gtClickHandlerAttached = false;

function attachGTClickHandler() {
  if (_gtClickHandlerAttached || !app.chart || !app.candleSeries) return;
  _gtClickHandlerAttached = true;

  const chartContainer = document.getElementById('lw-chart-container');
  if (!chartContainer) return;

  chartContainer.addEventListener('click', (e) => {
    if (!app.chart || !app.candleSeries) return;

    // Get chart container bounds
    const rect = chartContainer.getBoundingClientRect();
    const clickX = e.clientX;
    const clickY = e.clientY;
    const localX = clickX - rect.left;
    const localY = clickY - rect.top;

    // Find the nearest marker within a hit radius
    const hitRadius = 18; // pixels
    let bestMarker = null;
    let bestDist = Infinity;

    const timeScale = app.chart.timeScale();

    for (const marker of _allMarkers) {
      // Check toggle visibility
      if (app.configToggles[marker._config] === false) continue;
      if (app.primitiveToggles[marker._primitive] === false) continue;

      const mx = timeScale.timeToCoordinate(marker.time);
      if (mx == null) continue;

      // Get the price at the bar for positioning
      const candleData = app.candlesByDay[app.day];
      if (!candleData || !candleData[app.tf]) continue;

      const candle = candleData[app.tf].find(c => toTS(c.time) === marker.time);
      if (!candle) continue;

      const isBullish = marker.position === 'belowBar';
      const price = isBullish ? candle.low : candle.high;
      const my = app.candleSeries.priceToCoordinate(price);
      if (my == null) continue;

      // Offset for marker drawing position
      const markerY = isBullish ? my + 10 : my - 10;

      const dist = Math.sqrt((localX - mx) ** 2 + (localY - markerY) ** 2);
      if (dist < hitRadius && dist < bestDist) {
        bestDist = dist;
        bestMarker = marker;
      }
    }

    if (bestMarker) {
      showGTPopover(clickX, clickY, {
        detId: bestMarker._detId,
        primitive: bestMarker._primitive,
        config: bestMarker._config,
        time: bestMarker.time,
      });
    }
  });
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Lock Panel — localStorage persistence
 * ═══════════════════════════════════════════════════════════════════════════════ */

function _lockStorageKey() {
  return `lock_records_${_gtRunId}`;
}

function loadLockRecords() {
  try {
    const raw = localStorage.getItem(_lockStorageKey());
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed;
    }
  } catch (e) {
    console.warn('Failed to load lock records from localStorage:', e.message);
  }
  return [];
}

function saveLockRecords(records) {
  try {
    localStorage.setItem(_lockStorageKey(), JSON.stringify(records));
  } catch (e) {
    console.warn('Failed to save lock records to localStorage:', e.message);
  }
}

function exportLockRecords() {
  const records = loadLockRecords();
  const blob = new Blob([JSON.stringify(records, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'lock_records.json';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Lock Panel — Gather data from app state
 * ═══════════════════════════════════════════════════════════════════════════════ */

/**
 * Get current lock parameters from sweep data or config.
 * Returns an object of param name → value pairs.
 */
function getLockParams() {
  const params = {};

  // Try sweep data current_lock
  if (app.sweepData && app.sweepData.current_lock) {
    const lock = app.sweepData.current_lock;
    const axes = app.sweepData.axes || {};
    if (axes.x && axes.x.param && lock.x != null) {
      params[axes.x.param] = lock.x;
    }
    if (axes.y && axes.y.param && axes.y.param !== '_single' && lock.y != null) {
      params[axes.y.param] = lock.y;
    }
  }

  // Also try per_config params
  if (app.evalData && app.evalData.per_config) {
    for (const cfgName of (app.evalData.configs || [])) {
      const cfg = app.evalData.per_config[cfgName];
      if (cfg && cfg.params && Object.keys(cfg.params).length > 0) {
        for (const [prim, primParams] of Object.entries(cfg.params)) {
          if (typeof primParams === 'object') {
            for (const [k, v] of Object.entries(primParams)) {
              const key = `${prim}.${k}`;
              if (!(key in params)) {
                params[key] = v;
              }
            }
          }
        }
      }
    }
  }

  return params;
}

/**
 * Get comparison summary: config names and agreement rate.
 */
function getComparisonSummary() {
  const result = {
    configNames: [],
    agreementRate: null,
  };

  if (!app.evalData) return result;
  result.configNames = [...(app.evalData.configs || [])];

  // Find pairwise agreement rate
  if (app.evalData.pairwise) {
    const pairKeys = Object.keys(app.evalData.pairwise);
    if (pairKeys.length > 0) {
      const pair = app.evalData.pairwise[pairKeys[0]];
      // Compute average agreement rate across all primitives and TFs
      const pp = pair.per_primitive || {};
      let totalAgreement = 0;
      let count = 0;
      for (const prim of Object.keys(pp)) {
        const primData = pp[prim];
        // Check both per_tf structure and direct TF keys
        for (const key of Object.keys(primData)) {
          const tfData = primData[key];
          if (tfData && typeof tfData === 'object' && tfData.agreement_rate != null) {
            totalAgreement += tfData.agreement_rate;
            count++;
          }
        }
      }
      if (count > 0) {
        result.agreementRate = totalAgreement / count;
      }
    }
  }

  return result;
}

/**
 * Get walk-forward verdict info.
 */
function getWFVerdict() {
  if (!app.walkForwardData || !app.walkForwardData.summary) {
    return { verdict: null, windowsPassed: 0, windowsFailed: 0, windowsTotal: 0 };
  }
  const s = app.walkForwardData.summary;
  return {
    verdict: s.verdict || null,
    windowsPassed: s.windows_passed || 0,
    windowsFailed: s.windows_failed || 0,
    windowsTotal: s.windows_total || 0,
  };
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Lock Panel — Render UI
 * ═══════════════════════════════════════════════════════════════════════════════ */

function renderLockPanel() {
  const container = document.getElementById('lock-panel');
  if (!container) return;

  const lockParams = getLockParams();
  const comparison = getComparisonSummary();
  const wfInfo = getWFVerdict();

  const verdictColors = {
    'STABLE': 'var(--teal)',
    'CONDITIONALLY_STABLE': 'var(--yellow)',
    'UNSTABLE': 'var(--red)',
  };
  const verdictColor = verdictColors[wfInfo.verdict] || 'var(--muted)';
  const verdictText = wfInfo.verdict || 'No walk-forward data';
  const isUnstable = wfInfo.verdict === 'UNSTABLE';

  let html = '';

  // Lock Parameters
  html += '<div class="lock-section">';
  html += '<div class="lock-section-title">Lock Parameters</div>';
  if (Object.keys(lockParams).length === 0) {
    html += '<div class="lock-empty">No lock parameters available</div>';
  } else {
    html += '<div class="lock-params-list">';
    for (const [key, val] of Object.entries(lockParams)) {
      html += `<div class="lock-param-row">
        <span class="lock-param-key">${key}</span>
        <span class="lock-param-val">${val}</span>
      </div>`;
    }
    html += '</div>';
  }
  html += '</div>';

  // Comparison Summary
  html += '<div class="lock-section">';
  html += '<div class="lock-section-title">Comparison Summary</div>';
  if (comparison.configNames.length > 0) {
    html += `<div class="lock-param-row">
      <span class="lock-param-key">Configs</span>
      <span class="lock-param-val">${comparison.configNames.join(', ')}</span>
    </div>`;
  }
  if (comparison.agreementRate != null) {
    html += `<div class="lock-param-row">
      <span class="lock-param-key">Agreement Rate</span>
      <span class="lock-param-val">${(comparison.agreementRate * 100).toFixed(1)}%</span>
    </div>`;
  }
  html += '</div>';

  // Walk-Forward Verdict
  html += '<div class="lock-section">';
  html += '<div class="lock-section-title">Walk-Forward Verdict</div>';
  html += `<div class="lock-verdict-badge" style="color:${verdictColor};border-color:${verdictColor}">
    ${verdictText}
  </div>`;
  if (wfInfo.verdict) {
    html += `<div class="lock-param-row" style="margin-top:6px">
      <span class="lock-param-key">Windows</span>
      <span class="lock-param-val">${wfInfo.windowsPassed} passed / ${wfInfo.windowsFailed} failed</span>
    </div>`;
  }
  html += '</div>';

  // Notes
  html += '<div class="lock-section">';
  html += '<div class="lock-section-title">Notes</div>';
  html += '<textarea id="lock-notes" class="lock-notes-input" placeholder="Optional notes about this lock decision…" rows="3"></textarea>';
  html += '</div>';

  // Buttons
  html += '<div class="lock-buttons">';
  html += `<button id="btn-record-lock" class="lock-btn lock-btn-primary"
    ${isUnstable ? 'disabled title="Cannot lock when walk-forward verdict is UNSTABLE"' : ''}>
    🔒 Record Lock</button>`;
  html += '<button id="btn-export-lock" class="lock-btn lock-btn-secondary">📥 Export Lock Records</button>';
  html += '<button id="btn-export-labels" class="lock-btn lock-btn-secondary">📥 Export Labels</button>';
  html += '</div>';

  container.innerHTML = html;

  // Attach event handlers
  const recordBtn = document.getElementById('btn-record-lock');
  if (recordBtn && !isUnstable) {
    recordBtn.addEventListener('click', () => {
      handleRecordLock();
    });
  }

  const exportLockBtn = document.getElementById('btn-export-lock');
  if (exportLockBtn) {
    exportLockBtn.addEventListener('click', exportLockRecords);
  }

  const exportLabelsBtn = document.getElementById('btn-export-labels');
  if (exportLabelsBtn) {
    exportLabelsBtn.addEventListener('click', exportGTLabels);
  }
}

/**
 * Handle Record Lock: create a lock record with full provenance.
 */
function handleRecordLock() {
  const wfInfo = getWFVerdict();
  const comparison = getComparisonSummary();
  const lockParams = getLockParams();
  const notesEl = document.getElementById('lock-notes');
  const notes = notesEl ? notesEl.value.trim() : '';

  const record = {
    primitive: app.sweepData ? app.sweepData.primitive : 'unknown',
    params_locked: lockParams,
    locked_date: new Date().toISOString(),
    dataset_evaluated: app.evalData ? (app.evalData.dataset || {}).name || '' : '',
    configs_compared: comparison.configNames,
    walk_forward_verdict: wfInfo.verdict || 'N/A',
    walk_forward_windows_passed: wfInfo.windowsPassed,
    walk_forward_windows_failed: wfInfo.windowsFailed,
    notes: notes,
  };

  const records = loadLockRecords();
  records.push(record);
  saveLockRecords(records);

  // Visual feedback
  const btn = document.getElementById('btn-record-lock');
  if (btn) {
    const origText = btn.textContent;
    btn.textContent = '✓ Lock Recorded!';
    btn.style.background = 'var(--teal)';
    btn.style.borderColor = 'var(--teal)';
    btn.style.color = '#fff';
    setTimeout(() => {
      btn.textContent = origText;
      btn.style.background = '';
      btn.style.borderColor = '';
      btn.style.color = '';
    }, 2000);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * initGroundTruth — called after chart is created in chart-tab.js
 * ═══════════════════════════════════════════════════════════════════════════════ */

function initGroundTruth() {
  if (_gtInitialized) return;
  _gtInitialized = true;

  // Set run_id for localStorage scoping
  _gtRunId = (app.evalData && app.evalData.run_id) ? app.evalData.run_id : 'default';

  // Load existing labels
  loadGTLabels();

  // Create and attach ring primitive to the candle series
  if (app.candleSeries) {
    _gtRingPrimitive = new GTRingPrimitive();
    app.candleSeries.attachPrimitive(_gtRingPrimitive);

    // Subscribe to visible range changes to update rings
    if (app.chart) {
      app.chart.timeScale().subscribeVisibleTimeRangeChange(() => {
        if (_gtRingPrimitive && _gtRingPrimitive._requestUpdate) {
          _gtRingPrimitive._requestUpdate();
        }
      });
    }
  }

  // Attach click handler for marker hit detection
  attachGTClickHandler();

  // Rebuild rings for any pre-existing labels
  // Delay slightly to ensure markers are set
  setTimeout(() => rebuildGTRings(), 200);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * initLockPanel — called from initChartTab or switchTab
 * ═══════════════════════════════════════════════════════════════════════════════ */

function initLockPanel() {
  if (_lockInitialized) return;
  _lockInitialized = true;

  // Set run_id for localStorage scoping (same as GT)
  if (!_gtRunId) {
    _gtRunId = (app.evalData && app.evalData.run_id) ? app.evalData.run_id : 'default';
  }

  renderLockPanel();
}
