/* ═══════════════════════════════════════════════════════════════════════════════
 * mirror-app.js — Global state, WebSocket client, data management, navigation,
 *                 and UI controls for the MIRROR live trading dashboard
 * ═══════════════════════════════════════════════════════════════════════════════ */

/* ── Global App State ──────────────────────────────────────────────────────── */

const mApp = {
  // Connection
  ws: null,
  wsConnected: false,
  wsReconnectTimer: null,

  // Mode
  mode: 'live',           // 'live' | 'historical'
  currentDate: null,       // YYYY-MM-DD, null = today

  // Data
  candleData: {},          // keyed by TF: { "1m": [...], "5m": [...], ... }
  detectionData: null,     // { detections_by_primitive: {...} }
  worldState: null,        // { htf_phase, direction_permission, ... }
  worldStateSnapshots: [], // intraday state change timeline
  sessionData: [],         // session bands from backend [{session, forex_day, start_time, end_time, color, border}]
  signals: [],             // DIAGNOSTIC_SIGNAL array

  // Navigation
  forexDays: [],           // derived forex day strings for loaded bar data
  day: null,               // current forex day focus (null = auto)

  // UI state
  tf: '5m',
  primitiveToggles: {},

  // Chart refs (set by mirror-chart.js)
  chart: null,
  candleSeries: null,
};

/* ── Primitives Config ─────────────────────────────────────────────────────── */

const M_PRIMITIVES = [
  { key: 'displacement',      label: 'Displacement',  color: '#26a69a' },
  { key: 'fvg',               label: 'FVG',           color: '#2962ff' },
  { key: 'mss',               label: 'MSS',           color: '#f7c548' },
  { key: 'order_block',       label: 'Order Block',   color: '#9c27b0' },
  { key: 'liquidity_sweep',   label: 'Liq Sweep',     color: '#ef5350' },
  { key: 'swing_point',       label: 'Swing Points',  color: '#00bcd4' },
  { key: 'ote',               label: 'OTE',           color: '#ff9800' },
  { key: 'asia_range',        label: 'Asia Range',    color: '#e91e63' },
  { key: 'htf_liquidity',     label: 'HTF Liq',       color: '#8bc34a' },
  { key: 'session_liquidity', label: 'Session Liq',   color: '#795548' },
  { key: 'reference_levels',  label: 'Ref Levels',    color: '#607d8b' },
];

/* Lookup helpers */
function mPrimLabel(key) {
  const p = M_PRIMITIVES.find(x => x.key === key);
  return p ? p.label : key;
}

function mPrimColor(key) {
  const p = M_PRIMITIVES.find(x => x.key === key);
  return p ? p.color : '#787b86';
}

/* ── Session Legend Metadata ────────────────────────────────────────────────── */

const M_SESSION_META = [
  { key: 'asia',  label: 'Asia 19:00–00:00', color: 'rgba(156,39,176,0.5)' },
  { key: 'lokz',  label: 'LOKZ 02:00–05:00', color: 'rgba(41,98,255,0.5)' },
  { key: 'nyokz', label: 'NYOKZ 07:00–10:00', color: 'rgba(247,197,72,0.5)' },
];

/* ── TF Options ────────────────────────────────────────────────────────────── */

const M_TF_OPTIONS = ['1m', '5m', '15m', '1H', '4H', '1D'];

/* ═══════════════════════════════════════════════════════════════════════════════
 * Utility Functions
 * ═══════════════════════════════════════════════════════════════════════════════ */

/**
 * Convert ISO string to unix timestamp.
 * Strips timezone offset, treats as UTC for LightweightCharts display.
 */
function toTS(s) {
  if (!s) return null;
  let clean = s;
  // Remove tz offset like -04:00 or +00:00
  clean = clean.replace(/[+-]\d{2}:\d{2}$/, '');
  // Ensure T separator
  clean = clean.includes('T') ? clean : clean.replace(' ', 'T');
  // Remove trailing Z
  const noZ = clean.endsWith('Z') ? clean.slice(0, -1) : clean;
  return Math.floor(new Date(noZ + 'Z').getTime() / 1000);
}

/**
 * Compute the forex day (YYYY-MM-DD) a timestamp belongs to.
 * Forex day starts at 17:00 NY — a candle at/after 17:00 belongs to the NEXT day.
 */
function getForexDay(rawTimeStr) {
  if (!rawTimeStr) return '';
  const clean = rawTimeStr.replace(/[+-]\d{2}:\d{2}$/, '');
  const tPart = (clean.split('T')[1]) || '';
  const hour = parseInt(tPart.split(':')[0], 10);
  const datePart = clean.split('T')[0];

  if (hour >= 17) {
    const d = new Date(datePart + 'T12:00:00Z');
    d.setUTCDate(d.getUTCDate() + 1);
    return d.toISOString().split('T')[0];
  }
  return datePart;
}

/** Format a date string for display */
function dayLabel(dateStr) {
  const d = new Date(dateStr + 'T12:00:00Z');
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${days[d.getUTCDay()]} ${months[d.getUTCMonth()]} ${d.getUTCDate()}`;
}

/** Check if timeframe is HTF (1H, 4H, 1D) */
function isHTF(tf) { return ['1H', '4H', '1D'].includes(tf); }

/* ═══════════════════════════════════════════════════════════════════════════════
 * WebSocket Client
 * ═══════════════════════════════════════════════════════════════════════════════ */

let _wsBackoff = 1000;  // current reconnect delay in ms
const _WS_BACKOFF_MAX = 30000;

function connectWS() {
  // Don't connect if in historical mode
  if (mApp.mode === 'historical') return;

  // Clean up any existing connection
  if (mApp.ws) {
    try { mApp.ws.close(); } catch (_) {}
    mApp.ws = null;
  }

  if (mApp.wsReconnectTimer) {
    clearTimeout(mApp.wsReconnectTimer);
    mApp.wsReconnectTimer = null;
  }

  updateLiveBadge('connecting');
  console.log('[MIRROR] Connecting to WebSocket…');

  try {
    var wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    mApp.ws = new WebSocket(wsProto + '//' + location.host + '/ws');
  } catch (e) {
    console.error('[MIRROR] WebSocket constructor error:', e);
    scheduleReconnect();
    return;
  }

  mApp.ws.onopen = function () {
    console.log('[MIRROR] WebSocket connected');
    mApp.wsConnected = true;
    _wsBackoff = 1000;  // reset backoff
    updateLiveBadge('live');

    // Send TF subscription preference
    mApp.ws.send(JSON.stringify({ type: 'subscribe', tf: mApp.tf }));
  };

  mApp.ws.onmessage = function (evt) {
    let msg;
    try {
      msg = JSON.parse(evt.data);
    } catch (e) {
      console.warn('[MIRROR] Bad WS message:', e);
      return;
    }
    handleWSMessage(msg);
  };

  mApp.ws.onclose = function (evt) {
    console.log('[MIRROR] WebSocket closed:', evt.code, evt.reason);
    mApp.wsConnected = false;
    mApp.ws = null;
    updateLiveBadge('disconnected');
    scheduleReconnect();
  };

  mApp.ws.onerror = function (err) {
    console.error('[MIRROR] WebSocket error:', err);
    // onclose will fire after onerror, so reconnect is handled there
  };
}

function scheduleReconnect() {
  if (mApp.mode !== 'live') return;
  if (mApp.wsReconnectTimer) return;

  console.log(`[MIRROR] Reconnecting in ${_wsBackoff / 1000}s…`);
  mApp.wsReconnectTimer = setTimeout(function () {
    mApp.wsReconnectTimer = null;
    connectWS();
  }, _wsBackoff);

  // Exponential backoff: 1s, 2s, 4s, 8s, … max 30s
  _wsBackoff = Math.min(_wsBackoff * 2, _WS_BACKOFF_MAX);
}

function disconnectWS() {
  if (mApp.wsReconnectTimer) {
    clearTimeout(mApp.wsReconnectTimer);
    mApp.wsReconnectTimer = null;
  }
  if (mApp.ws) {
    try { mApp.ws.close(); } catch (_) {}
    mApp.ws = null;
  }
  mApp.wsConnected = false;
}

/* ── WebSocket Message Router ──────────────────────────────────────────────── */

function handleWSMessage(msg) {
  if (!msg || !msg.type) return;

  switch (msg.type) {
    case 'bars':
      mApp.candleData[msg.tf] = msg.data || msg.bars || [];
      if (msg.tf === mApp.tf && typeof refreshMirrorChart === 'function') refreshMirrorChart();
      break;

    case 'detections': {
      const rawDet = msg.data || msg;
      if (rawDet.detections_by_primitive) {
        mApp.detectionData = rawDet;
      } else {
        mApp.detectionData = { detections_by_primitive: rawDet };
      }
      if (typeof refreshMirrorChart === 'function') refreshMirrorChart();
      if (typeof updateFeedFromDetections === 'function') updateFeedFromDetections(mApp.detectionData);
      updateFiveFactorRow();
      updateSetupSummary();
      renderDayTabs();
      break;
    }

    case 'world_state':
      mApp.worldState = msg.data || msg;
      updateWorldStateBanner();
      break;

    case 'sessions':
      mApp.sessionData = msg.data || [];
      if (typeof refreshMirrorChart === 'function') refreshMirrorChart();
      break;

    case 'world_state_snapshots':
      mApp.worldStateSnapshots = msg.data || [];
      if (typeof renderStateTimeline === 'function') renderStateTimeline();
      break;

    case 'signals':
      mApp.signals = msg.data || msg.signals || [];
      if (typeof updateSignalMarkers === 'function') updateSignalMarkers();
      if (typeof addSignalsToFeed === 'function') addSignalsToFeed(mApp.signals);
      break;

    case 'status': {
      var stData = msg.data || msg;
      var st = (stData.state || '').toUpperCase();
      if (st === 'LIVE') updateLiveBadge('live');
      else if (st === 'MARKET_CLOSED') updateLiveBadge('closed');
      else updateLiveBadge('connecting');
      if (stData.last_bar) mApp.lastBarTime = stData.last_bar;
      updateMetadata();
      break;
    }

    default:
      console.log('[MIRROR] Unknown WS message type:', msg.type);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * REST API Client (Historical Mode)
 * ═══════════════════════════════════════════════════════════════════════════════ */

async function loadHistoricalDate(dateStr) {
  const loading = document.getElementById('loading-overlay');
  if (loading) loading.classList.remove('hidden');

  try {
    const [barsResp, detsResp, sessResp] = await Promise.all([
      fetch(`/api/bars/${dateStr}?tf=${mApp.tf}`),
      fetch(`/api/detections/${dateStr}`),
      fetch(`/api/sessions/${dateStr}`),
    ]);

    if (barsResp.ok) {
      const barsData = await barsResp.json();
      // API may return { tf: bars[] } or bare array
      if (Array.isArray(barsData)) {
        mApp.candleData[mApp.tf] = barsData;
      } else {
        // Merge all TF keys from response
        for (const [tf, bars] of Object.entries(barsData)) {
          mApp.candleData[tf] = bars;
        }
      }
    } else {
      console.warn('[MIRROR] Failed to load bars:', barsResp.status);
    }

    if (detsResp.ok) {
      mApp.detectionData = await detsResp.json();
    } else {
      console.warn('[MIRROR] Failed to load detections:', detsResp.status);
      mApp.detectionData = null;
    }

    if (sessResp.ok) {
      const sessData = await sessResp.json();
      mApp.sessionData = sessData.sessions || [];
    }
  } catch (e) {
    console.error('[MIRROR] Failed to load historical data:', e);
  }

  if (loading) loading.classList.add('hidden');

  // Refresh chart with new data
  if (typeof refreshMirrorChart === 'function') refreshMirrorChart();
  updateMetadata();
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Navigation — Live / Historical Mode Switching
 * ═══════════════════════════════════════════════════════════════════════════════ */

function switchToLive() {
  mApp.mode = 'live';
  mApp.currentDate = null;
  mApp.candleData = {};
  mApp.detectionData = null;
  mApp.signals = [];

  // Update date picker to show no selection
  const picker = document.getElementById('date-picker');
  if (picker) picker.value = '';

  connectWS();
  updateMetadata();
}

function switchToHistorical(dateStr) {
  mApp.mode = 'historical';
  mApp.currentDate = dateStr;
  mApp.candleData = {};
  mApp.detectionData = null;
  mApp.signals = [];

  // Disconnect live feed
  disconnectWS();
  updateLiveBadge('disconnected');

  // Load REST data for the selected date
  loadHistoricalDate(dateStr);
}

function setupDatePicker() {
  const picker = document.getElementById('date-picker');
  const pickerEnd = document.getElementById('date-picker-end');
  const rangeBtn = document.getElementById('range-btn');
  if (!picker) return;

  // Set bounds from available range
  fetch('/api/available-range')
    .then(r => r.ok ? r.json() : null)
    .then(data => {
      if (data && data.earliest) {
        picker.min = data.earliest;
        if (pickerEnd) pickerEnd.min = data.earliest;
      }
      if (data && data.latest) {
        picker.max = data.latest;
        if (pickerEnd) pickerEnd.max = data.latest;
      }
    })
    .catch(() => {});

  picker.addEventListener('change', function () {
    const val = picker.value;
    if (!val) return;
    if (pickerEnd && pickerEnd.style.display !== 'none' && pickerEnd.value) {
      loadWeekRange(val, pickerEnd.value);
    } else {
      switchToHistorical(val);
    }
  });

  if (pickerEnd) {
    pickerEnd.addEventListener('change', function () {
      const start = picker.value;
      const end = pickerEnd.value;
      if (start && end) {
        loadWeekRange(start, end);
      }
    });
  }

  if (rangeBtn && pickerEnd) {
    rangeBtn.addEventListener('click', function () {
      const visible = pickerEnd.style.display !== 'none';
      pickerEnd.style.display = visible ? 'none' : '';
      rangeBtn.style.background = visible ? '' : 'rgba(41, 98, 255, 0.25)';
    });
  }
}

function setupNowButton() {
  const btn = document.getElementById('now-btn');
  if (!btn) return;

  btn.addEventListener('click', function () {
    switchToLive();
  });
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * UI Rendering — TF Buttons
 * ═══════════════════════════════════════════════════════════════════════════════ */

function renderTFButtons() {
  const container = document.getElementById('tf-group');
  if (!container) return;
  container.innerHTML = '';

  for (const tf of M_TF_OPTIONS) {
    const btn = document.createElement('button');
    btn.className = 'tf-btn' + (tf === mApp.tf ? ' active' : '');
    btn.textContent = tf;
    btn.dataset.tf = tf;
    btn.addEventListener('click', function () {
      if (tf === mApp.tf) return;
      mApp.tf = tf;
      _savePreferences();
      renderTFButtons();

      // Fetch bars for the new TF if not cached
      if (!mApp.candleData[tf] || mApp.candleData[tf].length === 0) {
        // Determine the date to load
        let dateToLoad = mApp.currentDate;
        if (!dateToLoad && mApp.candleData['5m'] && mApp.candleData['5m'].length > 0) {
          const firstBar = mApp.candleData['5m'][0];
          dateToLoad = (firstBar.time || '').substring(0, 10);
        }
        if (!dateToLoad) dateToLoad = new Date().toISOString().substring(0, 10);

        // HTF (1H, 4H, 1D): load 10-day range for seamless scrolling
        // LTF (1m, 5m, 15m): load single day (WS push handles updates)
        var fetchUrl;
        if (isHTF(tf)) {
          var endDate = dateToLoad;
          var startD = new Date(dateToLoad + 'T12:00:00Z');
          var lookback = tf === '1D' ? 59 : tf === '4H' ? 29 : 9;
          startD.setUTCDate(startD.getUTCDate() - lookback);
          var startDate = startD.toISOString().split('T')[0];
          fetchUrl = '/api/bars-range?start=' + startDate + '&end=' + endDate + '&tf=' + tf;
        } else {
          fetchUrl = '/api/bars/' + dateToLoad + '?tf=' + tf;
        }

        fetch(fetchUrl)
          .then(r => r.ok ? r.json() : null)
          .then(data => {
            if (data && data.data) {
              mApp.candleData[tf] = data.data;
            }
            if (typeof refreshMirrorChart === 'function') refreshMirrorChart();
          })
          .catch(() => {
            if (typeof refreshMirrorChart === 'function') refreshMirrorChart();
          });
      } else {
        if (typeof refreshMirrorChart === 'function') refreshMirrorChart();
      }
    });
    container.appendChild(btn);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * UI Rendering — Primitive Toggles
 * ═══════════════════════════════════════════════════════════════════════════════ */

function initPrimitiveToggles() {
  mApp.primitiveToggles = {};
  for (const p of M_PRIMITIVES) {
    mApp.primitiveToggles[p.key] = true;
  }
}

function renderPrimitiveToggles() {
  const container = document.getElementById('prim-toggles');
  if (!container) return;
  container.innerHTML = '';

  for (const p of M_PRIMITIVES) {
    const isOn = mApp.primitiveToggles[p.key] !== false;
    const btn = document.createElement('button');
    btn.className = 'prim-toggle' + (isOn ? ' active' : '');
    btn.dataset.primitive = p.key;
    btn.innerHTML = `<span class="prim-swatch" style="background:${isOn ? p.color : 'var(--faint)'}"></span>${p.label}`;
    btn.addEventListener('click', function () {
      mApp.primitiveToggles[p.key] = !mApp.primitiveToggles[p.key];
      _savePreferences();
      renderPrimitiveToggles();
      if (typeof refreshMirrorChart === 'function') refreshMirrorChart();
    });
    container.appendChild(btn);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * UI Rendering — Session Legend
 * ═══════════════════════════════════════════════════════════════════════════════ */

function renderSessionLegend() {
  const container = document.getElementById('session-legend');
  if (!container) return;
  let html = '';
  for (const s of M_SESSION_META) {
    html += `<span class="session-legend-item">
      <span class="session-swatch" style="background:${s.color}"></span>
      <span>${s.label}</span>
    </span>`;
  }
  container.innerHTML = html;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * UI Rendering — Metadata Bar
 * ═══════════════════════════════════════════════════════════════════════════════ */

function updateMetadata() {
  const dateEl = document.getElementById('meta-date');
  const modeEl = document.getElementById('meta-mode');
  const detsEl = document.getElementById('meta-detections');
  const connEl = document.getElementById('meta-connection');

  if (dateEl) {
    dateEl.textContent = mApp.currentDate
      ? dayLabel(mApp.currentDate)
      : 'Today';
  }

  if (modeEl) {
    modeEl.textContent = mApp.mode === 'live' ? 'LIVE' : 'HISTORICAL';
  }

  if (detsEl) {
    let count = 0;
    if (mApp.detectionData && mApp.detectionData.detections_by_primitive) {
      for (const [prim, byTf] of Object.entries(mApp.detectionData.detections_by_primitive)) {
        if (mApp.primitiveToggles[prim] === false) continue;
        const arr = byTf[mApp.tf] || byTf['global'] || [];
        count += arr.length;
      }
    }
    detsEl.textContent = count.toLocaleString();
  }

  if (connEl) {
    connEl.textContent = mApp.wsConnected ? 'Connected' : 'Disconnected';
  }

  var wsDot = document.getElementById('ws-dot');
  if (wsDot) {
    wsDot.classList.remove('connected', 'disconnected');
    wsDot.classList.add(mApp.wsConnected ? 'connected' : 'disconnected');
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * UI Rendering — WorldState Banner
 * ═══════════════════════════════════════════════════════════════════════════════ */

function updateWorldStateBanner() {
  const banner = document.getElementById('worldstate-banner');
  if (!banner || !mApp.worldState) return;
  const ws = mApp.worldState;
  banner.className = 'phase-' + (ws.htf_phase || 'unclear').toLowerCase();
  // Show fields, hide waiting text
  const waiting = banner.querySelector('.ws-waiting');
  const fields = banner.querySelector('.ws-fields');
  if (waiting) waiting.style.display = 'none';
  if (fields) fields.style.display = '';
  // Update individual fields
  const phaseEl = document.getElementById('ws-phase');
  const permEl = document.getElementById('ws-permission');
  const authEl = document.getElementById('ws-authority');
  const dirEl = document.getElementById('ws-direction');
  const mechEl = document.getElementById('ws-mechanism');

  if (phaseEl) phaseEl.textContent = ws.htf_phase || '—';
  if (permEl) permEl.textContent = ws.direction_permission || '—';
  if (authEl) authEl.textContent = ws.authority_tf || '—';
  if (dirEl) dirEl.textContent = ws.daily_direction || '—';
  if (mechEl) mechEl.textContent = 'mech' + (ws.mechanism_used || '0');
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * UI Rendering — Live Badge
 * ═══════════════════════════════════════════════════════════════════════════════ */

/**
 * Update the live badge indicator.
 * @param {'live'|'closed'|'connecting'|'disconnected'} state
 */
function updateLiveBadge(newState) {
  const badge = document.getElementById('live-badge');
  if (!badge) return;

  // Remove all state classes (CSS uses these unprefixed names)
  badge.classList.remove('live', 'closed', 'connecting', 'disconnected');

  // Rebuild inner HTML to preserve the dot + text structure
  switch (newState) {
    case 'live':
      badge.className = 'live';
      badge.innerHTML = '<span class="live-dot"></span><span class="live-text">LIVE</span>';
      break;
    case 'closed':
      badge.className = 'closed';
      badge.innerHTML = '<span class="live-dot"></span><span class="live-text">MARKET CLOSED</span>';
      break;
    case 'connecting':
      badge.className = 'connecting';
      badge.innerHTML = '<span class="live-dot"></span><span class="live-text">CONNECTING</span>';
      break;
    case 'disconnected':
    default:
      badge.className = 'disconnected';
      badge.innerHTML = '<span class="live-dot"></span><span class="live-text">DISCONNECTED</span>';
      break;
  }
  badge.id = 'live-badge';
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Persistent Preferences (localStorage)
 * ═══════════════════════════════════════════════════════════════════════════════ */

const _PREFS_KEY = 'mirror_prefs';

function _loadPreferences() {
  try {
    const raw = localStorage.getItem(_PREFS_KEY);
    if (!raw) return;
    const prefs = JSON.parse(raw);
    if (prefs.tf && M_TF_OPTIONS.includes(prefs.tf)) mApp.tf = prefs.tf;
    if (prefs.primitiveToggles && typeof prefs.primitiveToggles === 'object') {
      mApp.primitiveToggles = prefs.primitiveToggles;
    }
  } catch (_) { /* ignore corrupt prefs */ }
}

function _savePreferences() {
  try {
    localStorage.setItem(_PREFS_KEY, JSON.stringify({
      tf: mApp.tf,
      primitiveToggles: mApp.primitiveToggles,
    }));
  } catch (_) { /* storage full or blocked */ }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Keyboard Shortcuts (TradingView-style)
 * ═══════════════════════════════════════════════════════════════════════════════ */

function setupKeyboardShortcuts() {
  const tfMap = { '1': '1m', '2': '5m', '3': '15m', '4': '1H', '5': '4H', '6': '1D' };

  document.addEventListener('keydown', function (e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;

    if (tfMap[e.key]) {
      const newTf = tfMap[e.key];
      if (newTf !== mApp.tf) {
        mApp.tf = newTf;
        _savePreferences();
        renderTFButtons();
        const btn = document.querySelector(`.tf-btn[data-tf="${newTf}"]`);
        if (btn) btn.click();
      }
      e.preventDefault();
      return;
    }

    if (e.key === 'ArrowLeft' && mApp.chart) {
      mApp.chart.timeScale().scrollToPosition(-3, false);
      e.preventDefault();
    } else if (e.key === 'ArrowRight' && mApp.chart) {
      mApp.chart.timeScale().scrollToPosition(3, false);
      e.preventDefault();
    } else if ((e.key === '+' || e.key === '=') && mApp.chart) {
      mApp.chart.timeScale().applyOptions({ barSpacing: (mApp.chart.timeScale().options().barSpacing || 6) + 2 });
      e.preventDefault();
    } else if (e.key === '-' && mApp.chart) {
      const curr = mApp.chart.timeScale().options().barSpacing || 6;
      mApp.chart.timeScale().applyOptions({ barSpacing: Math.max(1, curr - 2) });
      e.preventDefault();
    }
  });
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Day Tabs — Forex Day Navigation
 * ═══════════════════════════════════════════════════════════════════════════════ */

let _mScrollSyncActive = false;

function deriveForexDays() {
  const raw = mApp.candleData[mApp.tf];
  if (!raw || !raw.length) { mApp.forexDays = []; return; }

  const seen = new Set();
  for (const bar of raw) {
    const fd = getForexDay(bar.time);
    if (fd) seen.add(fd);
  }
  mApp.forexDays = Array.from(seen).sort();
}

function renderDayTabs() {
  const container = document.getElementById('day-tabs');
  if (!container) return;

  deriveForexDays();

  if (mApp.forexDays.length <= 1) {
    container.style.display = 'none';
    return;
  }

  container.style.display = '';
  container.innerHTML = '';

  for (const fd of mApp.forexDays) {
    const btn = document.createElement('button');
    btn.className = 'day-tab' + (mApp.day === fd ? ' active' : '');
    btn.textContent = dayLabel(fd);
    btn.dataset.day = fd;
    btn.addEventListener('click', function () {
      mApp.day = fd;
      renderDayTabs();
      _mScrollSyncActive = true;
      if (mApp.chart) {
        mApp.chart.timeScale().setVisibleRange(_mDayRange(fd));
      }
      setTimeout(function () { _mScrollSyncActive = false; }, 300);
    });
    container.appendChild(btn);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * State Timeline — WorldState Snapshot Display
 * ═══════════════════════════════════════════════════════════════════════════════ */

function renderStateTimeline() {
  const container = document.getElementById('state-timeline');
  if (!container) return;

  const snapshots = mApp.worldStateSnapshots;
  if (!snapshots || snapshots.length === 0) {
    container.style.display = 'none';
    return;
  }

  container.style.display = '';
  let html = '<span class="st-label">State</span>';

  for (const snap of snapshots) {
    const phase = (snap.htf_phase || 'unclear').toLowerCase();
    const time = snap.computed_at || snap.time || '';
    const timeStr = time ? new Date(time).toTimeString().slice(0, 5) : '';
    const title = `${phase.toUpperCase()} at ${timeStr}\nDir: ${snap.direction_permission || '—'}\nAuth: ${snap.authority_tf || '—'}`;
    html += `<span class="st-dot ${phase}" title="${title}"></span>`;
  }

  container.innerHTML = html;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Five-Factor Dashboard Row
 * ═══════════════════════════════════════════════════════════════════════════════ */

function updateFiveFactorRow() {
  const container = document.getElementById('five-factor-row');
  if (!container) return;

  const dets = mApp.detectionData;
  if (!dets || !dets.diagnostic_signals || dets.diagnostic_signals.length === 0) {
    container.style.display = 'none';
    return;
  }

  const latest = dets.diagnostic_signals[dets.diagnostic_signals.length - 1];
  const factors = latest.factors || latest.five_factors || {};
  const dir = latest.direction || '';
  const dirColor = dir === 'bullish' ? 'var(--teal)' : dir === 'bearish' ? 'var(--red)' : 'var(--muted)';

  const ck = (key) => {
    const v = factors[key] ?? factors['f' + key.slice(-1)];
    if (v === true || v === 1) return '<span class="ff-item ff-pass">✓</span>';
    if (v === false || v === 0) return '<span class="ff-item ff-fail">✗</span>';
    return '<span class="ff-item ff-na">—</span>';
  };

  const f = (label, key) => `<span style="color:var(--muted);font-size:10px;">${label}</span> ${ck(key)}`;

  container.style.display = '';
  container.innerHTML =
    `<span class="ff-label">Checklist</span>` +
    `<span style="color:${dirColor};font-weight:600;font-size:11px;">${(dir || '—').toUpperCase()}</span>` +
    `<span style="color:var(--faint);">|</span>` +
    f('F1 Bias', 'f1') + ' ' + f('F2 Liq', 'f2') + ' ' + f('F3 Struct', 'f3') + ' ' +
    f('F4 PDA', 'f4') + ' ' + f('F5 Target', 'f5');
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Week Picker + Extended HTF Loading
 * ═══════════════════════════════════════════════════════════════════════════════ */

async function setupWeekPicker() {
  const picker = document.getElementById('week-picker');
  if (!picker) return;

  try {
    const resp = await fetch('/api/weeks');
    if (!resp.ok) return;
    const data = await resp.json();
    const weeks = data.weeks || [];

    picker.innerHTML = '<option value="">— Week —</option>';
    for (const w of weeks.reverse()) {
      const label = w.start + ' → ' + w.end + ' (' + w.detection_count + 'd)';
      const opt = document.createElement('option');
      opt.value = w.start + '|' + w.end;
      opt.textContent = label;
      picker.appendChild(opt);
    }

    picker.addEventListener('change', function () {
      const val = picker.value;
      if (!val) return;
      const [start, end] = val.split('|');
      loadWeekRange(start, end);
    });
  } catch (e) {
    console.warn('[MIRROR] Failed to load week manifest:', e);
  }
}

async function loadWeekRange(startDate, endDate) {
  mApp.mode = 'historical';
  mApp.currentDate = startDate;
  disconnectWS();
  updateLiveBadge('disconnected');

  const loading = document.getElementById('loading-overlay');
  if (loading) loading.classList.remove('hidden');

  try {
    const tf = mApp.tf;
    const [barsResp, sessResp] = await Promise.all([
      fetch(`/api/bars-range?start=${startDate}&end=${endDate}&tf=${tf}`),
      fetch(`/api/sessions-range?start=${startDate}&end=${endDate}`),
    ]);

    if (barsResp.ok) {
      const barsData = await barsResp.json();
      mApp.candleData[tf] = barsData.data || [];
    }

    if (sessResp.ok) {
      const sessData = await sessResp.json();
      mApp.sessionData = sessData.sessions || [];
    }

    // Load detections for each day in the range
    const dStart = new Date(startDate + 'T12:00:00Z');
    const dEnd = new Date(endDate + 'T12:00:00Z');
    const merged = { detections_by_primitive: {}, diagnostic_signals: [] };
    const d = new Date(dStart);
    while (d <= dEnd) {
      const ds = d.toISOString().split('T')[0];
      try {
        const dr = await fetch(`/api/detections/${ds}`);
        if (dr.ok) {
          const dd = await dr.json();
          const byPrim = dd.detections_by_primitive || {};
          for (const [prim, byTf] of Object.entries(byPrim)) {
            if (!merged.detections_by_primitive[prim]) merged.detections_by_primitive[prim] = {};
            for (const [tf2, dets] of Object.entries(byTf)) {
              if (!merged.detections_by_primitive[prim][tf2]) merged.detections_by_primitive[prim][tf2] = [];
              merged.detections_by_primitive[prim][tf2].push(...dets);
            }
          }
          if (dd.diagnostic_signals) merged.diagnostic_signals.push(...dd.diagnostic_signals);
        }
      } catch (_) { /* skip failed day */ }
      d.setUTCDate(d.getUTCDate() + 1);
    }
    mApp.detectionData = merged;
  } catch (e) {
    console.error('[MIRROR] Failed to load week range:', e);
  }

  if (loading) loading.classList.add('hidden');
  if (typeof refreshMirrorChart === 'function') refreshMirrorChart();
  if (typeof updateFeedFromDetections === 'function') updateFeedFromDetections(mApp.detectionData);
  updateFiveFactorRow();
  updateSetupSummary();
  renderDayTabs();
  updateMetadata();
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Setup Summary Panel
 * ═══════════════════════════════════════════════════════════════════════════════ */

function updateSetupSummary() {
  const container = document.getElementById('setup-summary');
  if (!container) return;

  const dets = mApp.detectionData;
  if (!dets || !dets.diagnostic_signals || dets.diagnostic_signals.length === 0) {
    container.style.display = 'none';
    return;
  }

  const sigs = dets.diagnostic_signals;
  let bullish = 0, bearish = 0;
  for (const s of sigs) {
    if (s.direction === 'bullish') bullish++;
    else if (s.direction === 'bearish') bearish++;
  }

  container.style.display = '';
  let html = '<div class="setup-summary-title">Setups Today</div>';
  if (bullish > 0) {
    html += `<div class="setup-row"><span class="setup-count" style="color:var(--teal);">${bullish}</span><span class="setup-label">Bullish setup${bullish > 1 ? 's' : ''}</span></div>`;
  }
  if (bearish > 0) {
    html += `<div class="setup-row"><span class="setup-count" style="color:var(--red);">${bearish}</span><span class="setup-label">Bearish setup${bearish > 1 ? 's' : ''}</span></div>`;
  }
  if (bullish === 0 && bearish === 0) {
    html += `<div class="setup-row"><span class="setup-count" style="color:var(--faint);">${sigs.length}</span><span class="setup-label">Signal${sigs.length > 1 ? 's' : ''} (no direction)</span></div>`;
  }
  container.innerHTML = html;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Boot Sequence
 * ═══════════════════════════════════════════════════════════════════════════════ */

(async function boot() {
  _loadPreferences();
  initPrimitiveToggles();
  renderTFButtons();
  renderPrimitiveToggles();
  renderSessionLegend();
  setupDatePicker();
  setupNowButton();
  setupKeyboardShortcuts();
  if (typeof initFeed === 'function') initFeed();
  setupWeekPicker();
  connectWS();
})();
