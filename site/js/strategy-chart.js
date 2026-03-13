/* ═══════════════════════════════════════════════════════════════════════════════
 * strategy-chart.js — Lightweight Charts candlestick chart with detection
 *                     markers, session bands, and chain highlight overlays
 *                     for the Strategy Designer page
 * ═══════════════════════════════════════════════════════════════════════════════ */

/* ── Chart-specific state ──────────────────────────────────────────────────── */

let _sChartCreated = false;
let _sSessionPrimitive = null;
let _sAllMarkers = [];         // All built markers (unfiltered) for current day/tf
let _sCandleTimeSet = null;    // Current candle time set
let _sCandleTimesArr = null;   // Current candle times array
let _sResizeObserver = null;

/* ═══════════════════════════════════════════════════════════════════════════════
 * Session Bands Primitive (ISeriesPrimitive 3-class pattern)
 * ═══════════════════════════════════════════════════════════════════════════════ */

class SSessionBandsRenderer {
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
        // Dashed border lines
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

class SSessionBandsPaneView {
  constructor() { this._renderer = new SSessionBandsRenderer(); }
  renderer() { return this._renderer; }
  zOrder() { return 'bottom'; }
}

class SSessionBandsPrimitive {
  constructor() {
    this._paneView = new SSessionBandsPaneView();
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
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Chart Creation
 * ═══════════════════════════════════════════════════════════════════════════════ */

function createStrategyChart() {
  const container = document.getElementById('chart-container');
  if (!container) return;

  // Clear any existing content (empty state, previous chart)
  container.innerHTML = '';
  _sChartCreated = true;

  const chart = LightweightCharts.createChart(container, {
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
    width: container.clientWidth,
    height: container.clientHeight,
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
  const sessionPrimitive = new SSessionBandsPrimitive();
  candleSeries.attachPrimitive(sessionPrimitive);

  // Subscribe to visible range changes
  chart.timeScale().subscribeVisibleTimeRangeChange(() => {
    if (sessionPrimitive._requestUpdate) sessionPrimitive._requestUpdate();
  });

  // Resize observer for responsive chart
  if (_sResizeObserver) _sResizeObserver.disconnect();
  _sResizeObserver = new ResizeObserver(() => {
    chart.applyOptions({
      width: container.clientWidth,
      height: container.clientHeight,
    });
  });
  _sResizeObserver.observe(container);

  // Store refs
  sApp.chart = chart;
  sApp.candleSeries = candleSeries;
  _sSessionPrimitive = sessionPrimitive;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * initOrRefreshStrategyChart — Called when a week is selected
 * ═══════════════════════════════════════════════════════════════════════════════ */

function initOrRefreshStrategyChart() {
  if (!_sChartCreated) {
    createStrategyChart();
  }
  refreshStrategyChart();
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * refreshStrategyChart — Load candles, markers, session bands for current state
 * ═══════════════════════════════════════════════════════════════════════════════ */

function refreshStrategyChart() {
  if (!sApp.chart || !sApp.candleSeries) return;
  if (!sApp.candleData) {
    sApp.candleSeries.setData([]);
    _sAllMarkers = [];
    rebuildStrategyMarkers();
    if (_sSessionPrimitive) _sSessionPrimitive.setBands([]);
    return;
  }

  // Get candle data for current TF
  const raw = sApp.candleData[sApp.tf];
  if (!raw || !raw.length) {
    sApp.candleSeries.setData([]);
    _sAllMarkers = [];
    rebuildStrategyMarkers();
    if (_sSessionPrimitive) _sSessionPrimitive.setBands([]);
    return;
  }

  // Map candle data — filter by current day
  let candles = raw.map(c => ({
    time: toTS(c.time),
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
    _rawTime: c.time,
  })).filter(b => b.time != null);

  // Filter candles to the selected day
  if (sApp.day) {
    candles = candles.filter(c => {
      // Strip timezone, check date prefix
      const clean = (c._rawTime || '').replace(/[+-]\d{2}:\d{2}$/, '');
      return clean.startsWith(sApp.day);
    });
  }

  candles.sort((a, b) => a.time - b.time);

  // Set candle data (strip the _rawTime helper)
  const chartData = candles.map(c => ({
    time: c.time,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  }));

  sApp.candleSeries.setData(chartData);

  // Build candle time lookup sets
  _sCandleTimeSet = new Set(chartData.map(c => c.time));
  _sCandleTimesArr = chartData.map(c => c.time);

  // Build all markers (filtered by direction)
  _sAllMarkers = buildStrategyMarkers();

  // Apply markers
  rebuildStrategyMarkers();

  // Session bands for current day
  const bands = getStrategySessionBandsForDay(sApp.day);
  if (_sSessionPrimitive) {
    _sSessionPrimitive.setBands(bands);
  }

  // Fit content
  sApp.chart.timeScale().fitContent();

  // Force primitive update after layout settles
  requestAnimationFrame(() => {
    if (_sSessionPrimitive && _sSessionPrimitive._requestUpdate) {
      _sSessionPrimitive._requestUpdate();
    }
    requestAnimationFrame(() => {
      if (_sSessionPrimitive && _sSessionPrimitive._requestUpdate) {
        _sSessionPrimitive._requestUpdate();
      }
    });
  });

  // TODO: Task 6 will implement chain highlight overlay rendering here
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Build Markers from Detection Data (filtered by direction)
 * ═══════════════════════════════════════════════════════════════════════════════ */

function buildStrategyMarkers() {
  if (!sApp.detectionData || !sApp.detectionData.detections_by_primitive) return [];
  if (!_sCandleTimeSet || !_sCandleTimesArr) return [];

  const markers = [];

  for (const [primName, byTf] of Object.entries(sApp.detectionData.detections_by_primitive)) {
    const primColor = sPrimColor(primName);

    // Get detections for current TF (or 'global' for primitives that don't have per-TF data)
    const tfDets = byTf[sApp.tf] || byTf['global'] || [];

    // Filter to current day
    const dayDets = filterStrategyDetectionsByDay(tfDets, sApp.day);

    for (const det of dayDets) {
      const barTime = findStrategyNearestCandleTime(det.time);
      if (barTime == null) continue;

      const isBullish = det.direction === 'bullish' || det.direction === 'high';
      const isBearish = det.direction === 'bearish' || det.direction === 'low';

      // Filter by strategy direction
      if (sApp.direction === 'bullish' && !isBullish) continue;
      if (sApp.direction === 'bearish' && !isBearish) continue;

      markers.push({
        time: barTime,
        position: isBearish ? 'aboveBar' : 'belowBar',
        shape: isBearish ? 'arrowDown' : 'arrowUp',
        color: primColor,
        size: 1,
        text: '',
        _primitive: primName,
        _detId: det.id,
      });
    }
  }

  // Sort by time (required by LWC)
  markers.sort((a, b) => a.time - b.time);

  // Deduplicate same time+position+primitive
  const seen = new Set();
  return markers.filter(m => {
    const k = `${m.time}_${m.position}_${m._primitive}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * rebuildStrategyMarkers — Apply markers to chart
 * ═══════════════════════════════════════════════════════════════════════════════ */

function rebuildStrategyMarkers() {
  if (!sApp.candleSeries) return;

  // Sort by time (required by LWC)
  _sAllMarkers.sort((a, b) => a.time - b.time);

  try {
    sApp.candleSeries.setMarkers(_sAllMarkers);
  } catch (e) {
    console.warn('setMarkers error:', e);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Find Nearest Candle Time for a Detection
 * ═══════════════════════════════════════════════════════════════════════════════ */

function findStrategyNearestCandleTime(detTime) {
  if (!_sCandleTimeSet || !_sCandleTimesArr) return null;

  const ts = toTS(detTime);
  if (ts == null) return null;

  // Exact match
  if (_sCandleTimeSet.has(ts)) return ts;

  // Find nearest candle time (within 15 min for 5m, 1h for 15m)
  const maxDiff = sApp.tf === '5m' ? 900 : 3600;
  let best = null;
  let bestDiff = Infinity;
  for (const ct of _sCandleTimesArr) {
    const diff = Math.abs(ct - ts);
    if (diff < bestDiff) {
      bestDiff = diff;
      best = ct;
    }
  }
  return (bestDiff <= maxDiff) ? best : null;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Detection Filtering by Day
 * ═══════════════════════════════════════════════════════════════════════════════ */

function filterStrategyDetectionsByDay(detections, dayKey) {
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
 * Session Bands for Day
 * ═══════════════════════════════════════════════════════════════════════════════ */

function getStrategySessionBandsForDay(dayKey) {
  if (!sApp.sessionData || !dayKey) return [];
  const VISIBLE_SESSIONS = new Set(['asia', 'lokz', 'nyokz']);
  return sApp.sessionData
    .filter(b => b.forex_day === dayKey && VISIBLE_SESSIONS.has(b.session))
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
 * Primitive Color Lookup
 * ═══════════════════════════════════════════════════════════════════════════════ */

function sPrimColor(key) {
  const p = S_PRIMITIVES.find(x => x.key === key);
  return p ? p.color : '#787b86';
}
