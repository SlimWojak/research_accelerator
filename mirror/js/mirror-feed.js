/**
 * mirror-feed.js — Detection Feed Sidebar
 *
 * Scrolling list of recent detections and DIAGNOSTIC_SIGNAL entries.
 * Depends on global `mApp` and `toTS()` from mirror-app.js (loaded first).
 * Uses `typeof` guards for optional mirror-chart.js functions.
 */

/* ── Feed State ────────────────────────────────────────────────────────── */

const feedState = {
  items: [],           // Array of feed items (newest first)
  maxItems: 200,       // Max items in feed
  filter: 'all',       // 'all' | primitive key filter
  tfFilter: 'all',     // 'all' | specific TF
  autoScroll: true,    // Auto-scroll to newest
};

/* ── Primitive color map ───────────────────────────────────────────────── */

const PRIMITIVE_COLORS = {
  mss:              '#ffeb3b',
  fvg:              '#26a69a',
  displacement:     '#42a5f5',
  swingpoints:      '#ab47bc',
  orderblock:       '#ff7043',
  liquiditysweep:   '#ef5350',
  ote:              '#7e57c2',
  breaker:          '#66bb6a',
  bos:              '#29b6f6',
  choch:            '#ffa726',
};

function primitiveColor(type) {
  if (!type) return '#787b86';
  return PRIMITIVE_COLORS[type.toLowerCase()] || '#787b86';
}

/* ── Unique ID generator ───────────────────────────────────────────────── */

let _feedIdCounter = 0;
function feedUID() {
  _feedIdCounter += 1;
  return 'fi-' + Date.now().toString(36) + '-' + _feedIdCounter;
}

/* ── Helpers ───────────────────────────────────────────────────────────── */

function hhMM(isoTime) {
  try {
    const d = new Date(isoTime);
    if (isNaN(d.getTime())) return '--:--';
    return d.toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour12: false, hour: '2-digit', minute: '2-digit' });
  } catch (_) {
    return '--:--';
  }
}

function directionArrow(dir) {
  if (!dir) return '';
  const d = dir.toLowerCase();
  if (d === 'bullish') return '↑';
  if (d === 'bearish') return '↓';
  return '–';
}

function directionClass(dir) {
  if (!dir) return 'neutral';
  const d = dir.toLowerCase();
  if (d === 'bullish') return 'bullish';
  if (d === 'bearish') return 'bearish';
  return 'neutral';
}

/* ── Extract key detail per primitive type ──────────────────────────────── */

function extractDetail(type, det) {
  if (!det) return '';
  const key = (type || '').toLowerCase();

  try {
    switch (key) {
      case 'mss': {
        const price = det.break_price ?? det.breakPrice ?? det.price ?? '';
        const dir   = det.direction ?? '';
        return price ? 'break=' + Number(price).toFixed(5) + (dir ? ' ' + dir : '') : (dir || '');
      }
      case 'fvg': {
        const top   = det.top ?? det.zone_top ?? (det.zone && det.zone[0]) ?? '';
        const bot   = det.bottom ?? det.zone_bottom ?? (det.zone && det.zone[1]) ?? '';
        const state = det.state ?? det.status ?? '';
        const zone  = (top !== '' && bot !== '') ? 'zone=[' + Number(top).toFixed(5) + ', ' + Number(bot).toFixed(5) + ']' : '';
        return zone + (state ? ' ' + state : '');
      }
      case 'displacement': {
        const body = det.body_ratio ?? det.body ?? det.ratio ?? '';
        const dir  = det.direction ?? '';
        return (body !== '' ? 'body=' + (typeof body === 'number' ? body.toFixed(2) : body) : '') + (dir ? ' ' + dir : '');
      }
      case 'swingpoints': {
        const price = det.price ?? det.level ?? '';
        const hl    = det.type ?? det.swing_type ?? '';
        return (price !== '' ? 'price=' + Number(price).toFixed(5) : '') + (hl ? ' ' + hl : '');
      }
      case 'orderblock': {
        const top = det.top ?? det.zone_top ?? (det.zone && det.zone[0]) ?? '';
        const bot = det.bottom ?? det.zone_bottom ?? (det.zone && det.zone[1]) ?? '';
        return (top !== '' && bot !== '') ? 'zone=[' + Number(top).toFixed(5) + ', ' + Number(bot).toFixed(5) + ']' : '';
      }
      case 'liquiditysweep': {
        const level = det.level ?? det.price ?? '';
        return level !== '' ? 'level=' + Number(level).toFixed(5) : '';
      }
      case 'ote': {
        const z618 = det.fib_618 ?? det.zone_618 ?? (det.zone && det.zone[0]) ?? 0.618;
        const z79  = det.fib_79  ?? det.zone_79  ?? (det.zone && det.zone[1]) ?? 0.79;
        return 'zone=[' + Number(z618).toFixed(3) + ', ' + Number(z79).toFixed(3) + ']';
      }
      default: {
        return det.direction ?? '';
      }
    }
  } catch (_) {
    return '';
  }
}

/* ── Feed Item Factory ─────────────────────────────────────────────────── */

function makeFeedItem(type, tf, det) {
  const direction = det.direction ?? det.dir ?? '';
  const time      = det.time ?? det.timestamp ?? det.t ?? new Date().toISOString();
  const label     = (type.toUpperCase()) + ' ' + tf + (direction ? ' ' + direction.toUpperCase() : '');
  const detail    = extractDetail(type, det);

  return {
    id:         feedUID(),
    time:       time,
    type:       type.toLowerCase(),
    tf:         tf,
    direction:  direction.toLowerCase(),
    label:      label,
    detail:     detail,
    isSignal:   false,
    signalData: null,
    color:      primitiveColor(type),
  };
}

/* ── Add detections to feed ────────────────────────────────────────────── */

/**
 * detections format: { detections_by_primitive: { type: { tf: [...] } } }
 */
function addDetectionsToFeed(detections) {
  if (!detections) return;

  const byPrim = detections.detections_by_primitive || detections;
  const newItems = [];

  for (const type of Object.keys(byPrim)) {
    const tfMap = byPrim[type];
    if (!tfMap || typeof tfMap !== 'object') continue;

    for (const tf of Object.keys(tfMap)) {
      const dets = tfMap[tf];
      if (!Array.isArray(dets)) continue;

      for (const det of dets) {
        newItems.push(makeFeedItem(type, tf, det));
      }
    }
  }

  // Sort newest first
  newItems.sort(function (a, b) {
    return new Date(b.time).getTime() - new Date(a.time).getTime();
  });

  // Prepend to items list
  feedState.items = newItems.concat(feedState.items);

  // Enforce max items
  if (feedState.items.length > feedState.maxItems) {
    feedState.items = feedState.items.slice(0, feedState.maxItems);
  }

  renderFeed();
}

/* ── Add signals to feed ───────────────────────────────────────────────── */

function addSignalsToFeed(signals) {
  if (!signals || !Array.isArray(signals)) return;

  const newItems = [];

  for (const sig of signals) {
    const model   = sig.model_type  ?? sig.modelType ?? 'SIGNAL';
    const dir     = sig.direction   ?? sig.dir       ?? '';
    const factors = sig.factors     ?? sig.five_factors ?? {};

    const f1 = factors.f1 ?? factors.bias       ?? false;
    const f2 = factors.f2 ?? factors.liquidity  ?? false;
    const f3 = factors.f3 ?? factors.structure   ?? false;
    const f4 = factors.f4 ?? factors.pda         ?? false;
    const f5 = factors.f5 ?? factors.target      ?? false;

    const ck = function (v) { return v ? '✓' : '✗'; };

    const detail = model + ' ' + (dir ? dir.toUpperCase() + ' ' : '') +
      '[F1:' + ck(f1) + ' F2:' + ck(f2) + ' F3:' + ck(f3) + ' F4:' + ck(f4) + ' F5:' + ck(f5) + ']';

    const time = sig.time ?? sig.timestamp ?? new Date().toISOString();
    const tf   = sig.tf   ?? sig.timeframe ?? '';

    newItems.push({
      id:         feedUID(),
      time:       time,
      type:       'signal',
      tf:         tf,
      direction:  (dir || '').toLowerCase(),
      label:      'SIGNAL ' + (tf ? tf + ' ' : '') + (dir ? dir.toUpperCase() : ''),
      detail:     detail,
      isSignal:   true,
      signalData: sig,
      color:      '#f7c548',
    });
  }

  // Sort newest first
  newItems.sort(function (a, b) {
    return new Date(b.time).getTime() - new Date(a.time).getTime();
  });

  feedState.items = newItems.concat(feedState.items);

  if (feedState.items.length > feedState.maxItems) {
    feedState.items = feedState.items.slice(0, feedState.maxItems);
  }

  renderFeed();
}

/* ── Render Feed ───────────────────────────────────────────────────────── */

function renderFeed() {
  var listEl = document.getElementById('feed-list');
  if (!listEl) return;

  // Apply filters
  var visible = feedState.items.filter(function (item) {
    if (feedState.filter !== 'all' && item.type !== feedState.filter) return false;
    if (feedState.tfFilter !== 'all' && item.tf !== feedState.tfFilter) return false;
    return true;
  });

  if (visible.length === 0) {
    listEl.innerHTML =
      '<div class="feed-empty">' +
        '<div class="feed-empty-icon">◇</div>' +
        '<div>No detections yet</div>' +
        '<div style="font-size: 10px; color: var(--faint);">Detections appear here in real time</div>' +
      '</div>';
    return;
  }

  var html = '';
  for (var i = 0; i < visible.length; i++) {
    var item = visible[i];
    html += buildFeedItemHTML(item);
  }
  listEl.innerHTML = html;

  // Attach click listeners
  var rows = listEl.querySelectorAll('.feed-item');
  for (var j = 0; j < rows.length; j++) {
    (function (row) {
      row.addEventListener('click', function () {
        var id = row.getAttribute('data-id');
        var matched = feedState.items.find(function (it) { return it.id === id; });
        if (matched) onFeedItemClick(matched);
      });
    })(rows[j]);
  }

  // Auto-scroll to top (newest)
  if (feedState.autoScroll) {
    listEl.scrollTop = 0;
  }
}

/* ── Build single feed item HTML ───────────────────────────────────────── */

function buildFeedItemHTML(item) {
  var dirCls     = directionClass(item.direction);
  var arrow      = directionArrow(item.direction);
  var timeStr    = hhMM(item.time);
  var signalCls  = item.isSignal ? ' feed-item-signal' : '';

  // Direction color
  var dirColor = '#787b86';
  if (dirCls === 'bullish') dirColor = '#26a69a';
  if (dirCls === 'bearish') dirColor = '#ef5350';

  // Signal items get gold left border
  var signalBorder = item.isSignal
    ? 'border-left: 3px solid #f7c548; padding-left: 11px;'
    : '';

  var signalSize = item.isSignal ? ' font-size: 12px;' : '';

  var html =
    '<div class="feed-item' + signalCls + '" data-id="' + item.id + '" data-time="' + item.time + '"' +
    ' style="' + signalBorder + signalSize + '">' +
      '<span class="feed-swatch" style="' +
        'display:inline-block;width:10px;height:10px;border-radius:2px;flex-shrink:0;margin-top:3px;' +
        'background:' + item.color + ';"></span>' +
      '<span class="feed-time" style="' +
        'font-family:var(--mono);font-size:10px;color:var(--muted);flex-shrink:0;' +
        '">' + timeStr + '</span>' +
      '<span class="feed-type" style="' +
        'font-family:var(--mono);font-size:10px;font-weight:600;color:var(--text);white-space:nowrap;' +
        '">' + item.type.toUpperCase() + ' ' + item.tf + '</span>' +
      '<span class="feed-dir feed-dir-' + dirCls + '" style="' +
        'font-size:12px;font-weight:700;color:' + dirColor + ';flex-shrink:0;' +
        '">' + arrow + '</span>' +
      '<span class="feed-detail" style="' +
        'font-family:var(--mono);font-size:10px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0;' +
        '">' + escapeHTML(item.detail) + '</span>' +
    '</div>';

  // Signal tooltip (hover-driven via title or custom tooltip)
  if (item.isSignal && item.signalData) {
    html = html.replace(
      'class="feed-item feed-item-signal"',
      'class="feed-item feed-item-signal" onmouseenter="showSignalTooltip(event,\'' + item.id + '\')" onmouseleave="hideSignalTooltip()"'
    );
  }

  return html;
}

function escapeHTML(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/* ── Signal Tooltip ────────────────────────────────────────────────────── */

function showSignalTooltip(event, itemId) {
  var item = feedState.items.find(function (it) { return it.id === itemId; });
  if (!item || !item.signalData) return;

  hideSignalTooltip(); // remove any existing

  var sig     = item.signalData;
  var model   = sig.model_type  ?? sig.modelType ?? 'SIGNAL';
  var dir     = sig.direction   ?? sig.dir       ?? '';
  var factors = sig.factors     ?? sig.five_factors ?? {};
  var pdaType = sig.pda_type    ?? sig.pdaType   ?? '—';
  var confl   = sig.confluence  ?? '';
  var target  = sig.primary_target ?? sig.target  ?? '—';
  var dist    = sig.target_distance ?? sig.distance ?? '';
  var shadow  = sig.shadow_mode ?? sig.shadowMode ?? false;

  var f1 = factors.f1 ?? factors.bias       ?? false;
  var f2 = factors.f2 ?? factors.liquidity  ?? false;
  var f3 = factors.f3 ?? factors.structure   ?? false;
  var f4 = factors.f4 ?? factors.pda         ?? false;
  var f5 = factors.f5 ?? factors.target      ?? false;

  var ck = function (v) { return v ? '<span style="color:#26a69a;">✓</span>' : '<span style="color:#ef5350;">✗</span>'; };

  var tip = document.createElement('div');
  tip.id = 'signal-tooltip';
  tip.style.cssText =
    'position:fixed;z-index:9999;background:#1e222d;border:1px solid #f7c548;border-radius:6px;' +
    'padding:10px 14px;font-size:11px;color:#d1d4dc;pointer-events:none;' +
    'box-shadow:0 4px 16px rgba(0,0,0,0.5);max-width:260px;line-height:1.6;';

  tip.innerHTML =
    '<div style="font-weight:600;margin-bottom:4px;color:#f7c548;">' + escapeHTML(model) + (dir ? ' — ' + dir.toUpperCase() : '') + '</div>' +
    '<div>F1 Bias ' + ck(f1) + '</div>' +
    '<div>F2 Liquidity ' + ck(f2) + '</div>' +
    '<div>F3 Structure ' + ck(f3) + '</div>' +
    '<div>F4 PDA ' + ck(f4) + '</div>' +
    '<div>F5 Target ' + ck(f5) + '</div>' +
    '<div style="margin-top:4px;border-top:1px solid #2a2e39;padding-top:4px;">' +
      '<span style="color:#787b86;">PDA:</span> ' + escapeHTML(String(pdaType)) + (confl ? ' + ' + escapeHTML(String(confl)) : '') +
    '</div>' +
    '<div><span style="color:#787b86;">Target:</span> ' + escapeHTML(String(target)) + (dist ? ' (' + escapeHTML(String(dist)) + ')' : '') + '</div>' +
    (shadow ? '<div style="margin-top:4px;color:#f7c548;font-style:italic;">⚠ Shadow Mode</div>' : '');

  document.body.appendChild(tip);

  // Position near cursor
  var rect = event.target.getBoundingClientRect();
  var x = rect.left - 270;
  if (x < 8) x = rect.right + 8;
  var y = rect.top;
  if (y + tip.offsetHeight > window.innerHeight - 8) {
    y = window.innerHeight - tip.offsetHeight - 8;
  }
  tip.style.left = x + 'px';
  tip.style.top  = y + 'px';
}

function hideSignalTooltip() {
  var tip = document.getElementById('signal-tooltip');
  if (tip) tip.parentNode.removeChild(tip);
}

/* ── Feed Filters ──────────────────────────────────────────────────────── */

function setupFeedFilter() {
  var filterEl = document.getElementById('feed-filter');
  if (!filterEl) return;

  // Rebuild options: "All" + known primitives
  var options = '<option value="all">All</option>';

  var knownTypes = [
    'mss', 'fvg', 'displacement', 'swingpoints',
    'orderblock', 'liquiditysweep', 'ote', 'breaker', 'bos', 'choch', 'signal',
  ];

  // Collect types actually present in feed
  var seen = {};
  for (var i = 0; i < feedState.items.length; i++) {
    seen[feedState.items[i].type] = true;
  }

  for (var j = 0; j < knownTypes.length; j++) {
    var t = knownTypes[j];
    if (seen[t]) {
      options += '<option value="' + t + '">' + t.toUpperCase() + '</option>';
    }
  }

  // Add any unseen types from feed
  for (var k = 0; k < feedState.items.length; k++) {
    var it = feedState.items[k].type;
    if (!seen[it] || knownTypes.indexOf(it) !== -1) continue;
    options += '<option value="' + it + '">' + it.toUpperCase() + '</option>';
  }

  filterEl.innerHTML = options;
  filterEl.value = feedState.filter;

  filterEl.onchange = function () {
    feedState.filter = filterEl.value;
    renderFeed();
  };
}

/* ── Click-to-Navigate ─────────────────────────────────────────────────── */

function onFeedItemClick(item) {
  if (!item || !item.time) return;

  try {
    var ts = typeof toTS === 'function' ? toTS(item.time) : Math.floor(new Date(item.time).getTime() / 1000);

    // Pan chart to detection time
    if (typeof mApp !== 'undefined' && mApp.chart) {
      var rangeSeconds = 300; // 5-min window each side default
      // Adapt range to timeframe
      var tfMinutes = parseTFMinutes(item.tf);
      if (tfMinutes > 0) {
        rangeSeconds = Math.max(tfMinutes * 60 * 10, 300);
      }

      mApp.chart.timeScale().setVisibleRange({
        from: ts - rangeSeconds,
        to:   ts + rangeSeconds,
      });
    }

    // Highlight corresponding marker (flash effect)
    flashFeedItem(item.id);

    // For signals — highlight chain components if available
    if (item.isSignal && item.signalData) {
      if (typeof highlightSignalChain === 'function') {
        highlightSignalChain(item.signalData);
      }
    }
  } catch (e) {
    console.warn('[mirror-feed] onFeedItemClick error:', e);
  }
}

function parseTFMinutes(tf) {
  if (!tf) return 0;
  var s = tf.toLowerCase().trim();
  var m = s.match(/^(\d+)(m|h|d)$/);
  if (!m) return 0;
  var n = parseInt(m[1], 10);
  var unit = m[2];
  if (unit === 'm') return n;
  if (unit === 'h') return n * 60;
  if (unit === 'd') return n * 1440;
  return 0;
}

function flashFeedItem(id) {
  var el = document.querySelector('.feed-item[data-id="' + id + '"]');
  if (!el) return;

  // Mark active
  var prev = document.querySelector('.feed-item.active');
  if (prev) prev.classList.remove('active');

  el.classList.add('active');
  el.style.transition = 'background 0.15s';
  el.style.background = 'rgba(41, 98, 255, 0.25)';

  setTimeout(function () {
    el.style.background = '';
    // keep active class for a while
    setTimeout(function () {
      el.classList.remove('active');
    }, 3000);
  }, 400);
}

/* ── Live Feed Updates ─────────────────────────────────────────────────── */

function onNewBarsReceived() {
  // Called when new bars arrive. New detections (if any) should have been
  // already routed through addDetectionsToFeed / addSignalsToFeed
  // by the caller. This function is a hook for any additional feed refresh.
  // Re-render to update filter dropdown if new types appeared.
  setupFeedFilter();
}

function clearFeed() {
  feedState.items = [];
  feedState.filter = 'all';
  feedState.tfFilter = 'all';
  renderFeed();
  setupFeedFilter();
}

function updateFeedFromDetections(detectionData) {
  // Full rebuild from detection data (historical mode / initial load)
  feedState.items = [];
  addDetectionsToFeed(detectionData);
  setupFeedFilter();
}

/* ── Init ──────────────────────────────────────────────────────────────── */

function initFeed() {
  // Guard: make sure DOM elements exist
  if (!document.getElementById('feed-list')) {
    console.warn('[mirror-feed] #feed-list not found — feed not initialised.');
    return;
  }
  if (!document.getElementById('feed-filter')) {
    console.warn('[mirror-feed] #feed-filter not found — feed not initialised.');
    return;
  }

  // Set up filter dropdown handler
  setupFeedFilter();

  // Wire mobile sidebar toggle
  var toggleBtn = document.getElementById('feed-toggle-btn');
  var feedPanel = document.getElementById('detection-feed');
  if (toggleBtn && feedPanel) {
    toggleBtn.addEventListener('click', function () {
      feedPanel.classList.toggle('visible');
    });
  }

  // TF filter: sync with mApp.tf if available
  if (typeof mApp !== 'undefined' && mApp.tf) {
    feedState.tfFilter = 'all'; // default to all; can be toggled
  }

  // Listen for feed-list scroll to disable auto-scroll when user scrolls up
  var listEl = document.getElementById('feed-list');
  if (listEl) {
    listEl.addEventListener('scroll', function () {
      feedState.autoScroll = (listEl.scrollTop <= 5);
    });
  }

  // Initial render
  renderFeed();

  console.log('[mirror-feed] Feed initialised.');
}
