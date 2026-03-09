/* ═══════════════════════════════════════════════════════════════════════════════
 * validate-gt.js — Ground Truth Labeling System (Disk Persistence)
 *
 * Adapted from Mode 1's ground-truth.js pattern but saves to disk via serve.py
 * instead of localStorage.
 *
 * GROUND TRUTH ANNOTATION:
 *   Click detection marker on chart → label popover (CORRECT/NOISE/BORDERLINE)
 *   Selecting label applies colored ring (green/red/yellow) via GTRingPrimitive
 *   Labels POSTed to /api/labels/{week} and written to disk
 *   Labels loaded from disk on page load / week switch
 *   Export button downloads current week's labels as JSON
 *
 * LOCK PANEL:
 *   Shows locked params from params/locked.json
 *   Notes text input, Record Lock button
 *   Lock records POSTed to /api/lock-records/{week} and written to disk
 * ═══════════════════════════════════════════════════════════════════════════════ */

/* ── Ground Truth State ────────────────────────────────────────────────────── */

let _vgtLabels = [];            // Current week's labels array
let _vgtPopoverEl = null;       // Current popover DOM element
let _vgtOutsideClickHandler = null; // Tracked outside-click handler
let _vgtInitialized = false;    // Init guard
let _vgtRingPrimitive = null;   // GTRingPrimitive instance
let _vgtClickHandlerAttached = false;
let _vgtLockParams = null;      // Cached locked params

/* ── Label Constants ───────────────────────────────────────────────────────── */

const VGT_LABEL_OPTIONS = [
  { value: 'CORRECT',    color: '#26a69a', icon: '✓', ring: 'rgba(38,166,154,0.85)' },
  { value: 'NOISE',      color: '#ef5350', icon: '✗', ring: 'rgba(239,83,80,0.85)' },
  { value: 'BORDERLINE', color: '#f7c548', icon: '?', ring: 'rgba(247,197,72,0.85)' },
];

/* ═══════════════════════════════════════════════════════════════════════════════
 * Disk Persistence — Labels
 *
 * Labels are saved per-week to /api/labels/{week} via POST.
 * On load / week switch, fetched from /data/labels/{week}.json (static).
 * ═══════════════════════════════════════════════════════════════════════════════ */

/**
 * Load labels for the current week from disk (via static file serving).
 * Returns the labels array (or empty array if 404).
 */
async function loadVGTLabels() {
  if (!vApp.currentWeek) { _vgtLabels = []; return; }
  const weekId = vApp.currentWeek.week;
  try {
    const resp = await fetch('data/labels/' + weekId + '.json');
    if (resp.ok) {
      const data = await resp.json();
      _vgtLabels = Array.isArray(data) ? data : [];
    } else {
      _vgtLabels = [];
    }
  } catch (_) {
    _vgtLabels = [];
  }
}

/**
 * Save the full labels array to disk via POST.
 */
async function saveVGTLabels() {
  if (!vApp.currentWeek) return;
  const weekId = vApp.currentWeek.week;
  try {
    await fetch('/api/labels/' + weekId, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(_vgtLabels, null, 2),
    });
  } catch (e) {
    console.warn('Failed to save labels to disk:', e.message);
  }
}

/**
 * Set a label for a detection. Updates or adds the label in the array.
 */
function setVGTLabel(detectionId, primitive, timeframe, direction, label) {
  // Find existing label entry
  const idx = _vgtLabels.findIndex(l => l.detection_id === detectionId);
  const forexDay = _getDetForexDay(detectionId);

  const entry = {
    detection_id: detectionId,
    primitive: primitive,
    timeframe: timeframe,
    direction: direction,
    label: label,
    forex_day: forexDay,
    labeled_at: new Date().toISOString(),
  };

  if (idx >= 0) {
    _vgtLabels[idx] = entry;
  } else {
    _vgtLabels.push(entry);
  }

  saveVGTLabels();
}

/**
 * Get the label for a detection, or null.
 */
function getVGTLabel(detectionId) {
  return _vgtLabels.find(l => l.detection_id === detectionId) || null;
}

/**
 * Helper to extract forex_day from a detection by ID.
 */
function _getDetForexDay(detId) {
  if (!vApp.detectionData || !vApp.detectionData.detections_by_primitive) return vApp.day || '';
  for (const [, byTf] of Object.entries(vApp.detectionData.detections_by_primitive)) {
    for (const [, dets] of Object.entries(byTf)) {
      const det = dets.find(d => d.id === detId);
      if (det) return (det.properties && det.properties.forex_day) || vApp.day || '';
    }
  }
  return vApp.day || '';
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Export Labels
 * ═══════════════════════════════════════════════════════════════════════════════ */

function exportVGTLabels() {
  const weekId = vApp.currentWeek ? vApp.currentWeek.week : 'unknown';
  const blob = new Blob([JSON.stringify(_vgtLabels, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'labels_' + weekId + '.json';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * GTRingPrimitive — ISeriesPrimitive 3-class pattern for colored rings
 *
 * Renders colored rings around labeled detection markers:
 *   green = CORRECT, red = NOISE, yellow = BORDERLINE
 * ═══════════════════════════════════════════════════════════════════════════════ */

class VGTRingRenderer {
  constructor() { this._rings = []; }
  setData(rings) { this._rings = rings; }
  draw(target) {
    target.useMediaCoordinateSpace(scope => {
      const ctx = scope.context;
      for (const ring of this._rings) {
        if (ring.x == null || ring.y == null) continue;
        // Outer ring
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

class VGTRingPaneView {
  constructor() { this._renderer = new VGTRingRenderer(); }
  renderer() { return this._renderer; }
  zOrder() { return 'top'; }
}

class VGTRingPrimitive {
  constructor() {
    this._paneView = new VGTRingPaneView();
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;
    this._rawRings = [];
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
      const y = this._series.priceToCoordinate(ring.price);
      if (y == null) continue;
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

/* ═══════════════════════════════════════════════════════════════════════════════
 * Rebuild GT Rings — from labels + current markers
 * ═══════════════════════════════════════════════════════════════════════════════ */

function rebuildVGTRings() {
  if (!_vgtRingPrimitive || !vApp.chart || !vApp.candleSeries) return;

  const rings = [];

  for (const marker of _vAllMarkers) {
    const label = getVGTLabel(marker._detId);
    if (!label) continue;

    const opt = VGT_LABEL_OPTIONS.find(o => o.value === label.label);
    if (!opt) continue;

    // Check toggle visibility
    if (vApp.primitiveToggles[marker._primitive] === false) continue;

    const isBullish = marker.position === 'belowBar';

    // Get the candle price at this time for ring positioning
    let price = null;
    const raw = vApp.candleData && vApp.candleData[vApp.tf];
    if (raw) {
      const candle = raw.find(c => toTS(c.time) === marker.time);
      if (candle) {
        price = isBullish ? candle.low : candle.high;
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

  _vgtRingPrimitive.setRings(rings);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Popover — Label Selection UI
 * ═══════════════════════════════════════════════════════════════════════════════ */

function closeVGTPopover() {
  if (_vgtPopoverEl) {
    _vgtPopoverEl.remove();
    _vgtPopoverEl = null;
  }
  if (_vgtOutsideClickHandler) {
    document.removeEventListener('mousedown', _vgtOutsideClickHandler);
    _vgtOutsideClickHandler = null;
  }
}

function showVGTPopover(screenX, screenY, markerInfo) {
  closeVGTPopover();

  const existingLabel = getVGTLabel(markerInfo.detId);

  const popover = document.createElement('div');
  popover.className = 'vgt-popover';

  let html = '<div class="vgt-popover-title">Label Detection</div>';
  html += '<div class="vgt-popover-options">';

  for (const opt of VGT_LABEL_OPTIONS) {
    const isActive = existingLabel && existingLabel.label === opt.value;
    html += '<button class="vgt-popover-btn' + (isActive ? ' vgt-popover-btn-active' : '') + '"'
      + ' data-label="' + opt.value + '"'
      + ' style="--btn-color: ' + opt.color + '">'
      + '<span class="vgt-popover-icon" style="color:' + opt.color + '">' + opt.icon + '</span>'
      + '<span class="vgt-popover-label">' + opt.value + '</span>'
      + '</button>';
  }

  html += '</div>';
  popover.innerHTML = html;

  // Position within viewport bounds
  document.body.appendChild(popover);

  const pw = popover.offsetWidth;
  const ph = popover.offsetHeight;
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  let left = screenX - pw / 2;
  let top = screenY - ph - 12;

  // Clamp horizontal
  if (left < 8) left = 8;
  if (left + pw > vw - 8) left = vw - pw - 8;

  // If too close to top, show below
  if (top < 8) top = screenY + 12;

  // Clamp vertical
  if (top + ph > vh - 8) top = vh - ph - 8;

  popover.style.left = left + 'px';
  popover.style.top = top + 'px';

  _vgtPopoverEl = popover;

  // Button click handlers
  popover.querySelectorAll('.vgt-popover-btn').forEach(function(btn) {
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      var labelValue = btn.dataset.label;
      setVGTLabel(markerInfo.detId, markerInfo.primitive, vApp.tf, markerInfo.direction, labelValue);
      closeVGTPopover();
      rebuildVGTRings();
      updateLabelCounts();
    });
  });

  // Close on outside click (with delay to avoid immediate close)
  setTimeout(function() {
    _vgtOutsideClickHandler = function(e) {
      if (_vgtPopoverEl && !_vgtPopoverEl.contains(e.target)) {
        closeVGTPopover();
      }
    };
    document.addEventListener('mousedown', _vgtOutsideClickHandler);
  }, 50);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Chart Click → Marker Hit Detection → Popover
 * ═══════════════════════════════════════════════════════════════════════════════ */

function attachVGTClickHandler() {
  if (_vgtClickHandlerAttached || !vApp.chart || !vApp.candleSeries) return;
  _vgtClickHandlerAttached = true;

  const chartContainer = document.getElementById('chart-container');
  if (!chartContainer) return;

  chartContainer.addEventListener('click', function(e) {
    if (!vApp.chart || !vApp.candleSeries) return;

    const rect = chartContainer.getBoundingClientRect();
    var clickX = e.clientX;
    var clickY = e.clientY;
    var localX = clickX - rect.left;
    var localY = clickY - rect.top;

    var hitRadius = 18;
    var bestMarker = null;
    var bestDist = Infinity;

    var timeScale = vApp.chart.timeScale();

    for (var i = 0; i < _vAllMarkers.length; i++) {
      var marker = _vAllMarkers[i];
      // Check toggle visibility
      if (vApp.primitiveToggles[marker._primitive] === false) continue;

      var mx = timeScale.timeToCoordinate(marker.time);
      if (mx == null) continue;

      // Get candle data for price coordinate
      var raw = vApp.candleData && vApp.candleData[vApp.tf];
      if (!raw) continue;
      var candle = raw.find(function(c) { return toTS(c.time) === marker.time; });
      if (!candle) continue;

      var isBullish = marker.position === 'belowBar';
      var price = isBullish ? candle.low : candle.high;
      var my = vApp.candleSeries.priceToCoordinate(price);
      if (my == null) continue;

      var markerY = isBullish ? my + 10 : my - 10;
      var dist = Math.sqrt(Math.pow(localX - mx, 2) + Math.pow(localY - markerY, 2));
      if (dist < hitRadius && dist < bestDist) {
        bestDist = dist;
        bestMarker = marker;
      }
    }

    if (bestMarker) {
      // Determine direction from detection data
      var direction = bestMarker.position === 'belowBar' ? 'bullish' : 'bearish';
      showVGTPopover(clickX, clickY, {
        detId: bestMarker._detId,
        primitive: bestMarker._primitive,
        direction: direction,
        time: bestMarker.time,
      });
    }
  });
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Label Count Summary
 * ═══════════════════════════════════════════════════════════════════════════════ */

function updateLabelCounts() {
  var container = document.getElementById('label-counts');
  if (!container) return;

  var counts = { CORRECT: 0, NOISE: 0, BORDERLINE: 0 };
  for (var i = 0; i < _vgtLabels.length; i++) {
    var lbl = _vgtLabels[i].label;
    if (counts[lbl] !== undefined) counts[lbl]++;
  }

  var total = _vgtLabels.length;
  container.innerHTML =
    '<span class="label-count-item">' +
      '<span style="color:#26a69a">✓ ' + counts.CORRECT + '</span>' +
    '</span>' +
    '<span class="label-count-item">' +
      '<span style="color:#ef5350">✗ ' + counts.NOISE + '</span>' +
    '</span>' +
    '<span class="label-count-item">' +
      '<span style="color:#f7c548">? ' + counts.BORDERLINE + '</span>' +
    '</span>' +
    '<span class="label-count-item">' +
      '<span style="color:var(--muted)">Total: ' + total + '</span>' +
    '</span>';
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Lock Panel — Shows locked params, notes, record lock
 * ═══════════════════════════════════════════════════════════════════════════════ */

async function loadLockParams() {
  try {
    var resp = await fetch('data/params/locked.json');
    if (resp.ok) {
      _vgtLockParams = await resp.json();
    } else {
      _vgtLockParams = null;
    }
  } catch (_) {
    _vgtLockParams = null;
  }
}

/**
 * Render a value as a compact string for lock panel display.
 */
function _formatLockVal(val) {
  if (val === null || val === undefined) return '—';
  if (typeof val === 'boolean') return val ? 'true' : 'false';
  if (typeof val === 'number') return String(val);
  if (typeof val === 'string') return val;
  if (Array.isArray(val)) return val.join(', ');
  if (typeof val === 'object') return JSON.stringify(val);
  return String(val);
}

/**
 * Recursively render params as flat key-value rows.
 */
function _renderParamRows(obj, prefix) {
  var html = '';
  for (var key in obj) {
    var val = obj[key];
    var fullKey = prefix ? prefix + '.' + key : key;
    if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
      // Recurse into nested objects
      html += _renderParamRows(val, fullKey);
    } else {
      html += '<div class="vlock-param-row">'
        + '<span class="vlock-param-key">' + fullKey + '</span>'
        + '<span class="vlock-param-val">' + _formatLockVal(val) + '</span>'
        + '</div>';
    }
  }
  return html;
}

function renderLockPanel() {
  var container = document.getElementById('lock-panel-content');
  if (!container) return;

  var html = '';

  // Lock Parameters
  html += '<div class="vlock-section">';
  html += '<div class="vlock-section-title">Locked Parameters</div>';

  if (!_vgtLockParams || Object.keys(_vgtLockParams).length === 0) {
    html += '<div class="vlock-empty">No locked params available</div>';
  } else {
    html += '<div class="vlock-params-list">';

    // Render top-level non-primitives first
    for (var key in _vgtLockParams) {
      if (key === 'primitives') continue;
      var val = _vgtLockParams[key];
      if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
        html += '<div class="vlock-param-group">' + key + '</div>';
        html += _renderParamRows(val, '');
      } else {
        html += '<div class="vlock-param-row">'
          + '<span class="vlock-param-key">' + key + '</span>'
          + '<span class="vlock-param-val">' + _formatLockVal(val) + '</span>'
          + '</div>';
      }
    }

    // Render primitives section with grouping
    if (_vgtLockParams.primitives) {
      for (var primName in _vgtLockParams.primitives) {
        html += '<div class="vlock-param-group">' + primName + '</div>';
        html += _renderParamRows(_vgtLockParams.primitives[primName], '');
      }
    }

    html += '</div>';
  }
  html += '</div>';

  // Notes
  html += '<div class="vlock-section">';
  html += '<div class="vlock-section-title">Notes</div>';
  html += '<textarea id="vlock-notes" class="vlock-notes-input" placeholder="Optional notes about this lock decision…" rows="3"></textarea>';
  html += '</div>';

  // Buttons
  html += '<div class="vlock-buttons">';
  html += '<button id="btn-vrecord-lock" class="vlock-btn vlock-btn-primary">🔒 Record Lock</button>';
  html += '<button id="btn-vexport-labels" class="vlock-btn vlock-btn-secondary">📥 Export Labels</button>';
  html += '</div>';

  container.innerHTML = html;

  // Attach event handlers
  var recordBtn = document.getElementById('btn-vrecord-lock');
  if (recordBtn) {
    recordBtn.addEventListener('click', handleVRecordLock);
  }

  var exportLabelsBtn = document.getElementById('btn-vexport-labels');
  if (exportLabelsBtn) {
    exportLabelsBtn.addEventListener('click', exportVGTLabels);
  }
}

async function handleVRecordLock() {
  if (!vApp.currentWeek) return;

  var notesEl = document.getElementById('vlock-notes');
  var notes = notesEl ? notesEl.value.trim() : '';

  var record = {
    week: vApp.currentWeek.week,
    params: _vgtLockParams || {},
    notes: notes,
    recorded_at: new Date().toISOString(),
  };

  var weekId = vApp.currentWeek.week;
  try {
    var resp = await fetch('/api/lock-records/' + weekId, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(record, null, 2),
    });
    if (resp.ok) {
      // Visual feedback
      var btn = document.getElementById('btn-vrecord-lock');
      if (btn) {
        var origText = btn.textContent;
        btn.textContent = '✓ Lock Recorded!';
        btn.style.background = 'var(--teal)';
        btn.style.borderColor = 'var(--teal)';
        btn.style.color = '#fff';
        setTimeout(function() {
          btn.textContent = origText;
          btn.style.background = '';
          btn.style.borderColor = '';
          btn.style.color = '';
        }, 2000);
      }
    }
  } catch (e) {
    console.warn('Failed to save lock record:', e.message);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Lock Panel Toggle
 * ═══════════════════════════════════════════════════════════════════════════════ */

function toggleLockPanel() {
  var panel = document.getElementById('lock-panel');
  if (!panel) return;
  var isVisible = panel.classList.contains('visible');
  if (isVisible) {
    panel.classList.remove('visible');
  } else {
    panel.classList.add('visible');
    renderLockPanel();
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * initValidateGT — called after chart is created
 * ═══════════════════════════════════════════════════════════════════════════════ */

async function initValidateGT() {
  if (_vgtInitialized) return;
  _vgtInitialized = true;

  // Load lock params
  await loadLockParams();

  // Create and attach ring primitive
  if (vApp.candleSeries) {
    _vgtRingPrimitive = new VGTRingPrimitive();
    vApp.candleSeries.attachPrimitive(_vgtRingPrimitive);

    // Subscribe to visible range changes to update ring positions
    if (vApp.chart) {
      vApp.chart.timeScale().subscribeVisibleTimeRangeChange(function() {
        if (_vgtRingPrimitive && _vgtRingPrimitive._requestUpdate) {
          _vgtRingPrimitive._requestUpdate();
        }
      });
    }
  }

  // Attach click handler
  attachVGTClickHandler();

  // Load labels from disk
  await loadVGTLabels();

  // Rebuild rings for loaded labels
  setTimeout(function() { rebuildVGTRings(); updateLabelCounts(); }, 200);
}

/**
 * Called when week changes — reload labels from disk and rebuild rings.
 */
async function onVGTWeekChange() {
  await loadVGTLabels();
  setTimeout(function() { rebuildVGTRings(); updateLabelCounts(); }, 200);
}

/**
 * Reset GT state for clean re-init (when chart is recreated).
 */
function resetValidateGT() {
  _vgtInitialized = false;
  _vgtClickHandlerAttached = false;
  _vgtRingPrimitive = null;
  closeVGTPopover();
}
