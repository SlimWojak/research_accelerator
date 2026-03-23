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
  signals: [],             // DIAGNOSTIC_SIGNAL array

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
  { key: 'swing_points',      label: 'Swing Points',  color: '#00bcd4' },
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
      // Normalize: ensure detections_by_primitive wrapper exists
      if (rawDet.detections_by_primitive) {
        mApp.detectionData = rawDet;
      } else {
        mApp.detectionData = { detections_by_primitive: rawDet };
      }
      if (typeof refreshMirrorChart === 'function') refreshMirrorChart();
      if (typeof updateFeedFromDetections === 'function') updateFeedFromDetections(mApp.detectionData);
      break;
    }

    case 'world_state':
      mApp.worldState = msg.data || msg;
      updateWorldStateBanner();
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
    const [barsResp, detsResp] = await Promise.all([
      fetch(`/api/bars/${dateStr}?tf=${mApp.tf}`),
      fetch(`/api/detections/${dateStr}`),
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
  if (!picker) return;

  picker.addEventListener('change', function () {
    const val = picker.value;
    if (!val) return;
    switchToHistorical(val);
  });
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
      renderTFButtons();

      // Fetch bars for the new TF if not cached
      if (!mApp.candleData[tf] || mApp.candleData[tf].length === 0) {
        // Determine the date to load — use current date or detect from existing bar data
        let dateToLoad = mApp.currentDate;
        if (!dateToLoad && mApp.candleData['5m'] && mApp.candleData['5m'].length > 0) {
          const firstBar = mApp.candleData['5m'][0];
          dateToLoad = (firstBar.time || '').substring(0, 10);
        }
        if (!dateToLoad) dateToLoad = new Date().toISOString().substring(0, 10);
        fetch(`/api/bars/${dateToLoad}?tf=${tf}`)
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
 * Boot Sequence
 * ═══════════════════════════════════════════════════════════════════════════════ */

(async function boot() {
  initPrimitiveToggles();
  renderTFButtons();
  renderPrimitiveToggles();
  renderSessionLegend();
  setupDatePicker();
  setupNowButton();
  connectWS();
})();
