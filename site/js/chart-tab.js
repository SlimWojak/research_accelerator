/* ═══════════════════════════════════════════════════════════════════════════════
 * chart-tab.js — Multi-config candlestick chart with detection markers,
 *                session bands, TF switching, day navigation,
 *                config/primitive toggles, and detection count summary
 * ═══════════════════════════════════════════════════════════════════════════════ */

/* ── Chart-specific state ──────────────────────────────────────────────────── */

let _chartInitialized = false;
let _sessionPrimitive = null;
let _allMarkers = [];       // All built markers (unfiltered) for current day/tf
let _candleTimeSet = null;  // Current candle time set
let _candleTimesArr = null; // Current candle times array

/* ── CONFIG_COLORS for markers (bullish/bearish per config) ────────────────── */

const MARKER_COLORS = CONFIG_COLORS.map(c => ({
  bullish: c.base,
  bearish: c.light,
  bullishDark: c.dark,
  bearishDark: c.base,
}));

/* ═══════════════════════════════════════════════════════════════════════════════
 * Session Bands Primitive (ISeriesPrimitive 3-class pattern)
 * ═══════════════════════════════════════════════════════════════════════════════ */

class SessionBandsRenderer {
  constructor() { this._bands = []; }
  setData(bands) { this._bands = bands; }
  draw(target) {
    target.useMediaCoordinateSpace(scope => {
      const ctx = scope.context;
      const H = scope.mediaSize.height;
      for (const b of this._bands) {
        if (b.x1 == null || b.x2 == null) continue;
        const xL = Math.min(b.x1, b.x2);
        const xR = Math.max(b.x1, b.x2);
        if (xR < 0 || xL > scope.mediaSize.width) continue;
        // Fill
        ctx.fillStyle = b.color;
        ctx.fillRect(xL, 0, xR - xL, H);
        // Border
        ctx.strokeStyle = b.border;
        ctx.setLineDash([3, 3]);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(xL, 0); ctx.lineTo(xL, H);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(xR, 0); ctx.lineTo(xR, H);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    });
  }
}

class SessionBandsPaneView {
  constructor() { this._renderer = new SessionBandsRenderer(); }
  renderer() { return this._renderer; }
  zOrder() { return 'bottom'; }
}

class SessionBandsPrimitive {
  constructor() {
    this._paneView = new SessionBandsPaneView();
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;
    this._rawBands = [];
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
    if (!this._chart) return;
    const ts = this._chart.timeScale();
    const computed = [];
    for (const b of this._rawBands) {
      const x1 = ts.timeToCoordinate(b.startTS);
      const x2 = ts.timeToCoordinate(b.endTS);
      computed.push({ x1, x2, color: b.color, border: b.border });
    }
    this._paneView._renderer.setData(computed);
  }
  setBands(rawBands) {
    this._rawBands = rawBands;
    if (this._requestUpdate) this._requestUpdate();
  }
  injectRefs(chart, series) {
    this._chart = chart;
    this._series = series;
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Detection marker filtering by day
 * ═══════════════════════════════════════════════════════════════════════════════ */

/**
 * Filter detections to those matching the given forex_day.
 * Returns detections whose tags.forex_day or time date prefix matches dayKey.
 */
function filterDetectionsByDay(detections, dayKey) {
  if (!detections || !detections.length) return [];
  return detections.filter(det => {
    // Primary: use tags.forex_day
    const fd = det.tags && det.tags.forex_day;
    if (fd) return fd === dayKey;
    // Fallback: parse date from time string
    const t = det.time || '';
    return t.startsWith(dayKey);
  });
}

/**
 * Find the nearest candle timestamp for a detection time.
 * Returns the bar time (already toTS'd) or null.
 */
function findNearestCandleTime(detTime, candleTimeSet, candleTimes) {
  // Try exact match first (strip timezone suffix if any)
  const cleanTime = detTime.includes('-05:00') ? detTime.replace('-05:00', '') :
                    detTime.includes('+00:00') ? detTime.replace('+00:00', '') : detTime;
  const ts = toTS(cleanTime);
  if (ts != null && candleTimeSet.has(ts)) return ts;
  // Find nearest candle time (within 15 min)
  if (ts == null) return null;
  let best = null;
  let bestDiff = Infinity;
  for (const ct of candleTimes) {
    const diff = Math.abs(ct - ts);
    if (diff < bestDiff) {
      bestDiff = diff;
      best = ct;
    }
  }
  return (bestDiff <= 900) ? best : null; // 15 min max
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Build markers from detection data (unfiltered — all configs/primitives)
 * ═══════════════════════════════════════════════════════════════════════════════ */

function buildMarkers(candleTimesSet, candleTimesArr) {
  if (!app.evalData || !app.evalData.per_config) return [];

  const configs = app.evalData.configs || [];
  const markers = [];

  configs.forEach((configName, ci) => {
    const configData = app.evalData.per_config[configName];
    if (!configData || !configData.per_primitive) return;

    const colorIdx = Math.min(ci, CONFIG_COLORS.length - 1);
    const colors = CONFIG_COLORS[colorIdx];

    for (const prim of PRIMITIVES) {
      const primData = configData.per_primitive[prim];
      if (!primData || !primData.per_tf) continue;

      const tfData = primData.per_tf[app.tf];
      if (!tfData || !tfData.detections) continue;

      const dayDets = filterDetectionsByDay(tfData.detections, app.day);

      for (const det of dayDets) {
        const barTime = findNearestCandleTime(det.time, candleTimesSet, candleTimesArr);
        if (barTime == null) continue;

        const isBullish = det.direction === 'bullish';
        markers.push({
          time: barTime,
          position: isBullish ? 'belowBar' : 'aboveBar',
          shape: isBullish ? 'arrowUp' : 'arrowDown',
          color: isBullish ? colors.base : colors.light,
          size: 1,
          text: '',
          _config: configName,
          _primitive: prim,
          _detId: det.id,
        });
      }
    }
  });

  // Sort by time (required by LWC)
  markers.sort((a, b) => a.time - b.time);

  // Deduplicate: LWC allows multiple markers per time but they stack
  // Keep all but deduplicate same time+position+config+primitive
  const seen = new Set();
  return markers.filter(m => {
    const k = `${m.time}_${m.position}_${m._config}_${m._primitive}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * rebuildMarkers — Filter markers by toggle state and apply to chart
 * ═══════════════════════════════════════════════════════════════════════════════ */

/**
 * Read current toggle state and filter _allMarkers accordingly,
 * then call candleSeries.setMarkers() with the filtered set.
 */
function rebuildMarkers() {
  if (!app.candleSeries) return;

  const filtered = _allMarkers.filter(m => {
    // Check config toggle
    if (app.configToggles[m._config] === false) return false;
    // Check primitive toggle
    if (app.primitiveToggles[m._primitive] === false) return false;
    return true;
  });

  // LWC requires markers sorted by time
  filtered.sort((a, b) => a.time - b.time);

  try {
    app.candleSeries.setMarkers(filtered);
  } catch (e) {
    console.warn('setMarkers error:', e);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Initialize toggle state from eval data
 * ═══════════════════════════════════════════════════════════════════════════════ */

function initToggles() {
  if (!app.evalData) return;

  // Config toggles: all on by default
  const configs = app.evalData.configs || [];
  const ct = {};
  for (const c of configs) {
    ct[c] = true;
  }
  app.configToggles = ct;

  // Primitive toggles: all on by default
  const pt = {};
  for (const p of PRIMITIVES) {
    pt[p] = true;
  }
  app.primitiveToggles = pt;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Config Toggle Controls
 * ═══════════════════════════════════════════════════════════════════════════════ */

function renderConfigToggles(container) {
  if (!app.evalData) return;
  const configs = app.evalData.configs || [];
  container.innerHTML = '';

  const wrapper = document.createElement('div');
  wrapper.className = 'config-toggles';

  const label = document.createElement('span');
  label.className = 'toggle-group-label';
  label.textContent = 'Configs';
  wrapper.appendChild(label);

  configs.forEach((name, i) => {
    const c = CONFIG_COLORS[Math.min(i, CONFIG_COLORS.length - 1)];
    const btn = document.createElement('button');
    const isOn = app.configToggles[name] !== false;
    btn.className = 'toggle-btn config-toggle-btn' + (isOn ? ' active' : '');
    btn.dataset.config = name;
    btn.title = isOn ? `Hide ${name}` : `Show ${name}`;
    btn.innerHTML = `<span class="toggle-swatch" style="background:${isOn ? c.base : 'var(--faint)'}"></span><span class="toggle-label">${name}</span>`;

    btn.addEventListener('click', () => {
      app.configToggles[name] = !app.configToggles[name];
      renderConfigToggles(container);
      rebuildMarkers();
    });
    wrapper.appendChild(btn);
  });

  container.appendChild(wrapper);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Primitive Toggle Controls
 * ═══════════════════════════════════════════════════════════════════════════════ */

function renderPrimitiveToggles(container) {
  container.innerHTML = '';

  const wrapper = document.createElement('div');
  wrapper.className = 'primitive-toggles';

  const label = document.createElement('span');
  label.className = 'toggle-group-label';
  label.textContent = 'Primitives';
  wrapper.appendChild(label);

  for (const prim of PRIMITIVES) {
    const isOn = app.primitiveToggles[prim] !== false;
    const btn = document.createElement('button');
    btn.className = 'toggle-btn prim-toggle-btn' + (isOn ? ' active' : '');
    btn.dataset.primitive = prim;
    btn.title = isOn ? `Hide ${primLabel(prim)}` : `Show ${primLabel(prim)}`;
    btn.textContent = primLabel(prim);

    btn.addEventListener('click', () => {
      app.primitiveToggles[prim] = !app.primitiveToggles[prim];
      renderPrimitiveToggles(container);
      rebuildMarkers();
    });
    wrapper.appendChild(btn);
  }

  container.appendChild(wrapper);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Detection Count Summary Panel
 * ═══════════════════════════════════════════════════════════════════════════════ */

/**
 * Get detection counts for the current TF, per config, per primitive.
 * Returns: { configName: { primitiveName: count } }
 */
function getDetectionCounts() {
  const result = {};
  if (!app.evalData || !app.evalData.per_config) return result;

  const configs = app.evalData.configs || [];
  for (const configName of configs) {
    result[configName] = {};
    const configData = app.evalData.per_config[configName];
    if (!configData || !configData.per_primitive) {
      for (const prim of PRIMITIVES) {
        result[configName][prim] = 0;
      }
      continue;
    }

    for (const prim of PRIMITIVES) {
      const primData = configData.per_primitive[prim];
      if (!primData || !primData.per_tf) {
        result[configName][prim] = 0;
        continue;
      }
      const tfData = primData.per_tf[app.tf];
      if (!tfData) {
        result[configName][prim] = 0;
        continue;
      }
      // Use detection_count from Schema 4B
      result[configName][prim] = tfData.detection_count != null ? tfData.detection_count : 0;
    }
  }
  return result;
}

/**
 * Get detection counts filtered by the current day (from actual detections array).
 * Returns: { configName: { primitiveName: count } }
 */
function getDetectionCountsForDay() {
  const result = {};
  if (!app.evalData || !app.evalData.per_config) return result;

  const configs = app.evalData.configs || [];
  for (const configName of configs) {
    result[configName] = {};
    const configData = app.evalData.per_config[configName];
    if (!configData || !configData.per_primitive) {
      for (const prim of PRIMITIVES) {
        result[configName][prim] = 0;
      }
      continue;
    }

    for (const prim of PRIMITIVES) {
      const primData = configData.per_primitive[prim];
      if (!primData || !primData.per_tf) {
        result[configName][prim] = 0;
        continue;
      }
      const tfData = primData.per_tf[app.tf];
      if (!tfData || !tfData.detections) {
        result[configName][prim] = 0;
        continue;
      }
      const dayDets = filterDetectionsByDay(tfData.detections, app.day);
      result[configName][prim] = dayDets.length;
    }
  }
  return result;
}

function renderDetectionSummary(container) {
  if (!app.evalData) {
    container.innerHTML = '';
    return;
  }

  const configs = app.evalData.configs || [];
  const counts = getDetectionCountsForDay();
  const isSingle = configs.length === 1;

  let html = '<div class="detection-summary">';
  html += '<div class="detection-summary-header">';
  html += `<span class="summary-title">Detections</span>`;
  html += `<span class="summary-meta">${app.tf} · ${dayLabel(app.day)}</span>`;
  html += '</div>';

  // Table header
  html += '<table class="detection-summary-table"><thead><tr>';
  html += '<th class="prim-col">Primitive</th>';
  for (let ci = 0; ci < configs.length; ci++) {
    const c = CONFIG_COLORS[Math.min(ci, CONFIG_COLORS.length - 1)];
    html += `<th class="count-col" style="color:${c.base}">${configs[ci]}</th>`;
  }
  html += '</tr></thead><tbody>';

  for (const prim of PRIMITIVES) {
    html += '<tr>';
    html += `<td class="prim-col">${primLabel(prim)}</td>`;
    for (const cfgName of configs) {
      const cnt = (counts[cfgName] && counts[cfgName][prim] != null) ? counts[cfgName][prim] : 0;
      html += `<td class="count-col">${cnt}</td>`;
    }
    html += '</tr>';
  }

  // Totals row
  html += '<tr class="totals-row">';
  html += '<td class="prim-col">Total</td>';
  for (const cfgName of configs) {
    let total = 0;
    for (const prim of PRIMITIVES) {
      total += (counts[cfgName] && counts[cfgName][prim] != null) ? counts[cfgName][prim] : 0;
    }
    html += `<td class="count-col">${total}</td>`;
  }
  html += '</tr>';

  html += '</tbody></table>';
  html += '</div>';

  container.innerHTML = html;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Session bands rendering
 * ═══════════════════════════════════════════════════════════════════════════════ */

function getSessionBandsForDay(dayKey) {
  if (!app.sessionBoundaries) return [];
  return app.sessionBoundaries
    .filter(b => b.forex_day === dayKey)
    .map(b => ({
      startTS: toTS(b.start_time),
      endTS: toTS(b.end_time),
      color: b.color,
      border: b.border,
      session: b.session,
      label: b.label,
    }))
    .filter(b => b.startTS != null && b.endTS != null);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Session Legend
 * ═══════════════════════════════════════════════════════════════════════════════ */

const SESSION_META = [
  { key: 'asia',  label: 'Asia 19:00–00:00', color: 'rgba(156,39,176,0.5)' },
  { key: 'lokz',  label: 'LOKZ 02:00–05:00', color: 'rgba(41,98,255,0.5)' },
  { key: 'nyokz', label: 'NYOKZ 07:00–10:00', color: 'rgba(38,166,154,0.5)' },
];

function renderSessionLegend(container) {
  let html = '<div class="session-legend">';
  for (const s of SESSION_META) {
    html += `<span class="session-legend-item">
      <span class="session-swatch" style="background:${s.color}"></span>
      <span class="session-label-text">${s.label}</span>
    </span>`;
  }
  html += '</div>';
  container.innerHTML = html;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Config Color Legend
 * ═══════════════════════════════════════════════════════════════════════════════ */

function renderConfigLegend(container) {
  if (!app.evalData) return;
  const configs = app.evalData.configs || [];
  let html = '<div class="config-legend">';
  configs.forEach((name, i) => {
    const c = CONFIG_COLORS[Math.min(i, CONFIG_COLORS.length - 1)];
    html += `<span class="config-legend-item">
      <span class="config-swatch" style="background:${c.base}"></span>
      <span class="config-legend-name">${name}</span>
    </span>`;
  });
  html += '</div>';
  container.innerHTML = html;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Day Navigation Tabs
 * ═══════════════════════════════════════════════════════════════════════════════ */

function renderDayTabs(container) {
  container.innerHTML = '';
  for (const d of DAYS) {
    const btn = document.createElement('button');
    btn.className = 'chart-day-tab' + (d.key === app.day ? ' active' : '');
    btn.textContent = d.label;
    btn.dataset.day = d.key;
    btn.addEventListener('click', () => {
      if (d.key === app.day) return;
      app.day = d.key;
      renderDayTabs(container);
      refreshChart();
    });
    container.appendChild(btn);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * TF Switching Buttons
 * ═══════════════════════════════════════════════════════════════════════════════ */

const TF_OPTIONS = ['1m', '5m', '15m'];

function renderTFButtons(container) {
  container.innerHTML = '';
  for (const tf of TF_OPTIONS) {
    const btn = document.createElement('button');
    btn.className = 'chart-tf-btn' + (tf === app.tf ? ' active' : '');
    btn.textContent = tf;
    btn.dataset.tf = tf;
    btn.addEventListener('click', () => {
      if (tf === app.tf) return;
      app.tf = tf;
      renderTFButtons(container);
      refreshChart();
    });
    container.appendChild(btn);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Chart Creation & Data Rendering
 * ═══════════════════════════════════════════════════════════════════════════════ */

function createLWChart(container) {
  container.innerHTML = '';
  const chart = LightweightCharts.createChart(container, {
    autoSize: true,
    layout: {
      background: { type: 'solid', color: '#131722' },
      textColor: '#d1d4dc',
      fontSize: 11,
      fontFamily: "'IBM Plex Mono', monospace",
    },
    grid: {
      vertLines: { color: '#1e222d' },
      horzLines: { color: '#1e222d' },
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: '#4a4e5a', width: 1, style: 2 },
      horzLine: { color: '#4a4e5a', width: 1, style: 2 },
    },
    rightPriceScale: {
      borderColor: '#2a2e39',
      scaleMargins: { top: 0.05, bottom: 0.05 },
    },
    timeScale: {
      borderColor: '#2a2e39',
      timeVisible: true,
      secondsVisible: false,
      tickMarkFormatter: (time) => {
        const d = new Date(time * 1000);
        const hh = String(d.getUTCHours()).padStart(2, '0');
        const mm = String(d.getUTCMinutes()).padStart(2, '0');
        return `${hh}:${mm}`;
      },
    },
    handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true },
    handleScale: { mouseWheel: true, pinch: true },
  });

  const candleSeries = chart.addCandlestickSeries({
    upColor: '#26a69a',
    downColor: '#ef5350',
    borderUpColor: '#26a69a',
    borderDownColor: '#ef5350',
    wickUpColor: '#26a69a',
    wickDownColor: '#ef5350',
  });

  // Session bands primitive
  const sessionPrimitive = new SessionBandsPrimitive();
  candleSeries.attachPrimitive(sessionPrimitive);

  // Subscribe to visible range changes to update primitives
  chart.timeScale().subscribeVisibleTimeRangeChange(() => {
    if (sessionPrimitive._requestUpdate) sessionPrimitive._requestUpdate();
  });

  return { chart, candleSeries, sessionPrimitive };
}

/**
 * Refresh chart: load candles for current day+tf, set candle data, markers, session bands.
 * Also updates detection count summary and toggle controls.
 */
async function refreshChart() {
  if (!app.chart || !app.candleSeries) return;

  // Load candle data for current day
  const candleData = await loadCandles(app.day);
  if (!candleData || !candleData[app.tf]) {
    app.candleSeries.setData([]);
    _allMarkers = [];
    rebuildMarkers();
    if (_sessionPrimitive) _sessionPrimitive.setBands([]);
    updateDetectionSummary();
    return;
  }

  // Map candle data
  const raw = candleData[app.tf];
  const data = raw.map(c => ({
    time: toTS(c.time),
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  })).filter(b => b.time != null)
    .sort((a, b) => a.time - b.time);

  app.candleSeries.setData(data);

  // Build candle time lookup sets
  _candleTimeSet = new Set(data.map(c => c.time));
  _candleTimesArr = data.map(c => c.time);

  // Build all markers (unfiltered) and store
  _allMarkers = buildMarkers(_candleTimeSet, _candleTimesArr);

  // Apply toggle filters
  rebuildMarkers();

  // Session bands
  const bands = getSessionBandsForDay(app.day);
  if (_sessionPrimitive) {
    _sessionPrimitive.setBands(bands);
  }

  // Fit content
  app.chart.timeScale().fitContent();

  // Force primitive update after layout settles
  requestAnimationFrame(() => {
    if (_sessionPrimitive && _sessionPrimitive._requestUpdate) {
      _sessionPrimitive._requestUpdate();
    }
    requestAnimationFrame(() => {
      if (_sessionPrimitive && _sessionPrimitive._requestUpdate) {
        _sessionPrimitive._requestUpdate();
      }
    });
  });

  // Update detection count summary
  updateDetectionSummary();
}

/**
 * Update the detection count summary panel (called after day/TF change).
 */
function updateDetectionSummary() {
  const summaryEl = document.getElementById('chart-detection-summary');
  if (summaryEl) {
    renderDetectionSummary(summaryEl);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * initChartTab — called by shared.js when Chart tab is activated
 * ═══════════════════════════════════════════════════════════════════════════════ */

function initChartTab() {
  if (_chartInitialized) return;
  _chartInitialized = true;

  const tabEl = document.getElementById('tab-chart');
  if (!tabEl) return;

  // Initialize toggle state
  initToggles();

  // Build chart tab DOM structure with sidebar for controls + summary
  tabEl.innerHTML = `
    <div class="chart-tab-layout">
      <div class="chart-controls-bar">
        <div class="chart-day-tabs" id="chart-day-tabs"></div>
        <div class="chart-tf-group" id="chart-tf-group"></div>
        <div id="chart-session-legend"></div>
      </div>
      <div class="chart-body">
        <div class="chart-sidebar">
          <div class="sidebar-section" id="chart-config-toggles"></div>
          <div class="sidebar-section" id="chart-prim-toggles"></div>
          <div class="sidebar-section" id="chart-detection-summary"></div>
        </div>
        <div class="chart-main-area">
          <div class="chart-container" id="lw-chart-container"></div>
        </div>
      </div>
    </div>
  `;

  // Render controls
  renderDayTabs(document.getElementById('chart-day-tabs'));
  renderTFButtons(document.getElementById('chart-tf-group'));
  renderConfigToggles(document.getElementById('chart-config-toggles'));
  renderPrimitiveToggles(document.getElementById('chart-prim-toggles'));
  renderSessionLegend(document.getElementById('chart-session-legend'));

  // Create chart
  const chartContainer = document.getElementById('lw-chart-container');
  const { chart, candleSeries, sessionPrimitive } = createLWChart(chartContainer);
  app.chart = chart;
  app.candleSeries = candleSeries;
  _sessionPrimitive = sessionPrimitive;

  // Initial data render
  refreshChart();
}
