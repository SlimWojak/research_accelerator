/* ═══════════════════════════════════════════════════════════════════════════════
 * stats-tab.js — Stats dashboard: side-by-side config tables, Plotly grouped
 *                bar charts (session distribution), direction split, cascade
 *                funnel chart, pairwise comparison statistics, primitive
 *                selector, and TF indicator.
 * ═══════════════════════════════════════════════════════════════════════════════ */

let _statsInitialized = false;

/* ── Helpers ───────────────────────────────────────────────────────────────── */

/** Get per_primitive.{prim}.per_tf.{tf} data for a config. Returns {} if missing. */
function getStatsTfData(configName, prim, tf) {
  if (!app.evalData || !app.evalData.per_config) return {};
  const cfg = app.evalData.per_config[configName];
  if (!cfg || !cfg.per_primitive) return {};
  const primData = cfg.per_primitive[prim];
  if (!primData || !primData.per_tf) return {};
  return primData.per_tf[tf] || {};
}

/** Get pairwise data for the first pairwise key, or null. */
function getPairwiseData() {
  if (!app.evalData || !app.evalData.pairwise) return null;
  const keys = Object.keys(app.evalData.pairwise);
  if (keys.length === 0) return null;
  return { key: keys[0], data: app.evalData.pairwise[keys[0]] };
}

/** Get pairwise per_primitive.{prim}.per_tf.{tf} data, or null. */
function getPairwiseTfData(prim, tf) {
  const pw = getPairwiseData();
  if (!pw || !pw.data || !pw.data.per_primitive) return null;
  const primData = pw.data.per_primitive[prim];
  if (!primData || !primData.per_tf) return null;
  return primData.per_tf[tf] || null;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Stats Tab Rendering
 * ═══════════════════════════════════════════════════════════════════════════════ */

function initStatsTab() {
  const tabEl = document.getElementById('tab-stats');
  if (!tabEl) return;

  // Build the stats tab DOM structure (always rebuild for fresh state)
  tabEl.innerHTML = buildStatsHTML();

  // Bind primitive selector
  const primSelect = document.getElementById('stats-prim-select');
  if (primSelect) {
    primSelect.value = app.selectedPrimitive;
    primSelect.addEventListener('change', () => {
      app.selectedPrimitive = primSelect.value;
      renderStatsContent();
    });
  }

  // Render initial content
  renderStatsContent();
  _statsInitialized = true;
}

/** Build the static shell HTML for the stats tab */
function buildStatsHTML() {
  return `
    <div class="stats-layout">
      <div class="stats-toolbar">
        <div class="stats-toolbar-left">
          <label class="stats-label" for="stats-prim-select">Primitive</label>
          <select id="stats-prim-select" class="stats-select">
            ${PRIMITIVES.map(p => `<option value="${p}"${p === app.selectedPrimitive ? ' selected' : ''}>${primLabel(p)}</option>`).join('')}
          </select>
        </div>
        <div class="stats-toolbar-right">
          <span class="stats-tf-indicator" id="stats-tf-indicator">TF: ${app.tf}</span>
        </div>
      </div>
      <div id="stats-content" class="stats-content"></div>
    </div>
  `;
}

/** Render all stats content for the current primitive/TF */
function renderStatsContent() {
  const container = document.getElementById('stats-content');
  if (!container || !app.evalData) return;

  // Update TF indicator
  const tfInd = document.getElementById('stats-tf-indicator');
  if (tfInd) tfInd.textContent = `TF: ${app.tf}`;

  const configs = app.evalData.configs || [];
  const prim = app.selectedPrimitive;
  const tf = app.tf;
  const isSingle = configs.length <= 1;

  let html = '';

  // ── 1. Side-by-side stats tables ──
  html += renderStatsTables(configs, prim, tf, isSingle);

  // ── 2. Session distribution bar chart ──
  html += `<div class="stats-section">
    <h3 class="stats-section-title">Session Distribution</h3>
    <div id="stats-session-chart" class="stats-chart-container"></div>
  </div>`;

  // ── 3. Direction split ──
  html += renderDirectionSplit(configs, prim, tf);

  // ── 4. Cascade funnel ──
  html += `<div class="stats-section">
    <h3 class="stats-section-title">Cascade Funnel</h3>
    <div id="stats-funnel-chart" class="stats-chart-container stats-chart-tall"></div>
  </div>`;

  // ── 5. Pairwise comparison stats ──
  html += renderPairwiseStats(prim, tf);

  container.innerHTML = html;

  // Render Plotly charts (must be done after DOM insertion)
  renderSessionBarChart(configs, prim, tf);
  renderFunnelChart(configs);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Side-by-side Stats Tables
 * ═══════════════════════════════════════════════════════════════════════════════ */

function renderStatsTables(configs, prim, tf, isSingle) {
  let html = '<div class="stats-section">';
  html += '<h3 class="stats-section-title">Detection Statistics</h3>';
  html += `<div class="stats-tables-grid${isSingle ? ' single' : ''}">`;

  for (let ci = 0; ci < configs.length; ci++) {
    const cfgName = configs[ci];
    const color = CONFIG_COLORS[Math.min(ci, CONFIG_COLORS.length - 1)];
    const data = getStatsTfData(cfgName, prim, tf);

    const detCount = data.detection_count != null ? data.detection_count : 0;
    const perDay = data.detections_per_day != null ? data.detections_per_day : 0;
    const perDayStd = data.detections_per_day_std != null ? data.detections_per_day_std : 0;

    html += `<div class="stats-config-card">
      <div class="stats-config-header" style="border-left: 3px solid ${color.base}">
        <span class="config-swatch" style="background:${color.base}"></span>
        <span class="stats-config-name">${cfgName}</span>
      </div>
      <table class="stats-kv-table">
        <tr>
          <td class="stats-kv-label">Detection Count</td>
          <td class="stats-kv-value">${fmtNum(detCount)}</td>
        </tr>
        <tr>
          <td class="stats-kv-label">Detections / Day</td>
          <td class="stats-kv-value">${fmtMeanStd(perDay, perDayStd)}</td>
        </tr>
      </table>
    </div>`;
  }

  html += '</div></div>';
  return html;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Session Distribution Bar Chart (Plotly grouped bars)
 * ═══════════════════════════════════════════════════════════════════════════════ */

function renderSessionBarChart(configs, prim, tf) {
  const el = document.getElementById('stats-session-chart');
  if (!el) return;

  const sessions = ['asia', 'lokz', 'nyokz', 'other'];
  const sessionLabels = ['Asia', 'LOKZ', 'NYOKZ', 'Other'];

  const traces = [];
  for (let ci = 0; ci < configs.length; ci++) {
    const cfgName = configs[ci];
    const color = CONFIG_COLORS[Math.min(ci, CONFIG_COLORS.length - 1)];
    const data = getStatsTfData(cfgName, prim, tf);
    const bySession = data.by_session || {};

    const counts = sessions.map(s => {
      const sd = bySession[s];
      return sd ? (sd.count != null ? sd.count : 0) : 0;
    });

    const pcts = sessions.map(s => {
      const sd = bySession[s];
      return sd ? (sd.pct != null ? sd.pct : 0) : 0;
    });

    traces.push({
      x: sessionLabels,
      y: counts,
      name: cfgName,
      type: 'bar',
      marker: { color: color.base },
      text: pcts.map(p => fmtPct(p)),
      textposition: 'outside',
      textfont: { size: 10, color: '#d1d4dc' },
      hovertemplate: '%{x}: %{y} detections (%{text})<extra>' + cfgName + '</extra>',
    });
  }

  const layout = plotlyLayout({
    title: { text: `Session Distribution — ${primLabel(prim)} (${tf})`, font: { size: 13 } },
    barmode: 'group',
    xaxis: {
      title: '',
      gridcolor: '#1e222d',
      linecolor: '#2a2e39',
      zerolinecolor: '#2a2e39',
    },
    yaxis: {
      title: 'Count',
      gridcolor: '#1e222d',
      linecolor: '#2a2e39',
      zerolinecolor: '#2a2e39',
    },
    legend: { orientation: 'h', y: -0.15, x: 0.5, xanchor: 'center', font: { size: 11 } },
    margin: { l: 60, r: 20, t: 50, b: 60 },
  });

  Plotly.newPlot(el, traces, layout, PLOTLY_CONFIG);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Direction Split Display
 * ═══════════════════════════════════════════════════════════════════════════════ */

function renderDirectionSplit(configs, prim, tf) {
  let html = '<div class="stats-section">';
  html += '<h3 class="stats-section-title">Direction Split</h3>';
  html += `<div class="stats-tables-grid${configs.length <= 1 ? ' single' : ''}">`;

  for (let ci = 0; ci < configs.length; ci++) {
    const cfgName = configs[ci];
    const color = CONFIG_COLORS[Math.min(ci, CONFIG_COLORS.length - 1)];
    const data = getStatsTfData(cfgName, prim, tf);
    const byDir = data.by_direction || {};

    const bull = byDir.bullish || { count: 0, pct: 0 };
    const bear = byDir.bearish || { count: 0, pct: 0 };

    const bullCount = bull.count != null ? bull.count : 0;
    const bearCount = bear.count != null ? bear.count : 0;
    const bullPct = bull.pct != null ? bull.pct : 0;
    const bearPct = bear.pct != null ? bear.pct : 0;

    html += `<div class="stats-config-card">
      <div class="stats-config-header" style="border-left: 3px solid ${color.base}">
        <span class="config-swatch" style="background:${color.base}"></span>
        <span class="stats-config-name">${cfgName}</span>
      </div>
      <div class="direction-split">
        <div class="direction-bar-wrapper">
          <div class="direction-bar">
            <div class="direction-bar-fill bullish" style="width:${bullPct}%"></div>
            <div class="direction-bar-fill bearish" style="width:${bearPct}%"></div>
          </div>
        </div>
        <div class="direction-labels">
          <span class="direction-label bullish-label">▲ Bullish: ${fmtNum(bullCount)} (${fmtPct(bullPct)})</span>
          <span class="direction-label bearish-label">▼ Bearish: ${fmtNum(bearCount)} (${fmtPct(bearPct)})</span>
        </div>
      </div>
    </div>`;
  }

  html += '</div></div>';
  return html;
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Cascade Funnel Chart (Plotly funnel)
 * ═══════════════════════════════════════════════════════════════════════════════ */

function renderFunnelChart(configs) {
  const el = document.getElementById('stats-funnel-chart');
  if (!el) return;

  // Use first config's cascade_funnel (funnel is per-config, not per-primitive)
  const cfgName = configs[0];
  if (!cfgName) {
    el.innerHTML = '<div class="stats-empty">No config data available</div>';
    return;
  }
  const cfgData = app.evalData.per_config[cfgName];
  if (!cfgData || !cfgData.cascade_funnel || !cfgData.cascade_funnel.levels) {
    el.innerHTML = '<div class="stats-empty">No cascade funnel data</div>';
    return;
  }

  const levels = cfgData.cascade_funnel.levels;

  // Sort: leaf first, then composite, then terminal
  const typeOrder = { leaf: 0, composite: 1, terminal: 2 };
  const sorted = [...levels].sort((a, b) => {
    const aOrd = typeOrder[a.type] != null ? typeOrder[a.type] : 1;
    const bOrd = typeOrder[b.type] != null ? typeOrder[b.type] : 1;
    if (aOrd !== bOrd) return aOrd - bOrd;
    // Within same type, sort by count descending
    return (b.count || 0) - (a.count || 0);
  });

  // Build funnel labels with conversion rates between levels
  const labels = [];
  const values = [];
  const colors = [];
  const hoverTexts = [];

  const typeColors = {
    leaf: '#26a69a',
    composite: '#f7c548',
    terminal: '#ef5350',
  };

  for (let i = 0; i < sorted.length; i++) {
    const lvl = sorted[i];
    const count = lvl.count != null ? lvl.count : 0;
    let labelText = `${primLabel(lvl.name)} (${lvl.type})`;

    // Add conversion rate annotations
    let convText = '';
    if (lvl.conversion_rates) {
      const rates = Object.entries(lvl.conversion_rates)
        .map(([k, v]) => `${k}: ${fmtPct(v * 100)}`)
        .join(', ');
      convText = rates;
    }

    labels.push(labelText);
    values.push(count);
    colors.push(typeColors[lvl.type] || '#787b86');

    let hover = `<b>${primLabel(lvl.name)}</b><br>Type: ${lvl.type}<br>Count: ${fmtNum(count)}`;
    if (convText) hover += `<br>Conversion: ${convText}`;
    hoverTexts.push(hover);
  }

  const trace = {
    type: 'funnel',
    y: labels,
    x: values,
    textinfo: 'value+percent initial',
    textposition: 'inside',
    textfont: { color: '#fff', size: 12, family: "'IBM Plex Mono', monospace" },
    marker: {
      color: colors,
      line: { width: 1, color: '#2a2e39' },
    },
    connector: {
      line: { color: '#2a2e39', width: 1 },
      fillcolor: 'rgba(42,46,57,0.3)',
    },
    hovertext: hoverTexts,
    hoverinfo: 'text',
  };

  // Build annotations for conversion rates between levels
  const annotations = [];
  for (let i = 0; i < sorted.length; i++) {
    const lvl = sorted[i];
    if (lvl.conversion_rates) {
      const rateLines = Object.entries(lvl.conversion_rates)
        .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${fmtPct(v * 100)}`)
        .join('<br>');
      annotations.push({
        x: 1.02,
        y: labels[i],
        xref: 'paper',
        yref: 'y',
        text: rateLines,
        showarrow: false,
        font: { size: 10, color: '#787b86', family: "'IBM Plex Mono', monospace" },
        xanchor: 'left',
        align: 'left',
      });
    }
  }

  const layout = plotlyLayout({
    title: { text: `Cascade Funnel — ${configs[0]}`, font: { size: 13 } },
    funnelmode: 'stack',
    showlegend: false,
    margin: { l: 180, r: 200, t: 50, b: 30 },
    annotations: annotations,
    yaxis: {
      gridcolor: '#1e222d',
      linecolor: '#2a2e39',
      zerolinecolor: '#2a2e39',
    },
  });

  Plotly.newPlot(el, [trace], layout, PLOTLY_CONFIG);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Pairwise Comparison Stats
 * ═══════════════════════════════════════════════════════════════════════════════ */

function renderPairwiseStats(prim, tf) {
  const pw = getPairwiseData();
  if (!pw) {
    // No pairwise data (single config) — show informational message
    return `<div class="stats-section">
      <h3 class="stats-section-title">Pairwise Comparison</h3>
      <div class="stats-empty">Pairwise comparison requires two or more configs. Current run has a single config.</div>
    </div>`;
  }

  const pwTf = getPairwiseTfData(prim, tf);
  if (!pwTf) {
    return `<div class="stats-section">
      <h3 class="stats-section-title">Pairwise Comparison</h3>
      <div class="stats-empty">No pairwise data available for ${primLabel(prim)} at ${tf}.</div>
    </div>`;
  }

  const agreementRate = pwTf.agreement_rate != null ? pwTf.agreement_rate : 0;
  const onlyInA = pwTf.only_in_a != null ? pwTf.only_in_a : 0;
  const onlyInB = pwTf.only_in_b != null ? pwTf.only_in_b : 0;
  const bySessionAgreement = pwTf.by_session_agreement || {};

  const configA = pw.data.config_a || 'Config A';
  const configB = pw.data.config_b || 'Config B';

  let html = '<div class="stats-section">';
  html += '<h3 class="stats-section-title">Pairwise Comparison</h3>';
  html += `<div class="stats-config-card" style="max-width: 600px">
    <div class="stats-config-header" style="border-left: 3px solid var(--blue)">
      <span class="stats-config-name">${configA} vs ${configB}</span>
    </div>
    <table class="stats-kv-table">
      <tr>
        <td class="stats-kv-label">Agreement Rate</td>
        <td class="stats-kv-value">${fmtPct(agreementRate * 100)}</td>
      </tr>
      <tr>
        <td class="stats-kv-label">Only in ${configA}</td>
        <td class="stats-kv-value">${fmtNum(onlyInA)}</td>
      </tr>
      <tr>
        <td class="stats-kv-label">Only in ${configB}</td>
        <td class="stats-kv-value">${fmtNum(onlyInB)}</td>
      </tr>
    </table>`;

  // Per-session agreement
  const sessions = ['asia', 'lokz', 'nyokz', 'other'];
  const sessionNames = { asia: 'Asia', lokz: 'LOKZ', nyokz: 'NYOKZ', other: 'Other' };
  const hasSessionData = sessions.some(s => bySessionAgreement[s]);

  if (hasSessionData) {
    html += '<div class="stats-subsection-title">Per-Session Agreement</div>';
    html += '<table class="stats-kv-table">';
    for (const s of sessions) {
      const sa = bySessionAgreement[s];
      const agr = sa && sa.agreement != null ? sa.agreement : 0;
      html += `<tr>
        <td class="stats-kv-label">${sessionNames[s]}</td>
        <td class="stats-kv-value">${fmtPct(agr * 100)}</td>
      </tr>`;
    }
    html += '</table>';
  }

  html += '</div></div>';
  return html;
}
