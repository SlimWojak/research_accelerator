/* ═══════════════════════════════════════════════════════════════════════════════
 * stats-tab.js — Stats dashboard: side-by-side config tables, Plotly grouped
 *                bar charts (session distribution), direction split, cascade
 *                funnel chart, pairwise comparison statistics, primitive
 *                selector, and TF indicator.
 * ═══════════════════════════════════════════════════════════════════════════════ */

let _statsInitialized = false;

/** Reset stats tab state so it re-initializes on next activation. */
function resetStatsTab() {
  _statsInitialized = false;
}

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

  // Purge existing Plotly charts before re-creating to prevent memory leaks
  const sessionChartEl = document.getElementById('stats-session-chart');
  if (sessionChartEl) Plotly.purge(sessionChartEl);
  const funnelChartEl = document.getElementById('stats-funnel-chart');
  if (funnelChartEl) Plotly.purge(funnelChartEl);

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

  // ── 6. Ground Truth / Scored section ──
  html += renderGroundTruthSection();

  container.innerHTML = html;

  // Render Plotly charts (must be done after DOM insertion)
  renderSessionBarChart(configs, prim, tf);
  renderFunnelChart(configs);
}

/* ═══════════════════════════════════════════════════════════════════════════════
 * Side-by-side Stats Tables
 * ═══════════════════════════════════════════════════════════════════════════════ */

function renderStatsTables(configs, prim, tf, isSingle) {
  // Build title with variant info if available
  let statsTitle = 'Detection Statistics';
  if (app.hasVariantData && app.availableVariants.length > 0) {
    statsTitle += ` — ${primLabel(prim)}`;
  }

  let html = '<div class="stats-section">';
  html += `<h3 class="stats-section-title">${statsTitle}</h3>`;
  html += `<div class="stats-tables-grid${isSingle ? ' single' : ''}">`;

  for (let ci = 0; ci < configs.length; ci++) {
    const cfgName = configs[ci];
    const color = CONFIG_COLORS[Math.min(ci, CONFIG_COLORS.length - 1)];
    const data = getStatsTfData(cfgName, prim, tf);

    const detCount = data.detection_count != null ? data.detection_count : 0;
    const perDay = data.detections_per_day != null ? data.detections_per_day : 0;
    const perDayStd = data.detections_per_day_std != null ? data.detections_per_day_std : 0;

    // Include variant name in config card header
    const variant = typeof getConfigVariant === 'function' ? getConfigVariant(cfgName) : '';
    const cardTitle = variant ? `${cfgName} <span style="color:var(--muted);font-weight:400;font-size:11px">(${variant})</span>` : cfgName;

    html += `<div class="stats-config-card">
      <div class="stats-config-header" style="border-left: 3px solid ${color.base}">
        <span class="config-swatch" style="background:${color.base}"></span>
        <span class="stats-config-name">${cardTitle}</span>
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

    // Use variant name in trace label if available
    const traceVariant = typeof getConfigVariant === 'function' ? getConfigVariant(cfgName) : '';
    const traceName = traceVariant ? `${cfgName} (${traceVariant})` : cfgName;

    traces.push({
      x: sessionLabels,
      y: counts,
      name: traceName,
      type: 'bar',
      marker: { color: color.base },
      text: pcts.map(p => fmtPct(p)),
      textposition: 'outside',
      textfont: { size: 10, color: '#d1d4dc' },
      hovertemplate: '%{x}: %{y} detections (%{text})<extra>' + traceName + '</extra>',
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

    // Include variant name in direction split card header
    const dirVariant = typeof getConfigVariant === 'function' ? getConfigVariant(cfgName) : '';
    const dirCardTitle = dirVariant ? `${cfgName} <span style="color:var(--muted);font-weight:400;font-size:11px">(${dirVariant})</span>` : cfgName;

    html += `<div class="stats-config-card">
      <div class="stats-config-header" style="border-left: 3px solid ${color.base}">
        <span class="config-swatch" style="background:${color.base}"></span>
        <span class="stats-config-name">${dirCardTitle}</span>
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

  // Include variant names in pairwise header if available
  const varA = pw.data.variant_a || (typeof getConfigVariant === 'function' ? getConfigVariant(configA) : '');
  const varB = pw.data.variant_b || (typeof getConfigVariant === 'function' ? getConfigVariant(configB) : '');
  const pairLabelA = varA ? `${configA} (${varA})` : configA;
  const pairLabelB = varB ? `${configB} (${varB})` : configB;

  let html = '<div class="stats-section">';
  html += '<h3 class="stats-section-title">Pairwise Comparison</h3>';
  html += `<div class="stats-config-card" style="max-width: 600px">
    <div class="stats-config-header" style="border-left: 3px solid var(--blue)">
      <span class="stats-config-name">${pairLabelA} vs ${pairLabelB}</span>
    </div>
    <table class="stats-kv-table">
      <tr>
        <td class="stats-kv-label">Agreement Rate</td>
        <td class="stats-kv-value">${fmtPct(agreementRate * 100)}</td>
      </tr>
      <tr>
        <td class="stats-kv-label">Only in ${pairLabelA}</td>
        <td class="stats-kv-value">${fmtNum(onlyInA)}</td>
      </tr>
      <tr>
        <td class="stats-kv-label">Only in ${pairLabelB}</td>
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

/* ═══════════════════════════════════════════════════════════════════════════════
 * Ground Truth / Scored Section
 *
 * Displays precision/recall/F1 from the scoring section when label data was
 * included in the evaluation run (eval.py compare --labels).
 * Shows per-primitive breakdown, per-variant scores, and delta between configs.
 * When no labels loaded, shows a "No labels loaded" message.
 * ═══════════════════════════════════════════════════════════════════════════════ */

/** Format a score value (precision/recall/F1) as percentage */
function fmtScore(v) {
  if (v == null) return '—';
  return (v * 100).toFixed(1) + '%';
}

/** Format a delta value with +/- sign */
function fmtDelta(v) {
  if (v == null) return '—';
  const pct = (v * 100).toFixed(1);
  const sign = v > 0 ? '+' : '';
  return sign + pct + '%';
}

/** Get CSS color for a delta value */
function deltaColor(v) {
  if (v == null) return 'var(--muted)';
  if (v > 0.01) return 'var(--teal)';
  if (v < -0.01) return 'var(--red)';
  return 'var(--muted)';
}

/** Render the full Ground Truth section */
function renderGroundTruthSection() {
  const scoring = app.evalData ? app.evalData.scoring : null;

  let html = '<div class="stats-section">';
  html += '<h3 class="stats-section-title">Ground Truth</h3>';

  if (!scoring) {
    html += '<div class="stats-empty">No labels loaded — run eval.py compare with --labels to include precision/recall scoring.</div>';
    html += '</div>';
    return html;
  }

  // ── Label source summary ──
  const source = scoring.label_source || {};
  html += '<div style="margin-bottom:16px;font-size:12px;color:var(--muted);font-family:var(--mono)">';
  html += `${fmtNum(source.total || 0)} labels`;
  if (source.validate_count || source.compare_count) {
    html += ` (${fmtNum(source.validate_count || 0)} validate, ${fmtNum(source.compare_count || 0)} compare)`;
  }
  html += '</div>';

  // ── Aggregate scores ──
  const agg = scoring.aggregate || {};
  html += renderAggregateScores(agg);

  // ── Per-primitive P/R/F1 table ──
  html += renderPerPrimitiveScoreTable(scoring.per_primitive || {});

  // ── Per-config (variant) scores side-by-side ──
  if (scoring.per_config && Object.keys(scoring.per_config).length > 0) {
    html += renderPerConfigScores(scoring.per_config, scoring.delta);
  }

  html += '</div>';
  return html;
}

/** Render aggregate precision/recall/F1 card */
function renderAggregateScores(agg) {
  let html = '<div class="stats-config-card" style="max-width:500px;margin-bottom:16px">';
  html += `<div class="stats-config-header" style="border-left:3px solid var(--blue)">
    <span class="stats-config-name">Aggregate Scores</span>
  </div>`;
  html += '<table class="stats-kv-table">';
  html += `<tr>
    <td class="stats-kv-label">Precision</td>
    <td class="stats-kv-value">${fmtScore(agg.precision)}</td>
  </tr>`;
  html += `<tr>
    <td class="stats-kv-label">Recall</td>
    <td class="stats-kv-value">${fmtScore(agg.recall)}</td>
  </tr>`;
  html += `<tr>
    <td class="stats-kv-label">F1</td>
    <td class="stats-kv-value">${fmtScore(agg.f1)}</td>
  </tr>`;
  html += `<tr>
    <td class="stats-kv-label">Total Labels</td>
    <td class="stats-kv-value">${fmtNum(agg.total_labels)}</td>
  </tr>`;
  html += '</table></div>';
  return html;
}

/** Render per-primitive precision/recall/F1 grouped table */
function renderPerPrimitiveScoreTable(perPrimitive) {
  const primitives = Object.keys(perPrimitive);
  if (primitives.length === 0) return '';

  let html = '<div style="margin-bottom:16px">';
  html += '<div class="stats-subsection-title" style="padding:0 0 8px;margin-bottom:8px;border-bottom:1px solid var(--border)">Per-Primitive Breakdown</div>';

  html += '<div style="overflow-x:auto">';
  html += '<table class="stats-kv-table" style="width:100%;max-width:700px">';
  html += '<thead><tr>';
  html += '<th style="text-align:left;padding:6px 12px;font-size:11px;font-weight:600;color:var(--muted);border-bottom:1px solid var(--border)">Primitive</th>';
  html += '<th style="text-align:right;padding:6px 12px;font-size:11px;font-weight:600;color:var(--muted);border-bottom:1px solid var(--border)">Precision</th>';
  html += '<th style="text-align:right;padding:6px 12px;font-size:11px;font-weight:600;color:var(--muted);border-bottom:1px solid var(--border)">Recall</th>';
  html += '<th style="text-align:right;padding:6px 12px;font-size:11px;font-weight:600;color:var(--muted);border-bottom:1px solid var(--border)">F1</th>';
  html += '<th style="text-align:right;padding:6px 12px;font-size:11px;font-weight:600;color:var(--muted);border-bottom:1px solid var(--border)">Labels</th>';
  html += '</tr></thead><tbody>';

  for (const prim of primitives) {
    const data = perPrimitive[prim];
    html += '<tr>';
    html += `<td style="padding:6px 12px;font-size:12px;color:var(--text)">${primLabel(prim)}</td>`;
    html += `<td style="text-align:right;padding:6px 12px;font-family:var(--mono);font-size:12px;color:var(--text)">${fmtScore(data.precision)}</td>`;
    html += `<td style="text-align:right;padding:6px 12px;font-family:var(--mono);font-size:12px;color:var(--text)">${fmtScore(data.recall)}</td>`;
    html += `<td style="text-align:right;padding:6px 12px;font-family:var(--mono);font-size:12px;color:var(--text)">${fmtScore(data.f1)}</td>`;
    html += `<td style="text-align:right;padding:6px 12px;font-family:var(--mono);font-size:12px;color:var(--muted)">${fmtNum(data.label_count)}</td>`;
    html += '</tr>';

    // Per-variant sub-rows if available
    if (data.per_variant && Object.keys(data.per_variant).length > 0) {
      for (const [variant, vScores] of Object.entries(data.per_variant)) {
        html += '<tr>';
        html += `<td style="padding:4px 12px 4px 28px;font-size:11px;color:var(--muted)">↳ ${variant}</td>`;
        html += `<td style="text-align:right;padding:4px 12px;font-family:var(--mono);font-size:11px;color:var(--muted)">${fmtScore(vScores.precision)}</td>`;
        html += `<td style="text-align:right;padding:4px 12px;font-family:var(--mono);font-size:11px;color:var(--muted)">${fmtScore(vScores.recall)}</td>`;
        html += `<td style="text-align:right;padding:4px 12px;font-family:var(--mono);font-size:11px;color:var(--muted)">${fmtScore(vScores.f1)}</td>`;
        html += `<td style="text-align:right;padding:4px 12px;font-family:var(--mono);font-size:11px;color:var(--faint)">${fmtNum(vScores.label_count)}</td>`;
        html += '</tr>';
      }
    }
  }

  html += '</tbody></table></div></div>';
  return html;
}

/** Render per-config (per-variant) scores in side-by-side cards */
function renderPerConfigScores(perConfig, delta) {
  const configNames = Object.keys(perConfig);
  if (configNames.length === 0) return '';

  let html = '<div style="margin-bottom:16px">';
  html += '<div class="stats-subsection-title" style="padding:0 0 8px;margin-bottom:8px;border-bottom:1px solid var(--border)">Per-Variant Scores</div>';

  html += `<div class="stats-tables-grid${configNames.length <= 1 ? ' single' : ''}">`;

  for (let ci = 0; ci < configNames.length; ci++) {
    const cfgName = configNames[ci];
    const cfgScoring = perConfig[cfgName];
    const color = CONFIG_COLORS[Math.min(ci, CONFIG_COLORS.length - 1)];

    // Get variant name from evalData
    const variant = typeof getConfigVariant === 'function' ? getConfigVariant(cfgName) : '';
    const cardTitle = variant
      ? `${cfgName} <span style="color:var(--muted);font-weight:400;font-size:11px">(${variant})</span>`
      : cfgName;

    html += `<div class="stats-config-card">
      <div class="stats-config-header" style="border-left:3px solid ${color.base}">
        <span class="config-swatch" style="background:${color.base}"></span>
        <span class="stats-config-name">${cardTitle}</span>
      </div>`;

    // Per-primitive rows for this config
    const primitives = Object.keys(cfgScoring);
    if (primitives.length === 0) {
      html += '<div class="stats-empty">No scored primitives</div>';
    } else {
      html += '<table class="stats-kv-table">';

      for (const prim of primitives) {
        const s = cfgScoring[prim];
        html += `<tr><td colspan="2" class="stats-subsection-title" style="padding:8px 12px 2px;font-size:10px">${primLabel(prim)}</td></tr>`;
        html += `<tr>
          <td class="stats-kv-label">Precision</td>
          <td class="stats-kv-value">${fmtScore(s.precision)}</td>
        </tr>`;
        html += `<tr>
          <td class="stats-kv-label">Recall</td>
          <td class="stats-kv-value">${fmtScore(s.recall)}</td>
        </tr>`;
        html += `<tr>
          <td class="stats-kv-label">F1</td>
          <td class="stats-kv-value">${fmtScore(s.f1)}</td>
        </tr>`;
        html += `<tr>
          <td class="stats-kv-label">Labelled / Detected</td>
          <td class="stats-kv-value">${fmtNum(s.labelled_count)} / ${fmtNum(s.detection_count)}</td>
        </tr>`;
      }

      html += '</table>';
    }

    html += '</div>';
  }

  html += '</div>';

  // ── Delta between configs ──
  if (delta && delta.per_primitive) {
    html += renderScoringDelta(delta);
  }

  html += '</div>';
  return html;
}

/** Render scoring delta between two configs */
function renderScoringDelta(delta) {
  const configA = delta.config_a || 'Config A';
  const configB = delta.config_b || 'Config B';
  const perPrim = delta.per_primitive || {};
  const primitives = Object.keys(perPrim);
  if (primitives.length === 0) return '';

  let html = '<div style="margin-top:12px">';
  html += '<div class="stats-config-card" style="max-width:700px">';
  html += `<div class="stats-config-header" style="border-left:3px solid var(--purple)">
    <span class="stats-config-name">Delta: ${configB} vs ${configA}</span>
  </div>`;

  html += '<div style="overflow-x:auto">';
  html += '<table class="stats-kv-table" style="width:100%">';
  html += '<thead><tr>';
  html += '<th style="text-align:left;padding:6px 12px;font-size:11px;font-weight:600;color:var(--muted);border-bottom:1px solid var(--border)">Primitive</th>';
  html += '<th style="text-align:right;padding:6px 12px;font-size:11px;font-weight:600;color:var(--muted);border-bottom:1px solid var(--border)">ΔPrecision</th>';
  html += '<th style="text-align:right;padding:6px 12px;font-size:11px;font-weight:600;color:var(--muted);border-bottom:1px solid var(--border)">ΔRecall</th>';
  html += '<th style="text-align:right;padding:6px 12px;font-size:11px;font-weight:600;color:var(--muted);border-bottom:1px solid var(--border)">ΔF1</th>';
  html += '</tr></thead><tbody>';

  for (const prim of primitives) {
    const d = perPrim[prim];
    html += '<tr>';
    html += `<td style="padding:6px 12px;font-size:12px;color:var(--text)">${primLabel(prim)}</td>`;
    html += `<td style="text-align:right;padding:6px 12px;font-family:var(--mono);font-size:12px;color:${deltaColor(d.precision_delta)}">${fmtDelta(d.precision_delta)}</td>`;
    html += `<td style="text-align:right;padding:6px 12px;font-family:var(--mono);font-size:12px;color:${deltaColor(d.recall_delta)}">${fmtDelta(d.recall_delta)}</td>`;
    html += `<td style="text-align:right;padding:6px 12px;font-family:var(--mono);font-size:12px;color:${deltaColor(d.f1_delta)}">${fmtDelta(d.f1_delta)}</td>`;
    html += '</tr>';
  }

  // Aggregate delta if available
  const aggDelta = delta.aggregate;
  if (aggDelta) {
    html += '<tr style="border-top:1px solid var(--border)">';
    html += '<td style="padding:6px 12px;font-size:12px;font-weight:600;color:var(--text)">Aggregate</td>';
    html += `<td style="text-align:right;padding:6px 12px;font-family:var(--mono);font-size:12px;font-weight:600;color:${deltaColor(aggDelta.precision_delta)}">${fmtDelta(aggDelta.precision_delta)}</td>`;
    html += `<td style="text-align:right;padding:6px 12px;font-family:var(--mono);font-size:12px;font-weight:600;color:${deltaColor(aggDelta.recall_delta)}">${fmtDelta(aggDelta.recall_delta)}</td>`;
    html += `<td style="text-align:right;padding:6px 12px;font-family:var(--mono);font-size:12px;font-weight:600;color:${deltaColor(aggDelta.f1_delta)}">${fmtDelta(aggDelta.f1_delta)}</td>`;
    html += '</tr>';
  }

  html += '</tbody></table></div></div></div>';
  return html;
}
