/* ═══════════════════════════════════════════════════════════════════════════════
 * divergence.js — Divergence Navigator panel within the Chart tab
 *
 * Loads divergence entries from Schema 4C pairwise.{pair}.divergence_index[].
 * Renders a scrollable list panel alongside the chart showing each entry with:
 *   timestamp (formatted), primitive, TF, config detection status.
 * Color-codes entries by type: Config A only, Config B only, or Both.
 * Click-to-scroll: clicking an entry scrolls the LC time scale to that timestamp.
 * Filters by primitive and session. Shows count summary.
 * ═══════════════════════════════════════════════════════════════════════════════ */

/* ── Divergence State ──────────────────────────────────────────────────────── */

let _divEntries = [];          // All divergence entries from Schema 4C
let _divFilteredEntries = [];  // Currently filtered entries
let _divConfigA = '';          // Config A name
let _divConfigB = '';          // Config B name
let _divInitialized = false;

/* ── Session Classification ────────────────────────────────────────────────── */

/**
 * Derive session name from a timestamp string based on NY time hour.
 * Asia: 19:00–00:00, LOKZ: 02:00–05:00, NYOKZ: 07:00–10:00, Other: rest
 */
function getSessionFromTime(timeStr) {
  if (!timeStr) return 'other';
  const clean = timeStr.replace(/[+-]\d{2}:\d{2}$/, '');
  const match = clean.match(/T(\d{2}):(\d{2})/);
  if (!match) return 'other';
  const hour = parseInt(match[1], 10);
  if (hour >= 19) return 'asia';                 // 19:00–23:59
  if (hour < 2) return 'asia';                   // 00:00–01:59 (tail of Asia)
  if (hour >= 2 && hour < 5) return 'lokz';      // 02:00–04:59
  if (hour >= 7 && hour < 10) return 'nyokz';    // 07:00–09:59
  return 'other';
}

/**
 * Format timestamp for display: "Jan 8 09:35"
 */
function fmtDivTime(timeStr) {
  if (!timeStr) return '—';
  const clean = timeStr.replace(/[+-]\d{2}:\d{2}$/, '');
  const d = new Date(clean + (clean.includes('Z') ? '' : 'Z'));
  if (isNaN(d.getTime())) return timeStr.slice(0, 16);
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const mon = months[d.getUTCMonth()];
  const day = d.getUTCDate();
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  return `${mon} ${day} ${hh}:${mm}`;
}

/**
 * Derive detection status label from in_a / in_b flags.
 */
function detectionStatus(inA, inB) {
  if (inA && inB) return 'Both';
  if (inA && !inB) return 'A only';
  if (!inA && inB) return 'B only';
  return '—';
}

/* ── Load Divergence Data ──────────────────────────────────────────────────── */

/**
 * Load divergence entries from Schema 4C pairwise data.
 * Returns array of entries with added session field.
 */
function loadDivergenceEntries() {
  if (!app.evalData || !app.evalData.pairwise) return [];

  const pairwise = app.evalData.pairwise;
  const pairKeys = Object.keys(pairwise);
  if (pairKeys.length === 0) return [];

  // Use the first (and typically only) pairwise comparison
  const pairKey = pairKeys[0];
  const pairData = pairwise[pairKey];
  if (!pairData || !pairData.divergence_index) return [];

  // Extract config names from the pair key or pairData
  _divConfigA = pairData.config_a || '';
  _divConfigB = pairData.config_b || '';

  // If config names not in pairData, try to parse from key
  if (!_divConfigA && pairKey.includes('__vs__')) {
    const parts = pairKey.split('__vs__');
    _divConfigA = parts[0] || '';
    _divConfigB = parts[1] || '';
  }

  // Add session field to each entry
  return pairData.divergence_index.map(entry => ({
    ...entry,
    session: getSessionFromTime(entry.time),
    _status: detectionStatus(entry.in_a, entry.in_b),
  }));
}

/* ── Filter Logic ──────────────────────────────────────────────────────────── */

/**
 * Apply current filter state and return filtered entries.
 */
function filterDivergenceEntries(entries, primitiveFilter, sessionFilter) {
  let filtered = entries;

  if (primitiveFilter && primitiveFilter !== 'All') {
    filtered = filtered.filter(e => e.primitive === primitiveFilter);
  }

  if (sessionFilter && sessionFilter !== 'All') {
    filtered = filtered.filter(e => e.session === sessionFilter);
  }

  return filtered;
}

/**
 * Compute count summary for a set of entries.
 */
function computeDivCounts(entries) {
  let total = entries.length;
  let onlyA = 0;
  let onlyB = 0;
  let both = 0;

  for (const e of entries) {
    if (e.in_a && e.in_b) both++;
    else if (e.in_a && !e.in_b) onlyA++;
    else if (!e.in_a && e.in_b) onlyB++;
  }

  return { total, onlyA, onlyB, both };
}

/* ── Click-to-Scroll ───────────────────────────────────────────────────────── */

/**
 * Scroll the chart time scale to center on the given timestamp.
 */
function scrollChartToTime(timeStr) {
  if (!app.chart) return;

  const ts = toTS(timeStr.replace(/[+-]\d{2}:\d{2}$/, ''));
  if (ts == null) return;

  const timeScale = app.chart.timeScale();

  // Get the visible range to compute the width in seconds
  const visRange = timeScale.getVisibleRange();
  if (visRange) {
    const rangeSec = visRange.to - visRange.from;
    const halfRange = rangeSec / 2;
    timeScale.setVisibleRange({
      from: ts - halfRange,
      to: ts + halfRange,
    });
  } else {
    // Fallback: scroll to logical range around the timestamp
    timeScale.setVisibleRange({
      from: ts - 3600,
      to: ts + 3600,
    });
  }
}

/* ── Render Divergence Panel ───────────────────────────────────────────────── */

/**
 * Get unique primitive values from entries for the filter dropdown.
 */
function getUniquePrimitives(entries) {
  const s = new Set(entries.map(e => e.primitive).filter(Boolean));
  return Array.from(s).sort();
}

/**
 * Get unique session values from entries for the filter dropdown.
 */
function getUniqueSessions(entries) {
  const s = new Set(entries.map(e => e.session).filter(Boolean));
  return Array.from(s).sort();
}

/**
 * Get the color class/style for an entry based on its detection status.
 * Config A color for in_a-only, Config B color for in_b-only, neutral for both.
 */
function getDivEntryColor(entry) {
  if (entry.in_a && !entry.in_b) return CONFIG_COLORS[0].base;  // Config A teal
  if (!entry.in_a && entry.in_b) return CONFIG_COLORS[1].base;  // Config B amber
  return 'var(--muted)';  // Both — neutral
}

function getDivEntryBg(entry) {
  if (entry.in_a && !entry.in_b) return CONFIG_COLORS[0].fillLight;
  if (!entry.in_a && entry.in_b) return CONFIG_COLORS[1].fillLight;
  return 'transparent';
}

/**
 * Render the full divergence navigator panel into the given container element.
 */
function renderDivergencePanel(container) {
  if (!container) return;

  // Load entries if not already loaded
  if (_divEntries.length === 0 && app.evalData) {
    _divEntries = loadDivergenceEntries();
  }

  // Get current filter values
  const primSelect = document.getElementById('div-prim-filter');
  const sesSelect = document.getElementById('div-session-filter');
  const primFilter = primSelect ? primSelect.value : 'All';
  const sesFilter = sesSelect ? sesSelect.value : 'All';

  // Apply filters
  _divFilteredEntries = filterDivergenceEntries(_divEntries, primFilter, sesFilter);

  // Compute counts
  const counts = computeDivCounts(_divFilteredEntries);

  // Get unique values for filters
  const uniquePrims = getUniquePrimitives(_divEntries);
  const uniqueSessions = getUniqueSessions(_divEntries);

  // Session display labels
  const sessionLabels = {
    asia: 'Asia',
    lokz: 'LOKZ',
    nyokz: 'NYOKZ',
    other: 'Other',
  };

  // Build HTML
  let html = '';

  // Header
  html += '<div class="div-panel-header">';
  html += '<span class="div-panel-title">Divergences</span>';
  html += '</div>';

  // Count summary
  html += '<div class="div-count-summary">';
  html += `<span class="div-count-item div-count-total">Total: <strong>${counts.total}</strong></span>`;
  html += `<span class="div-count-item div-count-a" style="color:${CONFIG_COLORS[0].base}">A only: <strong>${counts.onlyA}</strong></span>`;
  html += `<span class="div-count-item div-count-b" style="color:${CONFIG_COLORS[1].base}">B only: <strong>${counts.onlyB}</strong></span>`;
  html += '</div>';

  // Filters
  html += '<div class="div-filters">';

  // Primitive filter
  html += '<div class="div-filter-group">';
  html += '<label class="div-filter-label" for="div-prim-filter">Primitive</label>';
  html += '<select id="div-prim-filter" class="div-filter-select">';
  html += `<option value="All"${primFilter === 'All' ? ' selected' : ''}>All</option>`;
  for (const p of uniquePrims) {
    html += `<option value="${p}"${primFilter === p ? ' selected' : ''}>${primLabel(p)}</option>`;
  }
  html += '</select>';
  html += '</div>';

  // Session filter
  html += '<div class="div-filter-group">';
  html += '<label class="div-filter-label" for="div-session-filter">Session</label>';
  html += '<select id="div-session-filter" class="div-filter-select">';
  html += `<option value="All"${sesFilter === 'All' ? ' selected' : ''}>All</option>`;
  for (const s of uniqueSessions) {
    const label = sessionLabels[s] || capitalize(s);
    html += `<option value="${s}"${sesFilter === s ? ' selected' : ''}>${label}</option>`;
  }
  html += '</select>';
  html += '</div>';

  html += '</div>';

  // Entry list — limit DOM nodes for performance with large divergence sets
  const DIV_RENDER_LIMIT = 500;
  const totalFiltered = _divFilteredEntries.length;
  const renderCount = Math.min(totalFiltered, DIV_RENDER_LIMIT);

  html += '<div class="div-entry-list" id="div-entry-list">';

  if (totalFiltered === 0) {
    html += '<div class="div-empty">No divergences</div>';
  } else {
    if (totalFiltered > DIV_RENDER_LIMIT) {
      html += `<div class="div-limit-notice">Showing ${DIV_RENDER_LIMIT} of ${totalFiltered} — use filters to narrow</div>`;
    }
    for (let i = 0; i < renderCount; i++) {
      const entry = _divFilteredEntries[i];
      const entryColor = getDivEntryColor(entry);
      const entryBg = getDivEntryBg(entry);

      html += `<div class="div-entry" data-idx="${i}" style="border-left-color:${entryColor};background:${entryBg}">`;
      html += `<div class="div-entry-top">`;
      html += `<span class="div-entry-time">${fmtDivTime(entry.time)}</span>`;
      html += `<span class="div-entry-status" style="color:${entryColor}">${entry._status}</span>`;
      html += `</div>`;
      html += `<div class="div-entry-bottom">`;
      html += `<span class="div-entry-prim">${primLabel(entry.primitive)}</span>`;
      html += `<span class="div-entry-tf">${entry.tf}</span>`;
      html += `</div>`;
      html += `</div>`;
    }
  }

  html += '</div>';

  container.innerHTML = html;

  // Attach event listeners to filter dropdowns
  const newPrimSelect = document.getElementById('div-prim-filter');
  const newSesSelect = document.getElementById('div-session-filter');

  if (newPrimSelect) {
    newPrimSelect.addEventListener('change', () => {
      renderDivergencePanel(container);
    });
  }

  if (newSesSelect) {
    newSesSelect.addEventListener('change', () => {
      renderDivergencePanel(container);
    });
  }

  // Attach click handlers to entries
  const entryEls = container.querySelectorAll('.div-entry');
  entryEls.forEach(el => {
    el.addEventListener('click', () => {
      const idx = parseInt(el.dataset.idx, 10);
      const entry = _divFilteredEntries[idx];
      if (entry) {
        scrollChartToTime(entry.time);

        // Highlight the clicked entry
        entryEls.forEach(e => e.classList.remove('div-entry-active'));
        el.classList.add('div-entry-active');
      }
    });
  });
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * initDivergencePanel — called by chart-tab.js after chart is created
 * ═══════════════════════════════════════════════════════════════════════════════ */

function initDivergencePanel() {
  if (_divInitialized) return;
  _divInitialized = true;

  // Load entries
  _divEntries = loadDivergenceEntries();

  // Render into the divergence panel container
  const container = document.getElementById('divergence-panel');
  if (container) {
    renderDivergencePanel(container);
  }
}
