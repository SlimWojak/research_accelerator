/* ═══════════════════════════════════════════════════════════════════════════════
 * strategy-chart.js — Lightweight Charts candlestick chart with detection
 *                     markers, session bands, and chain highlight overlays
 *                     for the Strategy Designer page
 * ═══════════════════════════════════════════════════════════════════════════════ */

/* ── Chart-specific state ──────────────────────────────────────────────────── */

let _sChartCreated = false;
let _sSessionPrimitive = null;
let _sChainHighlightPrimitive = null;
let _sAllMarkers = [];
let _sCandleTimeSet = null;
let _sCandleTimesArr = null;
let _sResizeObserver = null;
let _sScrollSyncActive = false;

function sWeekRange(weekEntry) {
  if (!weekEntry) return null;
  return { from: toTS(weekEntry.start + 'T00:00:00'), to: toTS(weekEntry.end + 'T23:59:00') };
}

function sDayRange(dayStr) {
  const d = new Date(dayStr + 'T12:00:00Z');
  d.setUTCDate(d.getUTCDate() - 1);
  const prevDate = d.toISOString().split('T')[0];
  return { from: toTS(prevDate + 'T17:00:00'), to: toTS(dayStr + 'T16:59:00') };
}

function scrollStrategyToDay(dayStr) {
  if (!sApp.chart) return;
  _sScrollSyncActive = true;
  if (dayStr) {
    sApp.chart.timeScale().setVisibleRange(sDayRange(dayStr));
  } else {
    sApp.chart.timeScale().fitContent();
  }
  setTimeout(() => { _sScrollSyncActive = false; }, 200);
}

function highlightStrategyDayTab(dayStr) {
  const container = document.getElementById('day-tabs');
  if (!container) return;
  container.querySelectorAll('.day-tab').forEach(btn => {
    const isAll = !btn.dataset.day;
    if (dayStr === null) {
      btn.classList.toggle('active', isAll);
    } else {
      btn.classList.toggle('active', btn.dataset.day === dayStr);
    }
  });
}

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
 * Chain Highlight Primitive (ISeriesPrimitive 3-class pattern)
 * ═══════════════════════════════════════════════════════════════════════════════ */

class SChainHighlightRenderer {
  constructor() { this._bands = []; this._onClick = null; }
  setData(bands) { this._bands = bands; }
  setOnClick(cb) { this._onClick = cb; }
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
        
        // Width must be at least 6px for visibility
        const width = Math.max(xR - xL, 6);
        
        // Fill band
        ctx.fillStyle = b.color; // rgba green or amber
        ctx.fillRect(xL, 0, width, H);
        
        // Left border line
        ctx.strokeStyle = b.border;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(xL, 0); ctx.lineTo(xL, H);
        ctx.stroke();
        
        // Match type label at top
        ctx.font = '10px IBM Plex Mono';
        ctx.fillStyle = b.border;
        ctx.fillText(b.label, xL + 4, 14);
        
        // If selected, draw thicker border
        if (b.selected) {
          ctx.strokeStyle = b.border;
          ctx.lineWidth = 2;
          ctx.strokeRect(xL, 0, width, H);
        }
      }
    });
  }
}

class SChainHighlightPaneView {
  constructor() { this._renderer = new SChainHighlightRenderer(); }
  renderer() { return this._renderer; }
  zOrder() { return 'top'; } // ABOVE candles, below crosshair
}

class SChainHighlightPrimitive {
  constructor() {
    this._paneView = new SChainHighlightPaneView();
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
  detached() { this._chart = null; this._series = null; this._requestUpdate = null; }
  paneViews() { return [this._paneView]; }
  updateAllViews() {
    if (!this._chart) return;
    const ts = this._chart.timeScale();
    const computed = [];
    for (const b of this._rawBands) {
      const x1 = ts.timeToCoordinate(b.startTS);
      // endTS with 1-bar offset for width
      const endTS = b.endTS || b.startTS;
      const barWidthMap = { '5m': 300, '15m': 900, '1H': 3600, '4H': 14400 };
      const barWidth = barWidthMap[sApp.tf] || 900; // Add 1 bar width
      const x2 = ts.timeToCoordinate(endTS + barWidth);
      computed.push({
        x1, x2,
        color: b.type === 'FULL_MATCH' ? 'rgba(38,166,154,0.08)' : 'rgba(247,197,72,0.06)',
        border: b.type === 'FULL_MATCH' ? '#26a69a' : '#f7c548',
        label: b.type === 'FULL_MATCH' ? 'MATCH' : 'NEAR',
        selected: b.selected,
      });
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

  // Chain highlight primitive
  const chainHighlightPrimitive = new SChainHighlightPrimitive();
  candleSeries.attachPrimitive(chainHighlightPrimitive);

  // Subscribe to visible range changes
  chart.timeScale().subscribeVisibleTimeRangeChange((range) => {
    if (sessionPrimitive._requestUpdate) sessionPrimitive._requestUpdate();
    if (chainHighlightPrimitive._requestUpdate) chainHighlightPrimitive._requestUpdate();
    // Scroll sync
    if (_sScrollSyncActive || !range || range.from == null || range.to == null) return;
    const center = Math.floor((range.from + range.to) / 2);

    if (isHTF(sApp.tf) && _sHTFAllWeeksLoaded && sApp.weeks.length > 0) {
      for (const w of sApp.weeks) {
        const wStart = toTS(w.start + 'T00:00:00');
        const wEnd = toTS(w.end + 'T23:59:00');
        if (center >= wStart && center <= wEnd && w.week !== (sApp.currentWeek && sApp.currentWeek.week)) {
          sApp.currentWeek = w;
          const picker = document.getElementById('week-picker');
          if (picker) picker.value = w.week;
          break;
        }
      }
      return;
    }

    if (!sApp.currentWeek || !sApp.day) return;
    const days = sApp.currentWeek.forex_days || [];
    for (const dk of days) {
      const r = sDayRange(dk);
      if (center >= r.from && center <= r.to && dk !== sApp.day) {
        sApp.day = dk;
        highlightStrategyDayTab(dk);
        break;
      }
    }
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
  _sChainHighlightPrimitive = chainHighlightPrimitive;

  // Setup chain match click handler
  setupChainMatchClickHandler();
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

  const raw = sApp.candleData[sApp.tf];
  if (!raw || !raw.length) {
    sApp.candleSeries.setData([]);
    _sAllMarkers = [];
    rebuildStrategyMarkers();
    if (_sSessionPrimitive) _sSessionPrimitive.setBands([]);
    return;
  }

  // Always load ALL candles for the week (continuous timeline)
  const chartData = raw.map(c => ({
    time: toTS(c.time),
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  })).filter(b => b.time != null)
    .sort((a, b) => a.time - b.time);

  sApp.candleSeries.setData(chartData);

  _sCandleTimeSet = new Set(chartData.map(c => c.time));
  _sCandleTimesArr = chartData.map(c => c.time);

  // Build markers for ALL days (filtered by direction only)
  _sAllMarkers = buildStrategyMarkers();
  rebuildStrategyMarkers();

  // Session bands for ALL days
  const bands = getStrategySessionBandsForDay(null);
  if (_sSessionPrimitive) {
    _sSessionPrimitive.setBands(bands);
  }

  // Scroll to selected day, or week on HTF, or fit all
  if (sApp.day) {
    scrollStrategyToDay(sApp.day);
  } else if (isHTF(sApp.tf) && _sHTFAllWeeksLoaded && sApp.currentWeek) {
    _sScrollSyncActive = true;
    const wr = sWeekRange(sApp.currentWeek);
    if (wr) sApp.chart.timeScale().setVisibleRange(wr);
    setTimeout(() => { _sScrollSyncActive = false; }, 200);
  } else {
    sApp.chart.timeScale().fitContent();
  }

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

    const tfDets = byTf[sApp.tf] || byTf['global'] || [];

    for (const det of tfDets) {
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

  // Find nearest candle time (within tolerance per TF)
  const maxDiffMap = { '5m': 900, '15m': 3600, '1H': 7200, '4H': 28800 };
  const maxDiff = maxDiffMap[sApp.tf] || 3600;
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
  if (!detections || !detections.length) return [];
  if (!dayKey) return detections;  // null day = show all (HTF week view)
  return detections.filter(det => {
    // Primary: use properties.forex_day
    const fd = det.properties && det.properties.forex_day;
    if (fd) return fd === dayKey;
    // Fallback: compute forex day from time string
    const t = det.time || '';
    return getForexDay(t) === dayKey;
  });
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Session Bands for Day
 * ═══════════════════════════════════════════════════════════════════════════════ */

function getStrategySessionBandsForDay(dayKey) {
  if (!sApp.sessionData) return [];
  const VISIBLE_SESSIONS = new Set(['asia', 'lokz', 'nyokz']);
  const htf = isHTF(sApp.tf);

  return sApp.sessionData
    .filter(b => VISIBLE_SESSIONS.has(b.session) && (!dayKey || b.forex_day === dayKey))
    .map(b => {
      let color = b.color;
      let border = b.border;
      // Reduce opacity on HTF week view to prevent solid color stacking
      if (htf && !dayKey) {
        color = color.replace(/([\d.]+)\)$/, (_, a) => (parseFloat(a) * 0.4).toFixed(2) + ')');
        border = border.replace(/([\d.]+)\)$/, (_, a) => (parseFloat(a) * 0.5).toFixed(2) + ')');
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
 * Update Chain Overlays (Highlight Bands + Metadata)
 * ═══════════════════════════════════════════════════════════════════════════════ */

function updateChainOverlays() {
  if (!_sChainHighlightPrimitive) return;
  
  if (!sApp.chainResults || sApp.chainResults.length === 0) {
    _sChainHighlightPrimitive.setBands([]);
    // Update metadata
    const matchEl = document.getElementById('meta-matches');
    const nearEl = document.getElementById('meta-near-misses');
    if (matchEl) matchEl.textContent = '0';
    if (nearEl) nearEl.textContent = '0';
    return;
  }
  
  // Filter results to current day if a day is selected
  let results = sApp.chainResults;
  if (sApp.day) {
    results = results.filter(r => r.day === sApp.day);
  }
  
  // Build bands from chain results
  const bands = results.map((r, idx) => ({
    startTS: toTS(r.startTime),
    endTS: toTS(r.endTime),
    type: r.type,
    selected: sApp.selectedMatch === idx,
    matchIdx: idx,
  }));
  
  _sChainHighlightPrimitive.setBands(bands);
  
  // Update metadata counts
  const matchEl = document.getElementById('meta-matches');
  const nearEl = document.getElementById('meta-near-misses');
  const allMatches = sApp.chainResults.filter(r => r.type === 'FULL_MATCH').length;
  const allNears = sApp.chainResults.filter(r => r.type === 'NEAR_MISS').length;
  if (matchEl) matchEl.textContent = allMatches.toString();
  if (nearEl) nearEl.textContent = allNears.toString();
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Click-to-Select Match Handler
 * ═══════════════════════════════════════════════════════════════════════════════ */

function setupChainMatchClickHandler() {
  const container = document.getElementById('chart-container');
  if (!container || container._chainClickHandler) return;
  
  container._chainClickHandler = true;
  container.addEventListener('dblclick', (e) => {
    if (!sApp.chainResults || sApp.chainResults.length === 0) return;
    if (!sApp.chart) return;
    
    // Get the click position in chart coordinates
    const rect = container.getBoundingClientRect();
    const x = e.clientX - rect.left;
    
    // Find which band was clicked (check x coordinate proximity)
    const ts = sApp.chart.timeScale();
    let results = sApp.chainResults;
    if (sApp.day) {
      results = results.filter(r => r.day === sApp.day);
    }
    
    let bestMatch = null;
    let bestDist = Infinity;
    
    for (let i = 0; i < results.length; i++) {
      const r = results[i];
      const startX = ts.timeToCoordinate(toTS(r.startTime));
      const endX = ts.timeToCoordinate(toTS(r.endTime));
      if (startX == null || endX == null) continue;
      
      if (x >= startX - 5 && x <= endX + 5) {
        const dist = Math.abs(x - (startX + endX) / 2);
        if (dist < bestDist) {
          bestDist = dist;
          bestMatch = i;
        }
      }
    }
    
    if (bestMatch !== null) {
      selectChainMatch(bestMatch);
    }
  });
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Select Chain Match + Drill-Down Panel
 * ═══════════════════════════════════════════════════════════════════════════════ */

function selectChainMatch(matchIdx) {
  // Toggle selection
  if (sApp.selectedMatch === matchIdx) {
    sApp.selectedMatch = null;
    closeDrillDown();
  } else {
    sApp.selectedMatch = matchIdx;
    openDrillDown(matchIdx);
  }
  updateChainOverlays();
  // Replace markers with numbered step markers
  updateStepMarkers();
}

function openDrillDown(matchIdx) {
  const panel = document.getElementById('drill-down-panel');
  const content = document.getElementById('drill-down-content');
  if (!panel || !content) return;
  
  let results = sApp.chainResults;
  if (sApp.day) {
    results = results.filter(r => r.day === sApp.day);
  }
  const match = results[matchIdx];
  if (!match) return;
  
  // Build drill-down HTML
  let html = '';
  html += `<div style="padding:12px 16px; border-bottom:1px solid var(--border);">`;
  html += `<div style="font-size:13px; font-weight:600; color:${match.type === 'FULL_MATCH' ? 'var(--teal)' : 'var(--yellow)'};">${match.type === 'FULL_MATCH' ? 'Full Match' : 'Near Miss'}</div>`;
  html += `<div style="font-size:11px; color:var(--muted); margin-top:4px;">Day: ${match.day}</div>`;
  html += `<div style="font-size:11px; color:var(--muted);">Time: ${match.startTime} → ${match.endTime}</div>`;
  html += `</div>`;
  
  for (const ms of match.steps) {
    const prim = S_PRIMITIVES.find(p => p.key === ms.primitive);
    const primLabel = prim ? prim.label : ms.primitive;
    const primColor = prim ? prim.color : '#787b86';
    const passed = ms.passed;
    
    html += `<div style="padding:10px 16px; border-bottom:1px solid var(--border);">`;
    html += `<div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">`;
    html += `<div style="font-family:var(--mono); font-size:11px; font-weight:600; color:var(--blue); background:rgba(41,98,255,0.15); width:22px; height:22px; border-radius:50%; display:flex; align-items:center; justify-content:center;">${ms.step}</div>`;
    html += `<span style="font-size:12px; font-weight:600; color:${primColor};">${primLabel}</span>`;
    html += `<span style="margin-left:auto; font-size:11px; font-weight:600; color:${passed ? 'var(--teal)' : 'var(--red)'};">${passed ? 'PASS' : 'FAIL'}</span>`;
    html += `</div>`;
    
    if (passed && ms.detection) {
      // Show detection details
      html += `<div style="font-size:10px; color:var(--muted); font-family:var(--mono);">`;
      html += `time: ${ms.detection.time}<br>`;
      html += `price: ${ms.detection.price?.toFixed(5) || '—'}<br>`;
      html += `direction: ${ms.detection.direction}<br>`;
      if (ms.detection.tags?.kill_zone) html += `kill_zone: ${ms.detection.tags.kill_zone}<br>`;
      // Show key properties for each primitive type
      const props = ms.detection.properties || {};
      if (ms.primitive === 'liquidity_sweep') {
        if (props.source) html += `source: ${props.source}<br>`;
        if (props.qualified_sweep != null) html += `qualified: ${props.qualified_sweep}<br>`;
      } else if (ms.primitive === 'mss') {
        if (props.break_type) html += `break_type: ${props.break_type}<br>`;
        if (props.displacement?.quality_grade) html += `displacement: ${props.displacement.quality_grade}<br>`;
        if (props.broken_swing) html += `broken_swing: ${JSON.stringify(props.broken_swing)}<br>`;
      } else if (ms.primitive === 'fvg') {
        if (props.top != null) html += `range: ${props.bottom?.toFixed(5)} – ${props.top?.toFixed(5)}<br>`;
        if (props.ce != null) html += `ce: ${props.ce?.toFixed(5)}<br>`;
      } else if (ms.primitive === 'order_block') {
        if (props.zone_body) html += `zone_body: ${JSON.stringify(props.zone_body)}<br>`;
      } else if (ms.primitive === 'ote') {
        if (props.fib_levels) html += `fib_levels: ${JSON.stringify(props.fib_levels)}<br>`;
      }
      html += `</div>`;
    } else if (!passed) {
      html += `<div style="font-size:11px; color:var(--red); font-family:var(--mono);">${ms.failReason || 'No matching detection found'}</div>`;
    }
    
    html += `</div>`;
  }
  
  content.innerHTML = html;
  panel.classList.add('visible');
}

function closeDrillDown() {
  const panel = document.getElementById('drill-down-panel');
  if (panel) panel.classList.remove('visible');
  sApp.selectedMatch = null;
  // Restore normal markers
  _sAllMarkers = buildStrategyMarkers();
  rebuildStrategyMarkers();
  updateChainOverlays();
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Numbered Step Markers
 * ═══════════════════════════════════════════════════════════════════════════════ */

function updateStepMarkers() {
  if (sApp.selectedMatch == null) {
    // Restore normal markers
    _sAllMarkers = buildStrategyMarkers();
    rebuildStrategyMarkers();
    return;
  }
  
  let results = sApp.chainResults;
  if (sApp.day) {
    results = results.filter(r => r.day === sApp.day);
  }
  const match = results[sApp.selectedMatch];
  if (!match) return;
  
  // Build numbered markers for each step
  const stepMarkers = [];
  for (const ms of match.steps) {
    if (!ms.detection) continue;
    const barTime = findStrategyNearestCandleTime(ms.detection.time);
    if (barTime == null) continue;
    
    const prim = S_PRIMITIVES.find(p => p.key === ms.primitive);
    const isBearish = ms.detection.direction === 'bearish' || ms.detection.direction === 'low';
    
    stepMarkers.push({
      time: barTime,
      position: isBearish ? 'aboveBar' : 'belowBar',
      shape: 'circle',
      color: ms.passed ? (prim ? prim.color : '#26a69a') : '#ef5350',
      size: 2,
      text: `${ms.step}`,
      _primitive: ms.primitive,
      _detId: ms.detection.id,
    });
  }
  
  // Keep normal markers but dim them, then overlay step markers
  const dimmed = _sAllMarkers.map(m => ({ ...m, color: '#3a3e49', size: 0.5, text: '' }));
  const combined = [...dimmed, ...stepMarkers].sort((a, b) => a.time - b.time);
  
  try {
    sApp.candleSeries.setMarkers(combined);
  } catch (e) {
    console.warn('setMarkers error:', e);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Primitive Color Lookup
 * ═══════════════════════════════════════════════════════════════════════════════ */

function sPrimColor(key) {
  const p = S_PRIMITIVES.find(x => x.key === key);
  return p ? p.color : '#787b86';
}
