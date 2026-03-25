/* ═══════════════════════════════════════════════════════════════════════════════
 * mirror-state.js — Unified state management for MIRROR dashboard
 *
 * ALL user actions flow through setView(patch). No other code mutates
 * view state directly. This eliminates race conditions, stale data leaks,
 * and the "fix one interaction, break another" cycle.
 *
 * Architecture:
 *   action → setView({tf?, date?, mode?})
 *     → compute derived ranges (barRange)
 *     → cancel in-flight fetches (AbortController)
 *     → parallel fetch: bars + sessions + detections
 *     → on completion: render(version) — no-ops if version is stale
 *
 * Loaded BEFORE mirror-app.js, mirror-chart.js, mirror-feed.js.
 * ═══════════════════════════════════════════════════════════════════════════════ */

/* ── TF Lookback Table ─────────────────────────────────────────────────────── */

const VIEW_TF_LOOKBACK = {
  '1m': 1, '5m': 2, '15m': 4, '1H': 9, '4H': 29, '1D': 59,
};

/* ── ViewState — single source of truth ────────────────────────────────────── */

const viewState = {
  // Core state (set by setView only)
  mode: 'live',           // 'live' | 'historical'
  tf: '5m',               // active timeframe
  anchorDate: null,        // YYYY-MM-DD — the date the view is centered on (null = today)

  // Derived state (computed by setView, read-only externally)
  barRange: null,          // { start: 'YYYY-MM-DD', end: 'YYYY-MM-DD' }

  // Loaded data (populated by fetch pipeline, read-only externally)
  bars: [],                // candle data for current TF
  detections: null,        // { detections_by_primitive: {...}, diagnostic_signals: [...] }
  sessions: [],            // session bands [{session, forex_day, start_time, end_time, color, border}]
  worldState: null,        // { htf_phase, direction_permission, ... }
  worldStateSnapshots: [],
  signals: [],

  // Navigation (derived from loaded data)
  forexDays: [],
  activeDay: null,         // currently focused forex day (for day tab highlighting)

  // Version counter — incremented on every setView call.
  // Render functions check this to skip stale renders.
  version: 0,

  // Fetch abort controller — cancels in-flight requests on new setView
  _abortController: null,

  // Loading state
  loading: false,
};

/* ── Compute derived bar range from anchor + TF lookback ───────────────────── */

function _computeBarRange(anchorDate, tf) {
  var lookback = VIEW_TF_LOOKBACK[tf] || 2;
  var anchor = anchorDate || _todayDateStr();
  var endD = new Date(anchor + 'T12:00:00Z');
  var startD = new Date(endD);
  startD.setUTCDate(startD.getUTCDate() - lookback);
  return {
    start: startD.toISOString().split('T')[0],
    end: endD.toISOString().split('T')[0],
  };
}

function _todayDateStr() {
  return new Date().toISOString().split('T')[0];
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * setView — THE state transition function
 *
 * Every user action calls this. It:
 *   1. Updates core state
 *   2. Computes derived ranges
 *   3. Cancels in-flight fetches
 *   4. Fetches all data in parallel
 *   5. Renders on completion (version-gated)
 *
 * @param {Object} patch — partial update:
 *   - tf: switch timeframe (e.g., '4H')
 *   - date: navigate to a date (e.g., '2026-03-20')
 *   - mode: switch mode ('live' | 'historical')
 *   - day: set active forex day (for day tab click)
 *   - rangeStart/rangeEnd: explicit range (week picker)
 * ═══════════════════════════════════════════════════════════════════════════════ */

async function setView(patch) {
  if (!patch || typeof patch !== 'object') return;

  // ── Fast path: day-only change doesn't need data reload ─────────────
  if (patch.day && !patch.tf && !patch.date && !patch.mode && !patch.rangeStart) {
    viewState.activeDay = patch.day;
    _syncToMApp();
    if (typeof renderDayTabs === 'function') renderDayTabs();
    return;
  }

  viewState.version++;
  var thisVersion = viewState.version;

  // ── 1. Update core state ────────────────────────────────────────────
  if (patch.mode != null) viewState.mode = patch.mode;
  if (patch.tf != null) viewState.tf = patch.tf;
  if (patch.date !== undefined) viewState.anchorDate = patch.date;

  // Live mode clears anchor date (follow current time)
  if (viewState.mode === 'live' && patch.date === undefined) {
    viewState.anchorDate = null;
  }

  // ── 2. Compute derived ranges ───────────────────────────────────────
  var barRange;
  if (patch.rangeStart && patch.rangeEnd) {
    // Explicit range (week picker) — expand by TF lookback for context
    var lookback = VIEW_TF_LOOKBACK[viewState.tf] || 9;
    var midDate = new Date(patch.rangeStart + 'T12:00:00Z');
    midDate.setUTCDate(midDate.getUTCDate() + 2); // ~Wednesday
    var rangeStart = new Date(midDate);
    rangeStart.setUTCDate(rangeStart.getUTCDate() - lookback);
    var rangeEnd = new Date(midDate);
    rangeEnd.setUTCDate(rangeEnd.getUTCDate() + lookback);
    var today = new Date();
    if (rangeEnd > today) rangeEnd.setTime(today.getTime());
    barRange = {
      start: rangeStart.toISOString().split('T')[0],
      end: rangeEnd.toISOString().split('T')[0],
    };
  } else {
    barRange = _computeBarRange(viewState.anchorDate, viewState.tf);
  }
  viewState.barRange = barRange;

  // ── 3. Cancel in-flight fetches ─────────────────────────────────────
  if (viewState._abortController) {
    viewState._abortController.abort();
  }
  viewState._abortController = new AbortController();
  var signal = viewState._abortController.signal;

  // ── 4. Show loading state ───────────────────────────────────────────
  viewState.loading = true;
  _showLoading(true);

  // ── 5. Parallel fetch: bars + sessions + detections ─────────────────
  try {
    var tf = viewState.tf;
    var start = barRange.start;
    var end = barRange.end;

    var fetches = [
      fetch('/api/bars-range?start=' + start + '&end=' + end + '&tf=' + tf, { signal }),
      fetch('/api/sessions-range?start=' + start + '&end=' + end, { signal }),
    ];

    // Try the range endpoint first; fall back to per-day loading
    var useDetsRange = true;
    fetches.push(
      fetch('/api/detections-range?start=' + start + '&end=' + end, { signal })
        .catch(function () { useDetsRange = false; return null; })
    );

    var responses = await Promise.all(fetches);

    // ── Version gate: skip if a newer setView() has been called ───────
    if (viewState.version !== thisVersion) return;

    var barsResp = responses[0];
    var sessResp = responses[1];
    var detsResp = responses[2];

    // Parse bars
    if (barsResp && barsResp.ok) {
      var barsData = await barsResp.json();
      viewState.bars = barsData.data || [];
    } else {
      viewState.bars = [];
    }

    // Parse sessions
    if (sessResp && sessResp.ok) {
      var sessData = await sessResp.json();
      viewState.sessions = sessData.sessions || [];
    } else {
      viewState.sessions = [];
    }

    // Parse detections (range endpoint or fallback)
    if (useDetsRange && detsResp && detsResp.ok) {
      viewState.detections = await detsResp.json();
    } else {
      viewState.detections = await _loadDetectionsParallel(start, end, signal);
    }

    // ── Version gate again (after async parsing) ──────────────────────
    if (viewState.version !== thisVersion) return;

    // Extract world state from detections (most recent day)
    if (viewState.detections) {
      if (viewState.detections.world_state) {
        viewState.worldState = viewState.detections.world_state;
      }
      if (viewState.detections.world_state_snapshots) {
        viewState.worldStateSnapshots = viewState.detections.world_state_snapshots;
      }
    }

    // ── 6. Render ─────────────────────────────────────────────────────
    viewState.loading = false;
    _showLoading(false);

    // Sync into mApp for chart/feed consumption (bridge layer)
    _syncToMApp();

    // Trigger ALL renders at once — data is complete
    if (typeof refreshMirrorChart === 'function') refreshMirrorChart();
    if (typeof updateFeedFromDetections === 'function') updateFeedFromDetections(viewState.detections);
    if (typeof updateWorldStateBanner === 'function') updateWorldStateBanner();
    if (typeof updateFiveFactorRow === 'function') updateFiveFactorRow();
    if (typeof updateSetupSummary === 'function') updateSetupSummary();
    if (typeof renderDayTabs === 'function') renderDayTabs();
    if (typeof renderStateTimeline === 'function') renderStateTimeline();
    if (typeof updateMetadata === 'function') updateMetadata();

  } catch (err) {
    if (err.name === 'AbortError') {
      // Expected — a newer setView() cancelled this one
      return;
    }
    console.error('[MIRROR] setView fetch error:', err);
    viewState.loading = false;
    _showLoading(false);
  }
}

/* ── Parallel detection loading (fallback until /api/detections-range) ────── */

async function _loadDetectionsParallel(startDate, endDate, signal) {
  var merged = { detections_by_primitive: {}, diagnostic_signals: [] };
  var dates = [];
  var d = new Date(startDate + 'T12:00:00Z');
  var dEnd = new Date(endDate + 'T12:00:00Z');
  while (d <= dEnd) {
    dates.push(d.toISOString().split('T')[0]);
    d.setUTCDate(d.getUTCDate() + 1);
  }

  // Parallel fetch all dates
  var results = await Promise.all(
    dates.map(function (ds) {
      return fetch('/api/detections/' + ds, { signal })
        .then(function (r) { return r.ok ? r.json() : null; })
        .catch(function () { return null; });
    })
  );

  for (var i = 0; i < results.length; i++) {
    var dd = results[i];
    if (!dd) continue;
    var byPrim = dd.detections_by_primitive || {};
    for (var prim in byPrim) {
      if (!byPrim.hasOwnProperty(prim)) continue;
      if (!merged.detections_by_primitive[prim]) merged.detections_by_primitive[prim] = {};
      var byTf = byPrim[prim];
      for (var tf2 in byTf) {
        if (!byTf.hasOwnProperty(tf2)) continue;
        if (!merged.detections_by_primitive[prim][tf2]) merged.detections_by_primitive[prim][tf2] = [];
        var dets = byTf[tf2];
        for (var j = 0; j < dets.length; j++) {
          merged.detections_by_primitive[prim][tf2].push(dets[j]);
        }
      }
    }
    if (dd.diagnostic_signals) {
      for (var k = 0; k < dd.diagnostic_signals.length; k++) {
        merged.diagnostic_signals.push(dd.diagnostic_signals[k]);
      }
    }
    // Keep world state from the most recent day
    if (dd.world_state) merged.world_state = dd.world_state;
    if (dd.world_state_snapshots) merged.world_state_snapshots = dd.world_state_snapshots;
  }
  return merged;
}

/* ── Bridge: sync viewState → mApp (temporary until full migration) ────────── */

function _syncToMApp() {
  if (typeof mApp === 'undefined') return;

  mApp.tf = viewState.tf;
  mApp.mode = viewState.mode;
  mApp.currentDate = viewState.anchorDate;
  mApp.day = viewState.activeDay;

  // Candle data keyed by TF (chart reads mApp.candleData[mApp.tf])
  if (!mApp.candleData) mApp.candleData = {};
  mApp.candleData[viewState.tf] = viewState.bars;

  mApp.detectionData = viewState.detections;
  mApp.sessionData = viewState.sessions;
  mApp.forexDays = viewState.forexDays;
  mApp.signals = viewState.signals;

  // World state
  if (viewState.worldState) mApp.worldState = viewState.worldState;
  if (viewState.worldStateSnapshots) mApp.worldStateSnapshots = viewState.worldStateSnapshots;
}

/* ── Loading overlay helper ────────────────────────────────────────────────── */

function _showLoading(show) {
  var el = document.getElementById('loading-overlay');
  if (!el) return;
  if (show) el.classList.remove('hidden');
  else el.classList.add('hidden');
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * handleLiveUpdate — Process WS data pushes in live mode
 *
 * In live mode, the server pushes incremental updates (bars, detections, etc.).
 * These update viewState data and trigger renders — but ONLY if no setView()
 * fetch is in flight (prevents stale-data races).
 * ═══════════════════════════════════════════════════════════════════════════════ */

function handleLiveUpdate(msg) {
  if (!msg || !msg.type) return;

  // If setView() is loading data, skip WS updates to prevent races
  if (viewState.loading) return;

  switch (msg.type) {
    case 'bars':
      // Only render bars for the active TF
      if (msg.tf === viewState.tf) {
        viewState.bars = msg.data || [];
        _syncToMApp();
        if (typeof refreshMirrorChart === 'function') refreshMirrorChart();
      }
      break;

    case 'detections': {
      var rawDet = msg.data || msg;
      viewState.detections = rawDet.detections_by_primitive
        ? rawDet
        : { detections_by_primitive: rawDet };
      _syncToMApp();
      if (typeof refreshMirrorChart === 'function') refreshMirrorChart();
      if (typeof updateFeedFromDetections === 'function') updateFeedFromDetections(viewState.detections);
      if (typeof updateFiveFactorRow === 'function') updateFiveFactorRow();
      if (typeof updateSetupSummary === 'function') updateSetupSummary();
      if (typeof renderDayTabs === 'function') renderDayTabs();
      break;
    }

    case 'world_state':
      viewState.worldState = msg.data || msg;
      _syncToMApp();
      if (typeof updateWorldStateBanner === 'function') updateWorldStateBanner();
      break;

    case 'sessions':
      viewState.sessions = msg.data || [];
      _syncToMApp();
      if (typeof refreshMirrorChart === 'function') refreshMirrorChart();
      break;

    case 'world_state_snapshots':
      viewState.worldStateSnapshots = msg.data || [];
      _syncToMApp();
      if (typeof renderStateTimeline === 'function') renderStateTimeline();
      break;

    case 'signals':
      viewState.signals = msg.data || msg.signals || [];
      _syncToMApp();
      if (typeof updateSignalMarkers === 'function') updateSignalMarkers();
      if (typeof addSignalsToFeed === 'function') addSignalsToFeed(viewState.signals);
      break;

    case 'status': {
      var stData = msg.data || msg;
      var st = (stData.state || '').toUpperCase();
      if (typeof updateLiveBadge === 'function') {
        if (st === 'LIVE') updateLiveBadge('live');
        else if (st === 'STALE') updateLiveBadge('stale');
        else if (st === 'MARKET_CLOSED') updateLiveBadge('closed');
        else updateLiveBadge('connecting');
      }
      if (stData.last_bar && typeof mApp !== 'undefined') mApp.lastBarTime = stData.last_bar;
      if (typeof updateMetadata === 'function') updateMetadata();
      break;
    }

    default:
      console.log('[MIRROR] Unknown WS message type:', msg.type);
  }
}
