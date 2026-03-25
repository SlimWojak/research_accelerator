/* ═══════════════════════════════════════════════════════════════════════════════
 * mirror-chart.js — Lightweight Charts candlestick chart with detection
 *                   markers, session bands, signal overlays, and live bar
 *                   updates for the MIRROR live trading dashboard
 * ═══════════════════════════════════════════════════════════════════════════════
 *
 * TIMEZONE CONTRACT (critical — read before modifying time handling):
 * ─────────────────────────────────────────────────────────────────────
 * All timestamps in this file operate in "NY time space" for chart display.
 * Different data sources arrive in different timezones but converge:
 *
 * ┌─────────────────────┬────────────────┬──────────────────────────────┐
 * │ Source               │ Format         │ Frontend conversion          │
 * ├─────────────────────┼────────────────┼──────────────────────────────┤
 * │ Bar times (backend)  │ UTC ISO string │ toNYTS() = toTS() + offset  │
 * │ Session times (BE)   │ UTC ISO string │ toNYTS() = toTS() + offset  │
 * │ Detection times (Dx) │ NY-local ISO*  │ toTS() only (already NY)    │
 * └─────────────────────┴────────────────┴──────────────────────────────┘
 *
 * (*) Dexter producers write bar_time from tf_aggregator which operates in
 *     NY time space. Detection timestamps are NY-local WITHOUT timezone
 *     suffix. This means toTS() (which parses as UTC) produces the SAME
 *     epoch as toNYTS() on a true UTC string — "two wrongs make a right".
 *
 * IMPORTANT: Never apply toNYTS() to detection timestamps — it would
 * double-shift by _nyOffset. If Dexter ever changes to emit UTC detection
 * times, findMirrorNearestCandleTime() must be updated to use toNYTS().
 *
 * The chart uses SEQUENTIAL timestamps (gap-free, adjacent bars) mapped
 * via _mSeqToReal / _mRealToSeq. All chart navigation (setVisibleRange,
 * day tabs, feed clicks) must use sequential timestamps, not real ones.
 *
 * ═══════════════════════════════════════════════════════════════════════════ */

/* ── Per-Primitive Marker Styles (unified across tools) ─────────────────── */

const M_MARKER_STYLES = {
  swing_point:         { shape_high: 'arrowDown', shape_low: 'arrowUp',  color: '#00e5ff' },
  liquidity_sweep:     { shape_high: 'arrowDown', shape_low: 'arrowUp',  color: '#ff9800' },
  mss:                 { shape_high: 'arrowDown', shape_low: 'arrowUp',  color: '#ffeb3b' },
  displacement:        { shape_high: 'square',    shape_low: 'square',   color: '#e040fb' },
  order_block:         { shape_high: 'square',    shape_low: 'square',   color: '#448aff' },
  fvg:                 { shape_high: 'circle',    shape_low: 'circle',   color: '#69f0ae' },
  ote:                 { shape_high: 'circle',    shape_low: 'circle',   color: '#ffb74d' },
  asia_range:          { shape_high: 'square',    shape_low: 'square',   color: '#e91e63' },
  htf_liquidity:       { shape_high: 'arrowDown', shape_low: 'arrowUp',  color: '#8bc34a' },
  session_liquidity:   { shape_high: 'square',    shape_low: 'square',   color: '#795548' },
  reference_levels:    { shape_high: 'circle',    shape_low: 'circle',   color: '#607d8b' },
  diagnostic_signal:   { shape_high: 'square',    shape_low: 'square',   color: '#ffd700' },
};

/* ── Chart-specific state ──────────────────────────────────────────────────── */

let _mChartCreated = false;
let _mSessionPrimitive = null;
let _mAllMarkers = [];
let _mCandleTimeSet = null;
let _mCandleTimesArr = null;
let _mResizeObserver = null;
let _mSeqToReal = {};    // sequential timestamp → real timestamp mapping
let _mRealToSeq = {};    // real timestamp → sequential timestamp mapping
let _mMultiDay = false;  // true when displaying multi-day data

/* ═══════════════════════════════════════════════════════════════════════════════
 * Session Bands Primitive (ISeriesPrimitive 3-class pattern)
 * ═══════════════════════════════════════════════════════════════════════════════ */

class MSessionBandsRenderer {
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

class MSessionBandsPaneView {
  constructor() { this._renderer = new MSessionBandsRenderer(); }
  renderer() { return this._renderer; }
  zOrder() { return 'bottom'; }
}

class MSessionBandsPrimitive {
  constructor() {
    this._paneView = new MSessionBandsPaneView();
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

function createMirrorChart() {
  if (_mChartCreated) return;

  const container = document.getElementById('chart-container');
  if (!container) return;

  // Clear any existing content (empty state, previous chart)
  container.innerHTML = '';
  _mChartCreated = true;

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
      horzLine: { color: '#4a4e5a', width: 1, style: 2, labelVisible: true },
    },
    rightPriceScale: {
      borderColor: '#2a2e39',
      scaleMargins: { top: 0.05, bottom: 0.05 },
    },
    timeScale: {
      borderColor: '#2a2e39',
      timeVisible: true,
      secondsVisible: false,
      minBarSpacing: 3,
      tickMarkFormatter: (time) => {
        // Data is in NY time space — UTC formatting gives NY times
        var real = _mSeqToReal ? _mSeqToReal[time] : time;
        var d = new Date(real * 1000);
        var hh = String(d.getUTCHours()).padStart(2, '0');
        var mm = String(d.getUTCMinutes()).padStart(2, '0');
        if (_mMultiDay) {
          var dd = String(d.getUTCDate()).padStart(2, '0');
          var mon = String(d.getUTCMonth() + 1).padStart(2, '0');
          return mon + '/' + dd + ' ' + hh + ':' + mm;
        }
        return hh + ':' + mm;
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
    priceFormat: { type: 'price', precision: 5, minMove: 0.00001 },
  });

  // Session bands primitive
  const sessionPrimitive = new MSessionBandsPrimitive();
  candleSeries.attachPrimitive(sessionPrimitive);

  // Subscribe to visible range changes for day sync
  chart.timeScale().subscribeVisibleTimeRangeChange((range) => {
    if (sessionPrimitive._requestUpdate) sessionPrimitive._requestUpdate();
    if (!range || range.from == null || range.to == null) return;
    if (typeof mApp === 'undefined') return;

    const center = Math.floor((range.from + range.to) / 2);

    // Day-level scroll sync — update active day tab as user scrolls
    if (mApp.forexDays && mApp.forexDays.length > 0 && mApp.day) {
      for (const dk of mApp.forexDays) {
        const r = _mDayRange(dk);
        if (center >= r.from && center <= r.to && dk !== mApp.day) {
          if (typeof setView === 'function') {
            setView({ day: dk });
          } else {
            mApp.day = dk;
            if (typeof renderDayTabs === 'function') renderDayTabs();
          }
          break;
        }
      }
    }
  });

  // Crosshair tooltip for primitive markers (hover — not click)
  chart.subscribeCrosshairMove((param) => {
    _handleCrosshairTooltip(param, container);
  });

  // Resize observer for responsive chart
  if (_mResizeObserver) _mResizeObserver.disconnect();
  _mResizeObserver = new ResizeObserver(() => {
    chart.applyOptions({
      width: container.clientWidth,
      height: container.clientHeight,
    });
  });
  _mResizeObserver.observe(container);

  // Store refs
  if (typeof mApp !== 'undefined') {
    mApp.chart = chart;
    mApp.candleSeries = candleSeries;
  }
  _mSessionPrimitive = sessionPrimitive;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Day Range Helper
 * ═══════════════════════════════════════════════════════════════════════════════ */

/** Map a real timestamp to the nearest sequential timestamp (snap to nearest bar).
 * Session bands use this to align with candle positions on the chart.
 * Snap error is at most half a bar width (acceptable on LTF; HTF hides bands). */
function _findNearestSeqTime(realTS) {
  if (!realTS || !_mCandleTimesArr || _mCandleTimesArr.length === 0) return null;
  if (_mRealToSeq[realTS] != null) return _mRealToSeq[realTS];

  // Binary search for nearest bar (array is sorted by real time)
  var lo = 0, hi = _mCandleTimesArr.length - 1;
  while (lo < hi) {
    var mid = (lo + hi) >> 1;
    if (_mCandleTimesArr[mid] < realTS) lo = mid + 1;
    else hi = mid;
  }
  // Check lo and lo-1 for closest
  var best = _mCandleTimesArr[lo];
  var bestDiff = Math.abs(best - realTS);
  if (lo > 0) {
    var altDiff = Math.abs(_mCandleTimesArr[lo - 1] - realTS);
    if (altDiff < bestDiff) { best = _mCandleTimesArr[lo - 1]; bestDiff = altDiff; }
  }

  // Max tolerance: 2 bar intervals (prevents cross-day mismatches)
  var tfLower = (typeof mApp !== 'undefined' ? mApp.tf : '1H').toLowerCase();
  var barSec = tfLower === '1d' ? 86400 : tfLower === '4h' ? 14400 : tfLower === '1h' ? 3600
             : tfLower === '15m' ? 900 : tfLower === '5m' ? 300 : 60;
  if (bestDiff > barSec * 2) return null;

  return _mRealToSeq[best] != null ? _mRealToSeq[best] : null;
}

function _mDayRange(dayStr) {
  // Forex day runs 17:00 NY (prev calendar day) → 16:59 NY (forex day).
  // Returns sequential timestamps for LWC chart navigation.
  const d = new Date(dayStr + 'T12:00:00Z');
  d.setUTCDate(d.getUTCDate() - 1);
  const prevDate = d.toISOString().split('T')[0];

  // Compute real NY-space timestamps (same domain as _mCandleTimesArr)
  const realFrom = toTS(prevDate + 'T17:00:00');
  const realTo = toTS(dayStr + 'T16:59:00');

  // Convert to sequential timestamps for chart axis
  const seqFrom = _findNearestSeqTime(realFrom);
  const seqTo = _findNearestSeqTime(realTo);

  // Fallback: if no seq mapping available yet, use real timestamps
  // (chart hasn't rendered — these won't be used for navigation)
  return {
    from: seqFrom != null ? seqFrom : realFrom,
    to: seqTo != null ? seqTo : realTo,
  };
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * refreshMirrorChart — Load candles, markers, session bands for current state
 * ═══════════════════════════════════════════════════════════════════════════════ */

function refreshMirrorChart() {
  if (typeof mApp === 'undefined') return;

  // Guard: skip render while setView() is still fetching data
  if (typeof viewState !== 'undefined' && viewState.loading) return;

  if (!mApp.chart || !mApp.candleSeries) {
    createMirrorChart();
  }
  if (!mApp.chart || !mApp.candleSeries) return;

  if (!mApp.candleData) {
    mApp.candleSeries.setData([]);
    _mAllMarkers = [];
    rebuildMirrorMarkers();
    if (_mSessionPrimitive) _mSessionPrimitive.setBands([]);
    return;
  }

  const raw = mApp.candleData[mApp.tf];
  if (!raw || !raw.length) {
    mApp.candleSeries.setData([]);
    _mAllMarkers = [];
    rebuildMirrorMarkers();
    if (_mSessionPrimitive) _mSessionPrimitive.setBands([]);
    return;
  }

  // Compute NY offset from first bar (DST-aware, sets global _nyOffset)
  var firstBarTS = null;
  for (var ri = 0; ri < raw.length; ri++) {
    firstBarTS = toTS(raw[ri].time);
    if (firstBarTS != null) { computeNYOffset(firstBarTS); break; }
  }

  // Convert to LC format, shift UTC → NY time space, sort
  const rawBars = raw.map(c => ({
    realTime: toNYTS(c.time),
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  })).filter(b => b.realTime != null)
    .sort((a, b) => a.realTime - b.realTime);

  // Build sequential time mapping (eliminates gaps — candles render adjacently like TradingView)
  // Determine appropriate spacing per TF
  var seqSpacing = 60; // 1m default
  var tfLower = mApp.tf.toLowerCase();
  if (tfLower === '5m') seqSpacing = 300;
  else if (tfLower === '15m') seqSpacing = 900;
  else if (tfLower === '1h') seqSpacing = 3600;
  else if (tfLower === '4h') seqSpacing = 14400;
  else if (tfLower === '1d') seqSpacing = 86400;

  _mSeqToReal = {};
  _mRealToSeq = {};
  // Use the first bar's real time as the base, then increment sequentially
  var seqBase = rawBars.length > 0 ? rawBars[0].realTime : 0;
  const chartData = rawBars.map((b, i) => {
    var seqTime = seqBase + (i * seqSpacing);
    _mSeqToReal[seqTime] = b.realTime;
    _mRealToSeq[b.realTime] = seqTime;
    return {
      time: seqTime,
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
    };
  });

  // Detect multi-day data for tick label formatting
  if (rawBars.length > 1) {
    var firstDay = new Date(rawBars[0].realTime * 1000).getUTCDate();
    var lastDay = new Date(rawBars[rawBars.length - 1].realTime * 1000).getUTCDate();
    _mMultiDay = (firstDay !== lastDay);
  } else {
    _mMultiDay = false;
  }

  mApp.candleSeries.setData(chartData);

  // Track candle times using REAL timestamps (for marker matching)
  _mCandleTimeSet = new Set(rawBars.map(c => c.realTime));
  _mCandleTimesArr = rawBars.map(c => c.realTime);

  // Build markers from detection data
  _mAllMarkers = buildMirrorMarkers();
  rebuildMirrorMarkers();

  // Derive forex day from bar data if not explicitly set
  let forexDay = mApp.day || null;
  if (!forexDay && rawBars.length > 0) {
    // Use the last bar's real time to determine the forex day
    const lastRealTime = rawBars[rawBars.length - 1].realTime;
    const d = new Date(lastRealTime * 1000);
    const isoStr = d.toISOString();
    forexDay = typeof getForexDay === 'function' ? getForexDay(isoStr) : isoStr.split('T')[0];
  }

  // Session bands — only on LTF (1m, 5m, 15m, 1H).
  // On 4H/1D the sessions overlap into a solid color wash — hide them.
  var showSessions = mApp.tf === '1m' || mApp.tf === '5m' || mApp.tf === '15m' || mApp.tf === '1H';
  let allBands = [];
  if (showSessions && forexDay) {
    // Show session bands for the active forex day only.
    // Multi-day bands create opacity stacking (yellow/purple wash) — not useful.
    allBands = getMirrorSessionBands(forexDay);

    // Convert session band real timestamps to sequential for rendering
    if (_mRealToSeq && Object.keys(_mRealToSeq).length > 0) {
      allBands = allBands.map(function(b) {
        return {
          startTS: _findNearestSeqTime(b.startTS),
          endTS: _findNearestSeqTime(b.endTS),
          color: b.color,
          border: b.border,
          session: b.session,
          label: b.label,
        };
      }).filter(function(b) {
        // Filter out bands where start === end (degenerate — no visible region)
        return b.startTS != null && b.endTS != null && b.startTS !== b.endTS;
      });
    }
  }
  if (_mSessionPrimitive) {
    _mSessionPrimitive.setBands(allBands);
  }

  // Scroll behavior depends on mode and last action
  var htf = isHTF(mApp.tf);
  var lastAction = (typeof viewState !== 'undefined') ? viewState.lastAction : null;

  if (lastAction === 'tf-switch') {
    // TF switch: fit all content to avoid two-candle zoom
    mApp.chart.timeScale().fitContent();
    // Clear the hint so subsequent WS-driven refreshes use normal behavior
    viewState.lastAction = null;
  } else if (mApp.mode === 'live' && !htf) {
    mApp.chart.timeScale().scrollToRealTime();
  } else if (mApp.day && !htf) {
    mApp.chart.timeScale().setVisibleRange(_mDayRange(mApp.day));
  } else {
    // HTF and historical: fit all content so bars fill the view
    mApp.chart.timeScale().fitContent();
  }

  // Force session band re-render
  requestAnimationFrame(() => {
    if (_mSessionPrimitive && _mSessionPrimitive._requestUpdate) {
      _mSessionPrimitive._requestUpdate();
      requestAnimationFrame(() => {
        if (_mSessionPrimitive && _mSessionPrimitive._requestUpdate) {
          _mSessionPrimitive._requestUpdate();
        }
      });
    }
  });

  // Active level lines
  if (typeof updateActiveLevels === 'function') updateActiveLevels();

  // Hide loading overlay
  const loading = document.getElementById('loading-overlay');
  if (loading) loading.classList.add('hidden');
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * appendLiveBar — Called when a single new bar arrives via WebSocket
 * ═══════════════════════════════════════════════════════════════════════════════ */

function appendLiveBar(barData) {
  if (typeof mApp === 'undefined') return;
  if (!mApp.candleSeries) return;

  const realTS = toNYTS(barData.time);
  if (realTS == null) return;

  // Compute sequential timestamp for this bar
  var seqTS;
  if (_mRealToSeq[realTS] != null) {
    // Already mapped (update existing bar)
    seqTS = _mRealToSeq[realTS];
  } else {
    // New bar — assign next sequential slot
    var lastSeq = 0;
    var keys = Object.keys(_mSeqToReal);
    if (keys.length > 0) {
      lastSeq = Math.max.apply(null, keys.map(Number));
    }
    var tfLower = (mApp.tf || '1m').toLowerCase();
    var spacing = 60;
    if (tfLower === '5m') spacing = 300;
    else if (tfLower === '15m') spacing = 900;
    else if (tfLower === '1h') spacing = 3600;
    else if (tfLower === '4h') spacing = 14400;
    seqTS = lastSeq + spacing;
    _mSeqToReal[seqTS] = realTS;
    _mRealToSeq[realTS] = seqTS;
  }

  const bar = {
    time: seqTS,
    open: barData.open,
    high: barData.high,
    low: barData.low,
    close: barData.close,
  };

  try {
    mApp.candleSeries.update(bar);
  } catch (e) {
    console.warn('appendLiveBar update error:', e);
    return;
  }

  // Update real candle time tracking
  if (_mCandleTimeSet && !_mCandleTimeSet.has(realTS)) {
    _mCandleTimeSet.add(realTS);
    if (_mCandleTimesArr) {
      _mCandleTimesArr.push(realTS);
    }
  }

  if (mApp.mode === 'live' && mApp.chart) {
    mApp.chart.timeScale().scrollToRealTime();
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Build Markers from Detection Data
 * ═══════════════════════════════════════════════════════════════════════════════ */

function buildMirrorMarkers() {
  if (typeof mApp === 'undefined') return [];
  if (!mApp.detectionData || !mApp.detectionData.detections_by_primitive) return [];
  if (!_mCandleTimeSet || !_mCandleTimesArr) return [];

  const markers = [];

  for (const [primName, byTf] of Object.entries(mApp.detectionData.detections_by_primitive)) {
    const style = M_MARKER_STYLES[primName];

    // vLOCK: show only detections native to the displayed timeframe.
    // "5m FVG = gap across 3 consecutive 5m candles. NOT: 1m detection projected onto 5m display."
    var currentTf = mApp.tf;
    var tfDets = byTf[currentTf] || byTf['global'] || [];

    for (const det of tfDets) {
      const barTime = findMirrorNearestCandleTime(det.time);
      if (barTime == null) continue;

      // Direction can be top-level or nested in properties (swing_point uses properties.swing_type)
      const dir = det.direction || (det.properties && (det.properties.direction || det.properties.swing_type)) || '';
      const isBullish = dir === 'bullish' || dir === 'high';
      const isBearish = dir === 'bearish' || dir === 'low';

      markers.push({
        time: barTime,
        position: isBearish ? 'aboveBar' : 'belowBar',
        shape: style ? (isBearish ? style.shape_high : style.shape_low) : (isBearish ? 'arrowDown' : 'arrowUp'),
        color: style ? style.color : '#787b86',
        size: 1,
        text: '',
        _primitive: primName,
        _detId: det.id,
        _det: det,
      });
    }
  }

  // Add DIAGNOSTIC_SIGNAL markers (larger, gold)
  if (mApp.detectionData.diagnostic_signals) {
    for (const sig of mApp.detectionData.diagnostic_signals) {
      const barTime = findMirrorNearestCandleTime(sig.time);
      if (barTime == null) continue;

      const isBearish = sig.direction === 'bearish' || sig.direction === 'low';

      markers.push({
        time: barTime,
        position: isBearish ? 'aboveBar' : 'belowBar',
        shape: 'square',
        color: '#ffd700',
        size: 2,
        text: '◆',
        _primitive: 'diagnostic_signal',
        _detId: sig.id,
        _signal: sig,
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
 * rebuildMirrorMarkers — Filter by toggle state and apply
 * ═══════════════════════════════════════════════════════════════════════════════ */

function rebuildMirrorMarkers() {
  if (typeof mApp === 'undefined') return;
  if (!mApp.candleSeries) return;

  const filtered = _mAllMarkers.filter(m => {
    if (mApp.primitiveToggles[m._primitive] === false) return false;
    return true;
  });

  // Sort by time (required by LWC)
  filtered.sort((a, b) => a.time - b.time);

  try {
    mApp.candleSeries.setMarkers(filtered);
  } catch (e) {
    console.warn('setMarkers error:', e);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * updateSignalMarkers — Add/update DIAGNOSTIC_SIGNAL markers on chart
 * ═══════════════════════════════════════════════════════════════════════════════ */

function updateSignalMarkers() {
  if (typeof mApp === 'undefined') return;
  if (!mApp.detectionData || !mApp.detectionData.diagnostic_signals) return;
  if (!_mCandleTimeSet || !_mCandleTimesArr) return;

  // Rebuild all markers including updated signal data
  _mAllMarkers = buildMirrorMarkers();
  rebuildMirrorMarkers();

  // Set up click handler for signal markers (highlight chain components)
  _setupSignalClickHandler();
}

/* ── Signal click handler (highlight chain: MSS, sweep, FVG/OB, OTE) ─── */

let _mSignalClickBound = false;

function _setupSignalClickHandler() {
  if (typeof mApp === 'undefined') return;
  if (!mApp.chart || _mSignalClickBound) return;
  _mSignalClickBound = true;

  mApp.chart.subscribeClick((param) => {
    if (!param.time || !param.point) return;
    if (typeof mApp === 'undefined') return;

    // Find signal markers at or near the clicked time
    const clickedSignal = _mAllMarkers.find(m =>
      m._primitive === 'diagnostic_signal' && m.time === param.time && m._signal
    );

    if (!clickedSignal || !clickedSignal._signal) return;

    const sig = clickedSignal._signal;

    // Highlight chain components if they exist
    if (sig.chain_components && typeof _highlightChainComponents === 'function') {
      _highlightChainComponents(sig.chain_components);
    }

    // Show tooltip with five-factor breakdown
    _showSignalTooltip(param.point, sig);
  });
}

/* ── Signal tooltip overlay ─────────────────────────────────────────────── */

function _showSignalTooltip(point, signal) {
  // Remove any existing tooltip
  _removeSignalTooltip();

  const container = document.getElementById('chart-container');
  if (!container) return;

  const tooltip = document.createElement('div');
  tooltip.id = 'mirror-signal-tooltip';
  tooltip.style.cssText = `
    position: absolute;
    z-index: 200;
    background: #1e222d;
    border: 1px solid #ffd700;
    border-radius: 4px;
    padding: 10px 12px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    color: #d1d4dc;
    max-width: 260px;
    pointer-events: auto;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
  `;

  // Position relative to click point
  const x = Math.min(point.x + 12, container.clientWidth - 280);
  const y = Math.max(point.y - 60, 4);
  tooltip.style.left = x + 'px';
  tooltip.style.top = y + 'px';

  // Build five-factor breakdown
  const factors = signal.factors || {};
  const rows = [
    { label: 'Direction', value: signal.direction || '—', color: signal.direction === 'bullish' ? '#26a69a' : '#ef5350' },
    { label: 'Confidence', value: signal.confidence != null ? (signal.confidence * 100).toFixed(0) + '%' : '—', color: '#ffd700' },
  ];

  // Add five-factor scores
  const fiveFactors = ['mss', 'sweep', 'fvg_ob', 'ote', 'session'];
  for (const fk of fiveFactors) {
    const val = factors[fk];
    rows.push({
      label: fk.toUpperCase().replace('_', '/'),
      value: val != null ? (typeof val === 'number' ? val.toFixed(2) : String(val)) : '—',
      color: '#787b86',
    });
  }

  let html = '<div style="font-weight:600;color:#ffd700;margin-bottom:6px;">◆ DIAGNOSTIC SIGNAL</div>';
  for (const r of rows) {
    html += `<div style="display:flex;justify-content:space-between;gap:8px;margin:2px 0;">
      <span style="color:#787b86;">${r.label}</span>
      <span style="color:${r.color};font-weight:500;">${r.value}</span>
    </div>`;
  }

  // Close button
  html += '<div style="text-align:right;margin-top:6px;"><span style="cursor:pointer;color:#4a4e59;font-size:10px;" onclick="this.closest(\'#mirror-signal-tooltip\').remove()">✕ close</span></div>';

  tooltip.innerHTML = html;
  container.style.position = 'relative';
  container.appendChild(tooltip);

  // Auto-dismiss on next chart click (delayed to avoid immediate removal)
  setTimeout(() => {
    const dismiss = () => {
      _removeSignalTooltip();
      document.removeEventListener('click', dismiss, true);
    };
    document.addEventListener('click', dismiss, true);
  }, 200);
}

function _removeSignalTooltip() {
  const existing = document.getElementById('mirror-signal-tooltip');
  if (existing) existing.remove();
}

/* ── Crosshair primitive tooltip (hover) ─────────────────────────────────── */

let _mPrimTooltip = null;

function _handleCrosshairTooltip(param, container) {
  // Update OHLC legend
  _updateOHLCLegend(param);

  if (!param.time || !param.point) {
    _removePrimTooltip();
    return;
  }

  const markersAtTime = _mAllMarkers.filter(
    m => m.time === param.time && m._primitive !== 'diagnostic_signal' && m._det
  );

  if (markersAtTime.length === 0) {
    _removePrimTooltip();
    return;
  }

  _removePrimTooltip();

  const tooltip = document.createElement('div');
  tooltip.id = 'mirror-prim-tooltip';
  tooltip.style.cssText =
    'position:absolute;z-index:190;background:#1e222d;border-radius:4px;padding:8px 10px;' +
    'font-family:"IBM Plex Mono",monospace;font-size:11px;color:#d1d4dc;max-width:280px;' +
    'pointer-events:none;box-shadow:0 4px 12px rgba(0,0,0,0.5);';

  let html = '';
  const shown = Math.min(markersAtTime.length, 4);
  for (let i = 0; i < shown; i++) {
    const m = markersAtTime[i];
    const det = m._det;
    const pColor = M_MARKER_STYLES[m._primitive]?.color || '#787b86';
    const pLabel = (typeof mPrimLabel === 'function') ? mPrimLabel(m._primitive) : m._primitive;
    const dir = det.direction || (det.properties && det.properties.direction) || '';

    if (i > 0) html += '<div style="border-top:1px solid #2a2e39;margin:4px 0;"></div>';
    html += `<div style="font-weight:600;color:${pColor};margin-bottom:2px;">${pLabel}</div>`;
    if (dir) html += `<div><span style="color:#787b86;">dir</span> ${dir}</div>`;
    if (det.time) html += `<div><span style="color:#787b86;">time</span> ${det.time}</div>`;

    html += _formatPrimitiveProps(m._primitive, det);
  }

  if (markersAtTime.length > shown) {
    html += `<div style="color:#787b86;margin-top:4px;font-size:10px;">+${markersAtTime.length - shown} more</div>`;
  }

  tooltip.innerHTML = html;
  tooltip.style.borderLeft = `3px solid ${M_MARKER_STYLES[markersAtTime[0]._primitive]?.color || '#787b86'}`;

  const x = Math.min(param.point.x + 16, container.clientWidth - 290);
  const y = Math.max(param.point.y - 40, 4);
  tooltip.style.left = x + 'px';
  tooltip.style.top = y + 'px';

  container.style.position = 'relative';
  container.appendChild(tooltip);
  _mPrimTooltip = tooltip;
}

function _formatPrimitiveProps(primName, det) {
  const props = det.properties || det;
  let html = '';

  switch (primName) {
    case 'mss': {
      const bt = props.break_type || '';
      const dg = (props.displacement && props.displacement.quality_grade) || props.quality_grade || '';
      if (bt) html += `<div><span style="color:#787b86;">break</span> ${bt}</div>`;
      if (dg) html += `<div><span style="color:#787b86;">grade</span> ${dg}</div>`;
      break;
    }
    case 'liquidity_sweep': {
      const lv = props.level_price ?? props.level ?? props.price ?? '';
      const bp = props.breach_pips ?? '';
      const qs = props.qualified_sweep;
      if (lv !== '') html += `<div><span style="color:#787b86;">level</span> ${Number(lv).toFixed(5)}</div>`;
      if (bp !== '') html += `<div><span style="color:#787b86;">breach</span> ${bp} pips</div>`;
      if (qs != null) html += `<div><span style="color:#787b86;">qualified</span> ${qs}</div>`;
      break;
    }
    case 'fvg': {
      const top = props.top ?? props.zone_top ?? '';
      const bot = props.bottom ?? props.zone_bottom ?? '';
      if (top !== '' && bot !== '') html += `<div><span style="color:#787b86;">range</span> ${Number(bot).toFixed(5)} – ${Number(top).toFixed(5)}</div>`;
      break;
    }
    case 'displacement': {
      const qg = props.quality_grade || '';
      const am = props.atr_multiple ?? '';
      if (qg) html += `<div><span style="color:#787b86;">grade</span> ${qg}</div>`;
      if (am !== '') html += `<div><span style="color:#787b86;">ATR×</span> ${Number(am).toFixed(2)}</div>`;
      break;
    }
    case 'order_block': {
      const zt = props.zone_top ?? (props.zone_body && props.zone_body[0]) ?? '';
      const zb = props.zone_bottom ?? (props.zone_body && props.zone_body[1]) ?? '';
      if (zt !== '' && zb !== '') html += `<div><span style="color:#787b86;">zone</span> ${Number(zb).toFixed(5)} – ${Number(zt).toFixed(5)}</div>`;
      break;
    }
    case 'ote': {
      const fl = props.fib_levels || {};
      const lo = fl.lower ?? fl['0.618'] ?? '';
      const hi = fl.upper ?? fl['0.79'] ?? '';
      if (lo !== '' && hi !== '') html += `<div><span style="color:#787b86;">OTE</span> ${Number(lo).toFixed(5)} – ${Number(hi).toFixed(5)}</div>`;
      break;
    }
    case 'swing_point': {
      const sp = props.swing_type || props.type || '';
      const pr = props.price ?? props.level ?? '';
      if (sp) html += `<div><span style="color:#787b86;">type</span> ${sp}</div>`;
      if (pr !== '') html += `<div><span style="color:#787b86;">price</span> ${Number(pr).toFixed(5)}</div>`;
      break;
    }
    default:
      break;
  }
  return html;
}

function _removePrimTooltip() {
  if (_mPrimTooltip) {
    _mPrimTooltip.remove();
    _mPrimTooltip = null;
  }
}

/* ── OHLC Legend (crosshair-driven) ──────────────────────────────────────── */

function _updateOHLCLegend(param) {
  const el = document.getElementById('ohlc-legend');
  if (!el) return;

  if (!param.time || !param.seriesData) {
    el.textContent = '';
    return;
  }

  let bar = null;
  if (typeof mApp !== 'undefined' && mApp.candleSeries) {
    bar = param.seriesData.get(mApp.candleSeries);
  }
  if (!bar) {
    el.textContent = '';
    return;
  }

  const fmt = (v) => v != null ? Number(v).toFixed(5) : '—';
  const oColor = bar.close >= bar.open ? '#26a69a' : '#ef5350';
  el.innerHTML =
    `<span style="color:#787b86;">O</span> <span style="color:${oColor}">${fmt(bar.open)}</span> ` +
    `<span style="color:#787b86;">H</span> <span style="color:${oColor}">${fmt(bar.high)}</span> ` +
    `<span style="color:#787b86;">L</span> <span style="color:${oColor}">${fmt(bar.low)}</span> ` +
    `<span style="color:#787b86;">C</span> <span style="color:${oColor}">${fmt(bar.close)}</span>`;
}

/* ── Highlight chain components ─────────────────────────────────────────── */

function _highlightChainComponents(components) {
  // components: { mss: detId, sweep: detId, fvg_ob: detId, ote: detId }
  // Briefly flash the matching markers by rebuilding with highlight
  // This is a visual cue — simply log for now, can be extended with custom primitives
  if (typeof mApp === 'undefined') return;
  console.log('[MIRROR] Signal chain components:', components);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Session Bands for current day
 * ═══════════════════════════════════════════════════════════════════════════════ */

/* Session time ranges (NY timezone offsets in UTC hours) */
const _M_SESSION_DEFS = {
  asia:  { label: 'Asia 19:00–00:00',  startH: 19, startM: 0,  endH: 0,  endM: 0,
           color: 'rgba(156, 39, 176, 0.08)',   border: 'rgba(156, 39, 176, 0.25)' },
  lokz:  { label: 'LOKZ 02:00–05:00',  startH: 2,  startM: 0,  endH: 5,  endM: 0,
           color: 'rgba(41, 98, 255, 0.08)',   border: 'rgba(41, 98, 255, 0.25)' },
  nyokz: { label: 'NYOKZ 07:00–10:00', startH: 7,  startM: 0,  endH: 10, endM: 0,
           color: 'rgba(247, 197, 72, 0.08)',   border: 'rgba(247, 197, 72, 0.25)' },
};

/* Active session border colors (brighter when current time is inside) */
const _M_SESSION_ACTIVE_BORDER = {
  asia:  'rgba(156, 39, 176, 0.55)',
  lokz:  'rgba(41, 98, 255, 0.55)',
  nyokz: 'rgba(247, 197, 72, 0.55)',
};

function getMirrorSessionBands(forexDay) {
  if (typeof mApp === 'undefined') return [];

  // If session data is provided by the backend, use it directly
  if (mApp.sessionData && mApp.sessionData.length > 0) {
    const VISIBLE_SESSIONS = new Set(['asia', 'lokz', 'nyokz']);
    const htf = typeof isHTF === 'function' && isHTF(mApp.tf);
    const now = Math.floor(Date.now() / 1000) + (_nyOffset || 0);

    return mApp.sessionData
      .filter(b => VISIBLE_SESSIONS.has(b.session) && (!forexDay || b.forex_day === forexDay))
      .map(b => {
        let color = b.color;
        let border = b.border;

        // Reduce opacity on HTF to prevent solid color stacking
        if (htf) {
          color = color.replace(/([\d.]+)\)$/, (_, a) => (parseFloat(a) * 0.4).toFixed(2) + ')');
          border = border.replace(/([\d.]+)\)$/, (_, a) => (parseFloat(a) * 0.5).toFixed(2) + ')');
        }

        const startTS = toNYTS(b.start_time);
        const endTS = toNYTS(b.end_time);

        // Active zone highlighting: brighter border if current time is inside
        if (startTS && endTS && now >= startTS && now <= endTS) {
          border = _M_SESSION_ACTIVE_BORDER[b.session] || border;
        }

        return { startTS, endTS, color, border, session: b.session, label: b.label };
      })
      .filter(b => b.startTS != null && b.endTS != null);
  }

  // Fallback: compute from forex day
  if (!forexDay) return [];

  const bands = [];
  const baseDate = forexDay; // YYYY-MM-DD

  for (const [sessKey, def] of Object.entries(_M_SESSION_DEFS)) {
    let startStr, endStr;

    if (def.startH >= 17) {
      // Previous calendar day (Asia starts at 19:00 NY = previous day in forex)
      const prev = new Date(baseDate + 'T12:00:00Z');
      prev.setUTCDate(prev.getUTCDate() - 1);
      const prevDate = prev.toISOString().split('T')[0];
      startStr = `${prevDate}T${String(def.startH).padStart(2, '0')}:${String(def.startM).padStart(2, '0')}:00`;
    } else {
      startStr = `${baseDate}T${String(def.startH).padStart(2, '0')}:${String(def.startM).padStart(2, '0')}:00`;
    }

    if (def.endH === 0 && def.endM === 0) {
      // Midnight = start of forex day
      endStr = `${baseDate}T00:00:00`;
    } else {
      endStr = `${baseDate}T${String(def.endH).padStart(2, '0')}:${String(def.endM).padStart(2, '0')}:00`;
    }

    const startTS = toTS(startStr);
    const endTS = toTS(endStr);
    const now = Math.floor(Date.now() / 1000) + (_nyOffset || 0);

    let border = def.border;
    if (startTS && endTS && now >= startTS && now <= endTS) {
      border = _M_SESSION_ACTIVE_BORDER[sessKey] || border;
    }

    bands.push({
      startTS,
      endTS,
      color: def.color,
      border,
      session: sessKey,
      label: def.label,
    });
  }

  return bands.filter(b => b.startTS != null && b.endTS != null);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Find Nearest Candle Time for a Detection
 * ═══════════════════════════════════════════════════════════════════════════════ */

function findMirrorNearestCandleTime(detTime) {
  if (!_mCandleTimeSet || !_mCandleTimesArr) return null;

  // TIMEZONE: Detection times are NY-local (see TIMEZONE CONTRACT above).
  // toTS() parses as UTC, producing the same epoch as toNYTS() on a UTC
  // string. Do NOT use toNYTS() here — it would double-shift.
  const ts = toTS(detTime);
  if (ts == null) return null;

  // Find nearest real candle time (within tolerance based on TF)
  const tf = (typeof mApp !== 'undefined') ? mApp.tf : '15m';
  const htf = typeof isHTF === 'function' && isHTF(tf);
  const maxDiff = tf === '1D' ? 86400 : tf === '1m' ? 900 : htf ? 14400 : 3600;

  // Exact match
  if (_mCandleTimeSet.has(ts)) {
    return _mRealToSeq[ts] != null ? _mRealToSeq[ts] : ts;
  }

  // Nearest match
  let best = null;
  let bestDiff = Infinity;
  for (const ct of _mCandleTimesArr) {
    const diff = Math.abs(ct - ts);
    if (diff < bestDiff) {
      bestDiff = diff;
      best = ct;
    }
  }
  if (bestDiff <= maxDiff && best != null) {
    return _mRealToSeq[best] != null ? _mRealToSeq[best] : best;
  }
  return null;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Active Level Lines on Chart (LWC createPriceLine)
 * ═══════════════════════════════════════════════════════════════════════════════ */

let _mActiveLines = [];

const _LEVEL_COLORS = {
  swing_high:   '#00e5ff',
  swing_low:    '#00e5ff',
  pdh:          '#ff9800',
  pdl:          '#ff9800',
  asia_high:    '#e91e63',
  asia_low:     '#e91e63',
  session_high: '#795548',
  session_low:  '#795548',
  eqh:          '#8bc34a',
  eql:          '#8bc34a',
};

function updateActiveLevels() {
  if (typeof mApp === 'undefined' || !mApp.candleSeries) return;

  // Remove existing lines
  for (const line of _mActiveLines) {
    try { mApp.candleSeries.removePriceLine(line); } catch (_) {}
  }
  _mActiveLines = [];

  if (!mApp.detectionData) return;
  const levels = mApp.detectionData.active_levels || mApp.detectionData.reference_levels || [];
  if (!Array.isArray(levels) || levels.length === 0) return;

  for (const lvl of levels) {
    const price = lvl.price ?? lvl.level ?? lvl.value;
    if (price == null) continue;

    const label = lvl.label || lvl.type || '';
    const levelType = (lvl.type || '').toLowerCase();
    const color = _LEVEL_COLORS[levelType] || '#607d8b';

    try {
      const line = mApp.candleSeries.createPriceLine({
        price: Number(price),
        color: color,
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: label,
      });
      _mActiveLines.push(line);
    } catch (_) {}
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * initOrRefreshMirrorChart — Entry point, guarded by _mChartCreated
 * ═══════════════════════════════════════════════════════════════════════════════ */

function initOrRefreshMirrorChart() {
  if (!_mChartCreated) {
    createMirrorChart();
  }
  refreshMirrorChart();
}
