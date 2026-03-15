/* ═══════════════════════════════════════════════════════════════════════════════
 * chart-tab.js — Multi-config candlestick chart with detection markers,
 *                session bands, TF switching, day navigation,
 *                config/primitive toggles, and detection count summary
 * ═══════════════════════════════════════════════════════════════════════════════ */

/* ── Chart-specific state ──────────────────────────────────────────────────── */

let _chartInitialized = false;
let _sessionPrimitive = null;
let _allMarkers = [];
let _candleTimeSet = null;
let _candleTimesArr = null;
let _cScrollSyncActive = false;

function cWeekRange(weekEntry) {
  if (!weekEntry) return null;
  return { from: toTS(weekEntry.start + 'T00:00:00'), to: toTS(weekEntry.end + 'T23:59:00') };
}

function cDayRange(dayStr) {
  const d = new Date(dayStr + 'T12:00:00Z');
  d.setUTCDate(d.getUTCDate() - 1);
  const prevDate = d.toISOString().split('T')[0];
  return { from: toTS(prevDate + 'T17:00:00'), to: toTS(dayStr + 'T16:59:00') };
}

function scrollCompareToDay(dayStr) {
  if (!app.chart) return;
  _cScrollSyncActive = true;
  if (dayStr) {
    app.chart.timeScale().setVisibleRange(cDayRange(dayStr));
  } else {
    app.chart.timeScale().fitContent();
  }
  setTimeout(() => { _cScrollSyncActive = false; }, 200);
}

function highlightCompareDayTab(dayStr) {
  const container = document.getElementById('chart-day-tabs');
  if (!container) return;
  container.querySelectorAll('.chart-day-tab').forEach(btn => {
    const isAll = btn.textContent === 'All';
    if (dayStr === null) {
      btn.classList.toggle('active', isAll);
    } else {
      btn.classList.toggle('active', btn.dataset.day === dayStr);
    }
  });
}

/** Reset chart tab state so it re-initializes on next activation. */
function resetChartTab() {
  _chartInitialized = false;
  _sessionPrimitive = null;
  _allMarkers = [];
  _candleTimeSet = null;
  _candleTimesArr = null;
  app.chart = null;
  app.candleSeries = null;
}

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
        if (b.x1 == null && b.x2 == null) continue;
        const rawL = b.x1 ?? 0;
        const rawR = b.x2 ?? scope.mediaSize.width;
        const xL = Math.min(rawL, rawR);
        const xR = Math.max(rawL, rawR);
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
  if (!dayKey) return detections; // null/undefined = all days (HTF week view)
  return detections.filter(det => {
    const fd = det.tags && det.tags.forex_day;
    if (fd) return fd === dayKey;
    const t = det.time || '';
    return getForexDay(t) === dayKey;
  });
}

/**
 * Find the nearest candle timestamp for a detection time.
 * Returns the bar time (already toTS'd) or null.
 */
function findNearestCandleTime(detTime, candleTimeSet, candleTimes) {
  // Strip any timezone offset (e.g. -04:00, -05:00, +00:00) to get naive NY time
  const cleanTime = detTime.replace(/[+-]\d{2}:\d{2}$/, '');
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
  // Week mode: build markers from detection data directly
  if (app.weekMode && app.weekData && app.weekData.detectionData) {
    return buildWeekModeMarkers(candleTimesSet, candleTimesArr);
  }

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

      const dayDets = filterDetectionsByDay(tfData.detections, null);

      for (const det of dayDets) {
        if (prim === 'displacement') {
          const grade = det.properties && det.properties.quality_grade;
          if (grade !== 'VALID' && grade !== 'STRONG' && grade !== 'DECISIVE') continue;
        }

        // Only render whitelisted liquidity_sweep types — all others are audit trail
        const detType = det.properties && det.properties.type;
        if (prim === 'liquidity_sweep' && detType !== 'SWEEP' && detType !== 'CONTINUATION') continue;

        // Split liquidity_sweep continuations into their own toggle
        const isContinuation = (prim === 'liquidity_sweep' && detType === 'CONTINUATION');
        const effectivePrim = isContinuation ? 'sweep_continuation' : prim;

        const barTime = findNearestCandleTime(det.time, candleTimesSet, candleTimesArr);
        if (barTime == null) continue;

        const dir = det.direction;
        const pm = PRIMITIVE_MARKERS[effectivePrim];
        let position, shape, markerColor, text;

        if (pm) {
          const isHigh = dir === 'high' || dir === 'bearish';
          position = isHigh ? 'aboveBar' : 'belowBar';
          shape = isHigh ? pm.shape_high : pm.shape_low;
          markerColor = pm.color;
          text = (prim === 'swing_points') ? (dir === 'high' ? 'SWH' : 'SWL')
               : isContinuation ? 'C' : '';
        } else {
          const isBullish = dir === 'bullish' || dir === 'high';
          position = isBullish ? 'belowBar' : 'aboveBar';
          shape = isBullish ? 'arrowUp' : 'arrowDown';
          markerColor = colors.base;
          text = '';
        }

        markers.push({
          time: barTime,
          position,
          shape,
          color: markerColor,
          size: 1,
          text,
          _config: configName,
          _primitive: effectivePrim,
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

/**
 * Build markers from week detection data (detection mode).
 * Uses the flat detections_by_primitive structure instead of Schema 4A per_config.
 */
function buildWeekModeMarkers(candleTimesSet, candleTimesArr) {
  const detData = app.weekData.detectionData;
  if (!detData || !detData.detections_by_primitive) return [];

  const dbp = detData.detections_by_primitive;
  const markers = [];
  const colors = CONFIG_COLORS[0]; // Use primary color palette
  const configName = detData.config || 'locked_a8ra_v1';

  for (const prim of PRIMITIVES) {
    // sweep_continuation is virtual — read from liquidity_sweep
    const dataPrim = (prim === 'sweep_continuation') ? 'liquidity_sweep' : prim;
    const byTf = dbp[dataPrim];
    if (!byTf) continue;

    const tfDets = byTf[app.tf] || [];
    const dayDets = filterDetectionsByDay(tfDets, null);

    for (const det of dayDets) {
      if (prim === 'displacement') {
        const grade = det.properties && det.properties.quality_grade;
        if (grade !== 'VALID' && grade !== 'STRONG' && grade !== 'DECISIVE') continue;
      }

      // Only render whitelisted liquidity_sweep types
      const detType = det.properties && det.properties.type;
      if (prim === 'liquidity_sweep' && detType !== 'SWEEP' && detType !== 'CONTINUATION') continue;

      // Split continuations
      const isContinuation = (prim === 'liquidity_sweep' && detType === 'CONTINUATION');
      if (prim === 'sweep_continuation' && detType !== 'CONTINUATION') continue;
      if (prim === 'liquidity_sweep' && detType === 'CONTINUATION') continue;
      const effectivePrim = isContinuation ? 'sweep_continuation' : prim;

      const barTime = findNearestCandleTime(det.time, candleTimesSet, candleTimesArr);
      if (barTime == null) continue;

      const dir = det.direction;
      const pm = PRIMITIVE_MARKERS[effectivePrim];
      let position, shape, markerColor, text;

      if (pm) {
        const isHigh = dir === 'high' || dir === 'bearish';
        position = isHigh ? 'aboveBar' : 'belowBar';
        shape = isHigh ? pm.shape_high : pm.shape_low;
        markerColor = pm.color;
        text = (dataPrim === 'swing_points') ? (dir === 'high' ? 'SWH' : 'SWL')
             : isContinuation ? 'C' : '';
      } else {
        const isBullish = dir === 'bullish' || dir === 'high';
        position = isBullish ? 'belowBar' : 'aboveBar';
        shape = isBullish ? 'arrowUp' : 'arrowDown';
        markerColor = colors.base;
        text = '';
      }

      markers.push({
        time: barTime,
        position,
        shape,
        color: markerColor,
        size: 1,
        text,
        _config: configName,
        _primitive: effectivePrim,
        _detId: det.id,
      });
    }
  }

  // Sort by time (required by LWC)
  markers.sort((a, b) => a.time - b.time);

  // Deduplicate
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
  // Config toggles: all on by default
  let configs;
  if (app.weekMode && app.weekData && app.weekData.detectionData) {
    const configName = app.weekData.detectionData.config || 'locked_a8ra_v1';
    configs = [configName];
  } else if (app.evalData) {
    configs = app.evalData.configs || [];
  } else {
    return;
  }

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
  let configs;
  if (app.weekMode && app.weekData && app.weekData.detectionData) {
    const configName = app.weekData.detectionData.config || 'locked_a8ra_v1';
    configs = [configName];
  } else if (app.evalData) {
    configs = app.evalData.configs || [];
  } else {
    return;
  }
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

    // Include variant name in label if variant data is available
    const variant = getConfigVariant(name);
    const displayName = variant ? `${name} (${variant})` : name;
    btn.title = isOn ? `Hide ${displayName}` : `Show ${displayName}`;
    btn.innerHTML = `<span class="toggle-swatch" style="background:${isOn ? c.base : 'var(--faint)'}"></span><span class="toggle-label">${displayName}</span>`;

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
    const pm = PRIMITIVE_MARKERS[prim];
    const swatchColor = pm ? pm.color : 'var(--faint)';
    const markerShape = pm ? _markerSymbol(pm.shape_low) : '\u25B2';

    const btn = document.createElement('button');
    btn.className = 'toggle-btn prim-toggle-btn' + (isOn ? ' active' : '');
    btn.dataset.primitive = prim;
    btn.title = isOn ? `Hide ${primLabel(prim)}` : `Show ${primLabel(prim)}`;
    btn.innerHTML = `<span class="toggle-swatch" style="background:${isOn ? swatchColor : 'var(--faint)'}"></span><span class="prim-marker-symbol" style="color:${isOn ? swatchColor : 'var(--faint)'}">${markerShape}</span><span class="toggle-label">${primLabel(prim)}</span>`;

    btn.addEventListener('click', () => {
      app.primitiveToggles[prim] = !app.primitiveToggles[prim];
      renderPrimitiveToggles(container);
      rebuildMarkers();
    });
    wrapper.appendChild(btn);
  }

  container.appendChild(wrapper);
}

function _markerSymbol(shape) {
  const map = {
    'arrowUp': '\u25B2',
    'arrowDown': '\u25BC',
    'square': '\u25A0',
    'circle': '\u25CF',
  };
  return map[shape] || '\u25CF';
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Detection Count Summary Panel
 * ═══════════════════════════════════════════════════════════════════════════════ */

/**
 * Get detection counts filtered by the current day (from actual detections array).
 * Returns: { configName: { primitiveName: count } }
 */
function getDetectionCountsForDay() {
  // Week mode: read from detection data directly
  if (app.weekMode && app.weekData && app.weekData.detectionData) {
    return getWeekModeDetectionCountsForDay();
  }

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
      // sweep_continuation is a virtual primitive — counts from liquidity_sweep CONTINUATION type
      const dataPrim = (prim === 'sweep_continuation') ? 'liquidity_sweep' : prim;
      const primData = configData.per_primitive[dataPrim];
      if (!primData || !primData.per_tf) {
        result[configName][prim] = 0;
        continue;
      }
      const tfData = primData.per_tf[app.tf];
      if (!tfData || !tfData.detections) {
        result[configName][prim] = 0;
        continue;
      }
      let dayDets = filterDetectionsByDay(tfData.detections, app.day);
      if (prim === 'displacement') {
        dayDets = dayDets.filter(det => {
          const g = det.properties && det.properties.quality_grade;
          return g === 'VALID' || g === 'STRONG' || g === 'DECISIVE';
        });
      } else if (prim === 'sweep_continuation') {
        dayDets = dayDets.filter(det => det.properties && det.properties.type === 'CONTINUATION');
      } else if (prim === 'liquidity_sweep') {
        dayDets = dayDets.filter(det => {
          const t = det.properties && det.properties.type;
          return t === 'SWEEP';
        });
      }
      result[configName][prim] = dayDets.length;
    }
  }
  return result;
}

/**
 * Get detection counts for week mode (single config from detection data).
 */
function getWeekModeDetectionCountsForDay() {
  const result = {};
  const detData = app.weekData.detectionData;
  if (!detData || !detData.detections_by_primitive) return result;

  const configName = detData.config || 'locked_a8ra_v1';
  const dbp = detData.detections_by_primitive;
  result[configName] = {};

  for (const prim of PRIMITIVES) {
    const dataPrim = (prim === 'sweep_continuation') ? 'liquidity_sweep' : prim;
    const byTf = dbp[dataPrim];
    if (!byTf) {
      result[configName][prim] = 0;
      continue;
    }
    const tfDets = byTf[app.tf] || [];
    let dayDets = filterDetectionsByDay(tfDets, app.day);
    if (prim === 'displacement') {
      dayDets = dayDets.filter(det => {
        const g = det.properties && det.properties.quality_grade;
        return g === 'VALID' || g === 'STRONG' || g === 'DECISIVE';
      });
    } else if (prim === 'sweep_continuation') {
      dayDets = dayDets.filter(det => det.properties && det.properties.type === 'CONTINUATION');
    } else if (prim === 'liquidity_sweep') {
      dayDets = dayDets.filter(det => {
        const t = det.properties && det.properties.type;
        return t === 'SWEEP';
      });
    }
    result[configName][prim] = dayDets.length;
  }
  return result;
}

function renderDetectionSummary(container) {
  if (!app.evalData && !app.weekMode) {
    container.innerHTML = '';
    return;
  }

  let configs;
  if (app.weekMode && app.weekData && app.weekData.detectionData) {
    const configName = app.weekData.detectionData.config || 'locked_a8ra_v1';
    configs = [configName];
  } else {
    configs = app.evalData.configs || [];
  }
  const counts = getDetectionCountsForDay();

  let html = '<div class="detection-summary">';
  html += '<div class="detection-summary-header">';
  html += `<span class="summary-title">Detections</span>`;
  html += `<span class="summary-meta">${app.tf} · ${app.day ? dayLabel(app.day) : 'All'}</span>`;
  html += '</div>';

  // Table header — include variant name if available
  html += '<table class="detection-summary-table"><thead><tr>';
  html += '<th class="prim-col">Primitive</th>';
  for (let ci = 0; ci < configs.length; ci++) {
    const c = CONFIG_COLORS[Math.min(ci, CONFIG_COLORS.length - 1)];
    const variant = getConfigVariant(configs[ci]);
    const headerLabel = variant ? variant : configs[ci];
    html += `<th class="count-col" style="color:${c.base}" title="${configs[ci]}">${headerLabel}</th>`;
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
  if (app.tf === '4H') return [];
  if (!app.sessionBoundaries) return [];
  const VISIBLE_SESSIONS = new Set(['asia', 'lokz', 'nyokz']);
  const htfAll = !dayKey && isHTF(app.tf);
  return app.sessionBoundaries
    .filter(b => VISIBLE_SESSIONS.has(b.session) && (htfAll || b.forex_day === dayKey))
    .map(b => {
      let color = b.color;
      let border = b.border;
      if (htfAll) {
        color = color.replace(/[\d.]+\)$/, m => (parseFloat(m) * 0.4).toFixed(2) + ')');
        border = border.replace(/[\d.]+\)$/, m => (parseFloat(m) * 0.5).toFixed(2) + ')');
      }
      return {
        startTS: toTS(b.start_time),
        endTS: toTS(b.end_time),
        color,
        border,
        session: b.session,
        label: b.label,
      };
    })
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
 * Day Navigation Tabs
 * ═══════════════════════════════════════════════════════════════════════════════ */

function renderDayTabs(container) {
  container.innerHTML = '';

  if (isHTF(app.tf)) {
    const allBtn = document.createElement('button');
    allBtn.className = 'chart-day-tab' + (app.day === null ? ' active' : '');
    allBtn.textContent = 'All';
    allBtn.addEventListener('click', () => {
      if (app.day === null) return;
      app.day = null;
      renderDayTabs(container);
      scrollCompareToDay(null);
    });
    container.appendChild(allBtn);
  }

  for (const d of DAYS) {
    const btn = document.createElement('button');
    btn.className = 'chart-day-tab' + (d.key === app.day ? ' active' : '');
    btn.textContent = d.label;
    btn.dataset.day = d.key;
    btn.addEventListener('click', () => {
      if (d.key === app.day) return;
      app.day = d.key;
      renderDayTabs(container);
      scrollCompareToDay(d.key);
    });
    container.appendChild(btn);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * TF Switching Buttons
 * ═══════════════════════════════════════════════════════════════════════════════ */

const TF_OPTIONS = ['1m', '5m', '15m', '1H', '4H'];

function renderTFButtons(container) {
  container.innerHTML = '';
  for (const tf of TF_OPTIONS) {
    const btn = document.createElement('button');
    btn.className = 'chart-tf-btn' + (tf === app.tf ? ' active' : '');
    btn.textContent = tf;
    btn.dataset.tf = tf;
    btn.addEventListener('click', () => {
      if (tf === app.tf) return;
      const wasHTF = isHTF(app.tf);
      const nowHTF = isHTF(tf);
      app.tf = tf;

      if (!wasHTF && nowHTF) {
        app.day = null;
      } else if (wasHTF && !nowHTF && !app.day) {
        app.day = DAY_KEYS.length > 0 ? DAY_KEYS[0] : null;
      }

      renderTFButtons(container);
      // Sync page-level TF buttons
      if (typeof renderCompareTFButtons === 'function') renderCompareTFButtons();
      // Re-render day tabs (shows/hides "All" tab)
      const dayTabsEl = document.getElementById('chart-day-tabs');
      if (dayTabsEl) renderDayTabs(dayTabsEl);
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

  // Subscribe to visible range changes
  chart.timeScale().subscribeVisibleTimeRangeChange((range) => {
    if (sessionPrimitive._requestUpdate) sessionPrimitive._requestUpdate();
    // Scroll sync
    if (_cScrollSyncActive || !range || range.from == null || range.to == null) return;
    const center = Math.floor((range.from + range.to) / 2);

    if (isHTF(app.tf) && _cHTFAllWeeksLoaded && app.weekManifest && app.weekManifest.length > 0) {
      for (const w of app.weekManifest) {
        const wStart = toTS(w.start + 'T00:00:00');
        const wEnd = toTS(w.end + 'T23:59:00');
        if (center >= wStart && center <= wEnd && w.week !== (app.currentCompareWeek && app.currentCompareWeek.week)) {
          app.currentCompareWeek = w;
          const picker = document.getElementById('week-picker-compare');
          if (picker) picker.value = w.week;
          break;
        }
      }
      return;
    }

    if (!app.day) return;
    for (const dk of DAY_KEYS) {
      const r = cDayRange(dk);
      if (center >= r.from && center <= r.to && dk !== app.day) {
        app.day = dk;
        highlightCompareDayTab(dk);
        break;
      }
    }
  });

  return { chart, candleSeries, sessionPrimitive };
}

/**
 * Refresh chart: load candles for current day+tf, set candle data, markers, session bands.
 * Also updates detection count summary and toggle controls.
 */
async function refreshChart() {
  if (!app.chart || !app.candleSeries) return;

  let raw;

  if (app.weekMode && app.weekData && app.weekData.candleData) {
    const candleData = app.weekData.candleData;
    if (!candleData || !candleData[app.tf]) {
      app.candleSeries.setData([]);
      _allMarkers = [];
      rebuildMarkers();
      if (_sessionPrimitive) _sessionPrimitive.setBands([]);
      updateDetectionSummary();
      return;
    }
    // Always load ALL candles (continuous timeline)
    raw = candleData[app.tf];
  } else {
    // Fixture mode: always merge candles from all days
    const allBars = [];
    for (const dk of DAY_KEYS) {
      const cd = await loadCandles(dk);
      if (cd && cd[app.tf]) {
        for (const c of cd[app.tf]) allBars.push(c);
      }
    }
    raw = allBars;
  }

  if (!raw || raw.length === 0) {
    app.candleSeries.setData([]);
    _allMarkers = [];
    rebuildMarkers();
    if (_sessionPrimitive) _sessionPrimitive.setBands([]);
    updateDetectionSummary();
    return;
  }

  const data = raw.map(c => ({
    time: toTS(c.time),
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  })).filter(b => b.time != null)
    .sort((a, b) => a.time - b.time);

  app.candleSeries.setData(data);

  _candleTimeSet = new Set(data.map(c => c.time));
  _candleTimesArr = data.map(c => c.time);

  // Build markers for ALL days
  _allMarkers = buildMarkers(_candleTimeSet, _candleTimesArr);
  rebuildMarkers();

  // Session bands for ALL days
  let bands;
  if (app.weekMode && app.weekData && app.weekData.sessionData) {
    bands = getWeekModeSessionBandsForDay(null);
  } else {
    bands = getSessionBandsForDay(null);
  }
  if (_sessionPrimitive) {
    _sessionPrimitive.setBands(bands);
  }

  // Scroll to selected day, or week on HTF, or fit all
  if (app.day) {
    scrollCompareToDay(app.day);
  } else if (isHTF(app.tf) && _cHTFAllWeeksLoaded && app.currentCompareWeek) {
    _cScrollSyncActive = true;
    const wr = cWeekRange(app.currentCompareWeek);
    if (wr) app.chart.timeScale().setVisibleRange(wr);
    setTimeout(() => { _cScrollSyncActive = false; }, 200);
  } else {
    app.chart.timeScale().fitContent();
  }

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

  updateDetectionSummary();

  if (typeof rebuildGTRings === 'function') {
    setTimeout(() => rebuildGTRings(), 100);
  }
}

/**
 * Get session bands for a day in week mode (from weekData.sessionData).
 */
function getWeekModeSessionBandsForDay(dayKey) {
  if (app.tf === '4H') return [];
  if (!app.weekData || !app.weekData.sessionData) return [];
  const VISIBLE_SESSIONS = new Set(['asia', 'lokz', 'nyokz']);
  const htfAll = !dayKey && isHTF(app.tf);
  return app.weekData.sessionData
    .filter(b => VISIBLE_SESSIONS.has(b.session) && (htfAll || b.forex_day === dayKey))
    .map(b => {
      let color = b.color;
      let border = b.border;
      if (htfAll) {
        color = color.replace(/[\d.]+\)$/, m => (parseFloat(m) * 0.4).toFixed(2) + ')');
        border = border.replace(/[\d.]+\)$/, m => (parseFloat(m) * 0.5).toFixed(2) + ')');
      }
      return {
        startTS: toTS(b.start_time),
        endTS: toTS(b.end_time),
        color,
        border,
        session: b.session,
        label: b.label,
      };
    })
    .filter(b => b.startTS != null && b.endTS != null);
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
 * Variant / Fixture Selector Dropdown
 * ═══════════════════════════════════════════════════════════════════════════════ */

/**
 * Render the variant/fixture selector in the sidebar.
 * Shows a dropdown to switch between fixture files (e.g., default vs variant comparison).
 * Also shows available variant names extracted from the current fixture.
 */
function renderVariantSelector(container) {
  if (!container) return;

  // In week mode, show week info instead of fixture selector
  if (app.weekMode && app.currentCompareWeek) {
    container.style.display = '';
    const w = app.currentCompareWeek;
    container.innerHTML = `
      <span class="toggle-group-label">Week Mode</span>
      <div class="variant-info-row" style="color:var(--yellow);">
        <span class="variant-info-label">${w.week} (${w.start} → ${w.end})</span>
      </div>
      <div class="variant-info-row">
        <span class="variant-info-label">${w.detection_count.toLocaleString()} detections</span>
      </div>
    `;
    return;
  }

  const fixtures = typeof getAvailableFixtures === 'function' ? getAvailableFixtures() : [];
  const hasMultipleFixtures = fixtures.length > 1;
  const hasVariants = app.hasVariantData && app.availableVariants.length > 0;

  // Hide section if no variant data and no fixture options
  if (!hasMultipleFixtures && !hasVariants) {
    container.style.display = 'none';
    return;
  }
  container.style.display = '';

  let html = '';

  // Fixture selector dropdown (if multiple fixtures available)
  if (hasMultipleFixtures) {
    html += '<span class="toggle-group-label">Fixture</span>';
    html += '<select id="fixture-select" class="variant-select">';
    for (const f of fixtures) {
      const selected = f.key === (app.activeVariantFixture || 'default') ? ' selected' : '';
      html += `<option value="${f.key}"${selected}>${f.displayLabel || f.label}</option>`;
    }
    html += '</select>';
  }

  // Variant info display
  if (hasVariants) {
    html += '<span class="toggle-group-label" style="margin-top:8px">Variants</span>';
    const configs = app.evalData.configs || [];
    for (let ci = 0; ci < configs.length; ci++) {
      const cfgName = configs[ci];
      const variant = getConfigVariant(cfgName);
      const c = CONFIG_COLORS[Math.min(ci, CONFIG_COLORS.length - 1)];
      if (variant) {
        html += `<div class="variant-info-row">
          <span class="toggle-swatch" style="background:${c.base}"></span>
          <span class="variant-info-label">${variant}</span>
        </div>`;
      }
    }
  }

  container.innerHTML = html;

  // Bind fixture selector change event
  const fixtureSelect = document.getElementById('fixture-select');
  if (fixtureSelect) {
    fixtureSelect.addEventListener('change', async (e) => {
      const key = e.target.value;
      await switchFixture(key);
    });
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Config Legend (in controls bar — maps colors to config/variant names)
 * ═══════════════════════════════════════════════════════════════════════════════ */

/**
 * Render config/variant color legend in the controls bar.
 */
function renderConfigLegend(container) {
  if (!container) return;

  let configs;
  if (app.weekMode && app.weekData && app.weekData.detectionData) {
    const configName = app.weekData.detectionData.config || 'locked_a8ra_v1';
    configs = [configName];
  } else if (app.evalData) {
    configs = app.evalData.configs || [];
  } else {
    container.innerHTML = '';
    return;
  }
  let html = '<div class="config-legend">';
  for (let ci = 0; ci < configs.length; ci++) {
    const cfgName = configs[ci];
    const c = CONFIG_COLORS[Math.min(ci, CONFIG_COLORS.length - 1)];
    const variant = getConfigVariant(cfgName);
    const displayName = variant ? variant : cfgName;
    html += `<span class="config-legend-item">
      <span class="config-swatch" style="background:${c.base}"></span>
      <span class="config-legend-name">${displayName}</span>
    </span>`;
  }
  html += '</div>';
  container.innerHTML = html;
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
        <div id="chart-config-legend"></div>
        <div id="chart-session-legend"></div>
      </div>
      <div class="chart-body">
        <div class="chart-sidebar">
          <div class="sidebar-section" id="chart-variant-selector"></div>
          <div class="sidebar-section" id="chart-config-toggles"></div>
          <div class="sidebar-section" id="chart-prim-toggles"></div>
          <div class="sidebar-section" id="chart-detection-summary"></div>
        </div>
        <div class="chart-main-area">
          <div class="chart-container" id="lw-chart-container"></div>
          <button class="lock-panel-toggle" id="lock-panel-toggle" title="Toggle Lock & Provenance panel">🔒 Lock</button>
        </div>
        <div class="lock-panel-container" id="lock-panel"></div>
        <div class="divergence-panel" id="divergence-panel"></div>
      </div>
    </div>
  `;

  // Render controls
  renderDayTabs(document.getElementById('chart-day-tabs'));
  renderTFButtons(document.getElementById('chart-tf-group'));
  renderVariantSelector(document.getElementById('chart-variant-selector'));
  renderConfigToggles(document.getElementById('chart-config-toggles'));
  renderPrimitiveToggles(document.getElementById('chart-prim-toggles'));
  renderConfigLegend(document.getElementById('chart-config-legend'));
  renderSessionLegend(document.getElementById('chart-session-legend'));

  // Create chart
  const chartContainer = document.getElementById('lw-chart-container');
  const { chart, candleSeries, sessionPrimitive } = createLWChart(chartContainer);
  app.chart = chart;
  app.candleSeries = candleSeries;
  _sessionPrimitive = sessionPrimitive;

  // Initial data render
  refreshChart();

  // Initialize divergence navigator panel
  if (typeof initDivergencePanel === 'function') {
    initDivergencePanel();
  }

  // Initialize ground truth annotation system
  if (typeof initGroundTruth === 'function') {
    initGroundTruth();
  }

  // Initialize lock panel
  if (typeof initLockPanel === 'function') {
    initLockPanel();
  }

  // Lock panel toggle button
  const lockToggleBtn = document.getElementById('lock-panel-toggle');
  const lockPanelEl = document.getElementById('lock-panel');
  if (lockToggleBtn && lockPanelEl) {
    lockToggleBtn.addEventListener('click', () => {
      const isVisible = lockPanelEl.classList.contains('visible');
      lockPanelEl.classList.toggle('visible', !isVisible);
      lockToggleBtn.classList.toggle('active', !isVisible);
      // Resize chart when panel toggles
      if (app.chart) {
        requestAnimationFrame(() => app.chart.resize(0, 0));
        requestAnimationFrame(() => {
          const container = document.getElementById('lw-chart-container');
          if (container && app.chart) {
            app.chart.applyOptions({ autoSize: true });
          }
        });
      }
    });
  }
}
