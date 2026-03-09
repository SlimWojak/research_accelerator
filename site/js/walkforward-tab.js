/* ═══════════════════════════════════════════════════════════════════════════════
 * walkforward-tab.js — Walk-Forward Stability Visualization (Schema 4E)
 * ═══════════════════════════════════════════════════════════════════════════════
 *
 * Renders a Plotly line/area chart showing train vs test metrics across
 * walk-forward windows. Features:
 *   - Two lines: train_metric (solid) and test_metric (dashed) with legend
 *   - Shaded delta bands between train and test lines
 *   - Pass/fail coloring per window (green=pass, red=fail)
 *   - Summary verdict badge (STABLE / CONDITIONALLY_STABLE / UNSTABLE)
 *   - Summary statistics panel
 *   - Window detail on hover/click
 *   - Pass threshold indicator line on chart
 *   - Worst window highlight
 *   - Degradation flag warning
 *   - Graceful handling of missing file / empty windows
 *   - Dark theme on all Plotly elements
 * ═══════════════════════════════════════════════════════════════════════════════ */

let wfInitialized = false;

/**
 * Initialize the Walk-Forward tab. Called by switchTab() in shared.js.
 */
function initWalkForwardTab() {
  const container = document.getElementById('tab-walkforward');
  if (!container) return;

  // Skip if already rendered
  if (wfInitialized) return;

  const wfData = app.walkForwardData;

  // No walk-forward data — show user-visible error (VAL-WFUI-009)
  if (!wfData) {
    container.innerHTML = renderWFError('No walk-forward data available. The walk-forward JSON file could not be loaded from eval/ directory.');
    wfInitialized = true;
    return;
  }

  // Validate minimum structure
  if (!wfData.summary) {
    container.innerHTML = renderWFError('Walk-forward data is malformed (missing summary).');
    wfInitialized = true;
    return;
  }

  // Empty windows — show informative message (not blank chart)
  const windows = wfData.windows || [];
  if (windows.length === 0) {
    container.innerHTML = renderWFEmpty(wfData);
    wfInitialized = true;
    return;
  }

  // Build full walk-forward visualization
  container.innerHTML = renderWFShell(wfData);
  renderWFChart(wfData);
  wfInitialized = true;
}

/* ── HTML Shells ───────────────────────────────────────────────────────────── */

/**
 * Render error state for walk-forward tab (VAL-WFUI-009).
 */
function renderWFError(message) {
  return `
    <div class="tab-placeholder">
      <div class="ph-icon">⚠️</div>
      <div class="ph-title">Walk-Forward Unavailable</div>
      <div class="ph-desc">${message}</div>
    </div>
  `;
}

/**
 * Render empty windows state — dataset too short for walk-forward.
 */
function renderWFEmpty(data) {
  const summary = data.summary;
  const verdict = summary.verdict || 'STABLE';
  const verdictColor = getVerdictColor(verdict);

  return `
    <div class="wf-layout">
      <div class="wf-header">
        <div class="wf-header-left">
          <div class="wf-title">Walk-Forward Stability</div>
          <div class="wf-subtitle">${primLabel(data.primitive || '')} — ${(data.metric || '').replace(/_/g, ' ')}</div>
        </div>
        <div class="wf-header-right">
          <span class="wf-verdict-badge" style="background: ${verdictColor.bg}; color: ${verdictColor.text}; border-color: ${verdictColor.border};">
            ${verdict.replace(/_/g, ' ')}
          </span>
        </div>
      </div>
      <div class="wf-empty-state">
        <div class="wf-empty-icon">📊</div>
        <div class="wf-empty-title">No windows — dataset too short</div>
        <div class="wf-empty-desc">
          The dataset does not contain enough data for walk-forward validation
          with the configured window sizes (train: ${data.window_config?.train_months || '?'}mo, test: ${data.window_config?.test_months || '?'}mo).
          A longer dataset is needed to produce walk-forward windows.
        </div>
      </div>
    </div>
  `;
}

/**
 * Render full walk-forward visualization shell with verdict, stats, and chart container.
 */
function renderWFShell(data) {
  const summary = data.summary;
  const verdict = summary.verdict || 'UNKNOWN';
  const verdictColor = getVerdictColor(verdict);
  const degradation = summary.degradation_flag === true;

  return `
    <div class="wf-layout">
      <div class="wf-header">
        <div class="wf-header-left">
          <div class="wf-title">Walk-Forward Stability</div>
          <div class="wf-subtitle">${primLabel(data.primitive || '')} — ${(data.metric || '').replace(/_/g, ' ')}</div>
        </div>
        <div class="wf-header-right">
          ${degradation ? '<span class="wf-degradation-warning" title="Performance degradation detected across windows">⚠ Degradation Detected</span>' : ''}
          <span class="wf-verdict-badge" style="background: ${verdictColor.bg}; color: ${verdictColor.text}; border-color: ${verdictColor.border};">
            ${verdict.replace(/_/g, ' ')}
          </span>
        </div>
      </div>

      <div class="wf-stats-bar">
        ${renderWFStats(summary)}
      </div>

      <div class="wf-body">
        <div id="wf-chart-container" class="wf-chart-container"></div>
        <div id="wf-detail-panel" class="wf-detail-panel">
          <div class="wf-detail-placeholder">Hover or click a window to see details</div>
        </div>
      </div>
    </div>
  `;
}

/**
 * Render summary statistics bar (VAL-WFUI-006).
 */
function renderWFStats(summary) {
  const stats = [
    { label: 'Windows', value: fmtNum(summary.windows_total) },
    { label: 'Passed', value: String(summary.windows_passed), cls: 'wf-stat-pass' },
    { label: 'Failed', value: String(summary.windows_failed), cls: summary.windows_failed > 0 ? 'wf-stat-fail' : '' },
    { label: 'Mean Test', value: summary.mean_test_metric != null ? Number(summary.mean_test_metric).toFixed(3) : '—' },
    { label: 'Std Test', value: summary.std_test_metric != null ? Number(summary.std_test_metric).toFixed(3) : '—' },
    { label: 'Mean Δ', value: summary.mean_delta != null ? Number(summary.mean_delta).toFixed(3) : '—' },
    { label: 'Threshold', value: summary.pass_threshold_pct != null ? summary.pass_threshold_pct + '%' : '—' },
  ];

  return stats.map(s =>
    `<div class="wf-stat">
      <div class="wf-stat-label">${s.label}</div>
      <div class="wf-stat-value ${s.cls || ''}">${s.value}</div>
    </div>`
  ).join('');
}

/* ── Chart Rendering ───────────────────────────────────────────────────────── */

/**
 * Render the Plotly walk-forward chart (VAL-WFUI-001 through VAL-WFUI-008, VAL-WFUI-010, VAL-WFUI-011).
 */
function renderWFChart(data) {
  const chartEl = document.getElementById('wf-chart-container');
  if (!chartEl) return;

  Plotly.purge(chartEl);

  const windows = data.windows;
  const summary = data.summary;
  const threshold = summary.pass_threshold_pct || 15.0;
  const worstIdx = summary.worst_window ? summary.worst_window.window_index : null;

  // X-axis labels: window indices with test period labels
  const xLabels = windows.map((w, i) => {
    const tp = w.test_period;
    if (tp && tp.start && tp.end) {
      return `W${w.window_index} (${formatPeriodShort(tp.start)}–${formatPeriodShort(tp.end)})`;
    }
    return `W${w.window_index}`;
  });

  const trainValues = windows.map(w => w.train_metric);
  const testValues = windows.map(w => w.test_metric);

  // Colors per window based on pass/fail (VAL-WFUI-004)
  const passColor = '#26a69a';   // green
  const failColor = '#ef5350';   // red
  const windowColors = windows.map(w => w.passed ? passColor : failColor);

  const traces = [];

  // --- Shaded delta band between train and test (VAL-WFUI-003) ---
  // Upper boundary (max of train, test)
  const upperBound = windows.map((w, i) => Math.max(trainValues[i], testValues[i]));
  const lowerBound = windows.map((w, i) => Math.min(trainValues[i], testValues[i]));

  // Fill band using fill='tonexty'
  traces.push({
    type: 'scatter',
    x: xLabels,
    y: upperBound,
    mode: 'lines',
    line: { width: 0 },
    showlegend: false,
    hoverinfo: 'skip',
    name: '_upper',
  });

  traces.push({
    type: 'scatter',
    x: xLabels,
    y: lowerBound,
    mode: 'lines',
    line: { width: 0 },
    fill: 'tonexty',
    fillcolor: 'rgba(120,123,134,0.15)',
    showlegend: false,
    hoverinfo: 'skip',
    name: '_delta_band',
  });

  // --- Train metric line (VAL-WFUI-001, VAL-WFUI-002) ---
  traces.push({
    type: 'scatter',
    x: xLabels,
    y: trainValues,
    mode: 'lines+markers',
    name: 'Train Metric',
    line: { color: '#2962ff', width: 2, dash: 'solid' },
    marker: {
      color: '#2962ff',
      size: 8,
      line: { color: '#0a0e17', width: 1 },
    },
    hovertemplate: xLabels.map((label, i) => {
      const w = windows[i];
      return `<b>Window ${w.window_index} — Train</b><br>` +
        `Value: ${trainValues[i] != null ? Number(trainValues[i]).toFixed(4) : 'N/A'}<br>` +
        `Period: ${formatPeriod(w.train_period)}<extra></extra>`;
    }),
  });

  // --- Test metric line (VAL-WFUI-001, VAL-WFUI-002) ---
  traces.push({
    type: 'scatter',
    x: xLabels,
    y: testValues,
    mode: 'lines+markers',
    name: 'Test Metric',
    line: { color: '#f7c548', width: 2, dash: 'dash' },
    marker: {
      color: windowColors,
      size: 10,
      symbol: windows.map(w => w.passed ? 'circle' : 'x'),
      line: { color: '#0a0e17', width: 1 },
    },
    hovertemplate: xLabels.map((label, i) => {
      const w = windows[i];
      return `<b>Window ${w.window_index} — Test</b><br>` +
        `Value: ${testValues[i] != null ? Number(testValues[i]).toFixed(4) : 'N/A'}<br>` +
        `Δ: ${w.delta != null ? Number(w.delta).toFixed(4) : '—'} (${w.delta_pct != null ? Number(w.delta_pct).toFixed(1) + '%' : '—'})<br>` +
        `Status: ${w.passed ? '✓ PASS' : '✗ FAIL'}<br>` +
        `Period: ${formatPeriod(w.test_period)}<br>` +
        `Regime: ${(w.regime_tags || []).join(', ') || 'none'}<extra></extra>`;
    }),
  });

  // --- Pass/fail background coloring per window (VAL-WFUI-004) ---
  // Add vertical rectangular shapes per window
  const shapes = [];
  windows.forEach((w, i) => {
    const color = w.passed
      ? 'rgba(38,166,154,0.07)'
      : 'rgba(239,83,80,0.10)';
    shapes.push({
      type: 'rect',
      xref: 'x',
      yref: 'paper',
      x0: i - 0.4,
      x1: i + 0.4,
      y0: 0,
      y1: 1,
      fillcolor: color,
      line: { width: 0 },
      layer: 'below',
    });
  });

  // --- Pass threshold indicator (VAL-WFUI-008) ---
  // Show as a reference band around the mean train value
  // The threshold defines max allowable delta_pct from train to test
  // Render as annotation + horizontal reference line at the threshold delta zone
  const meanTrain = trainValues.reduce((a, b) => a + b, 0) / trainValues.length;
  const thresholdLow = meanTrain * (1 - threshold / 100);

  shapes.push({
    type: 'line',
    xref: 'paper',
    yref: 'y',
    x0: 0,
    x1: 1,
    y0: thresholdLow,
    y1: thresholdLow,
    line: { color: 'rgba(239,83,80,0.5)', width: 1.5, dash: 'dot' },
    layer: 'above',
  });

  // --- Worst window highlight (VAL-WFUI-010) ---
  const annotations = [];
  if (worstIdx != null) {
    const worstArrIdx = windows.findIndex(w => w.window_index === worstIdx);
    if (worstArrIdx >= 0) {
      const worstW = windows[worstArrIdx];
      // Special marker emphasis via annotation
      annotations.push({
        x: xLabels[worstArrIdx],
        y: worstW.test_metric,
        xref: 'x',
        yref: 'y',
        text: '▼ Worst',
        showarrow: true,
        arrowhead: 2,
        arrowsize: 1,
        arrowwidth: 2,
        arrowcolor: '#ef5350',
        ax: 0,
        ay: -35,
        font: { color: '#ef5350', size: 11, family: "'IBM Plex Mono', monospace" },
        bgcolor: 'rgba(239,83,80,0.15)',
        bordercolor: '#ef5350',
        borderwidth: 1,
        borderpad: 3,
      });

      // Highlight ring around worst window marker
      shapes.push({
        type: 'circle',
        xref: 'x',
        yref: 'y',
        x0: worstArrIdx - 0.3,
        x1: worstArrIdx + 0.3,
        y0: worstW.test_metric - 0.02,
        y1: worstW.test_metric + 0.02,
        line: { color: '#ef5350', width: 2, dash: 'dot' },
        fillcolor: 'rgba(239,83,80,0.08)',
        layer: 'above',
      });
    }
  }

  // Threshold annotation
  annotations.push({
    x: 1.0,
    y: thresholdLow,
    xref: 'paper',
    yref: 'y',
    text: `Threshold (−${threshold}%)`,
    showarrow: false,
    font: { color: 'rgba(239,83,80,0.7)', size: 10, family: "'IBM Plex Mono', monospace" },
    xanchor: 'right',
    yanchor: 'bottom',
    bgcolor: 'rgba(10,14,23,0.8)',
    borderpad: 2,
  });

  // Layout
  const layout = plotlyLayout({
    title: { text: '' },
    xaxis: {
      title: { text: 'Walk-Forward Windows', font: { color: '#d1d4dc', size: 12 } },
      tickfont: { size: 9, family: "'IBM Plex Mono', monospace" },
      tickangle: -25,
      gridcolor: '#1e222d',
      linecolor: '#2a2e39',
    },
    yaxis: {
      title: { text: (data.metric || 'Metric').replace(/_/g, ' '), font: { color: '#d1d4dc', size: 12 } },
      tickfont: { size: 10, family: "'IBM Plex Mono', monospace" },
      gridcolor: '#1e222d',
      linecolor: '#2a2e39',
      zeroline: false,
    },
    margin: { l: 70, r: 20, t: 20, b: 80 },
    showlegend: true,
    legend: {
      font: { color: '#d1d4dc', size: 11, family: "'IBM Plex Mono', monospace" },
      bgcolor: 'rgba(19,23,34,0.8)',
      bordercolor: '#2a2e39',
      borderwidth: 1,
      x: 0.01,
      y: 0.99,
      xanchor: 'left',
      yanchor: 'top',
    },
    shapes: shapes,
    annotations: annotations,
  });

  Plotly.newPlot(chartEl, traces, layout, PLOTLY_CONFIG);

  // --- Window detail on click (VAL-WFUI-007) ---
  chartEl.on('plotly_click', function(eventData) {
    if (!eventData || !eventData.points || eventData.points.length === 0) return;
    const pt = eventData.points[0];
    const pointIdx = pt.pointIndex;
    if (pointIdx >= 0 && pointIdx < windows.length) {
      showWindowDetail(windows[pointIdx], data, pointIdx);
    }
  });

  // Also show on hover
  chartEl.on('plotly_hover', function(eventData) {
    if (!eventData || !eventData.points || eventData.points.length === 0) return;
    const pt = eventData.points[0];
    const pointIdx = pt.pointIndex;
    if (pointIdx >= 0 && pointIdx < windows.length) {
      showWindowDetail(windows[pointIdx], data, pointIdx);
    }
  });
}

/* ── Window Detail Panel (VAL-WFUI-007) ────────────────────────────────────── */

/**
 * Show detailed info for a specific window in the detail panel.
 */
function showWindowDetail(w, data, arrIdx) {
  const panel = document.getElementById('wf-detail-panel');
  if (!panel) return;

  const summary = data.summary;
  const isWorst = summary.worst_window && summary.worst_window.window_index === w.window_index;
  const statusColor = w.passed ? '#26a69a' : '#ef5350';
  const statusText = w.passed ? '✓ PASS' : '✗ FAIL';

  panel.innerHTML = `
    <div class="wf-detail-header">
      <span class="wf-detail-title">Window ${w.window_index}</span>
      <span class="wf-detail-status" style="color: ${statusColor};">${statusText}</span>
      ${isWorst ? '<span class="wf-detail-worst">▼ Worst</span>' : ''}
    </div>
    <div class="wf-detail-grid">
      <div class="wf-detail-row">
        <span class="wf-detail-label">Train Period</span>
        <span class="wf-detail-value">${formatPeriod(w.train_period)}</span>
      </div>
      <div class="wf-detail-row">
        <span class="wf-detail-label">Test Period</span>
        <span class="wf-detail-value">${formatPeriod(w.test_period)}</span>
      </div>
      <div class="wf-detail-row">
        <span class="wf-detail-label">Train Metric</span>
        <span class="wf-detail-value">${w.train_metric != null ? Number(w.train_metric).toFixed(4) : '—'}</span>
      </div>
      <div class="wf-detail-row">
        <span class="wf-detail-label">Test Metric</span>
        <span class="wf-detail-value">${w.test_metric != null ? Number(w.test_metric).toFixed(4) : '—'}</span>
      </div>
      <div class="wf-detail-row">
        <span class="wf-detail-label">Delta</span>
        <span class="wf-detail-value" style="color: ${w.delta != null && w.delta < 0 ? '#ef5350' : '#26a69a'};">
          ${w.delta != null ? (w.delta >= 0 ? '+' : '') + Number(w.delta).toFixed(4) : '—'}
        </span>
      </div>
      <div class="wf-detail-row">
        <span class="wf-detail-label">Delta %</span>
        <span class="wf-detail-value" style="color: ${w.delta_pct != null && w.delta_pct < 0 ? '#ef5350' : '#26a69a'};">
          ${w.delta_pct != null ? (w.delta_pct >= 0 ? '+' : '') + Number(w.delta_pct).toFixed(1) + '%' : '—'}
        </span>
      </div>
      <div class="wf-detail-row">
        <span class="wf-detail-label">Regime Tags</span>
        <span class="wf-detail-value wf-detail-tags">
          ${(w.regime_tags || []).length > 0
            ? w.regime_tags.map(t => `<span class="wf-tag">${t}</span>`).join('')
            : '<span class="wf-tag wf-tag-none">none</span>'}
        </span>
      </div>
    </div>
  `;
}

/* ── Helpers ───────────────────────────────────────────────────────────────── */

/**
 * Get verdict color scheme (VAL-WFUI-005).
 */
function getVerdictColor(verdict) {
  switch (verdict) {
    case 'STABLE':
      return { bg: 'rgba(38,166,154,0.15)', text: '#26a69a', border: 'rgba(38,166,154,0.4)' };
    case 'CONDITIONALLY_STABLE':
      return { bg: 'rgba(247,197,72,0.15)', text: '#f7c548', border: 'rgba(247,197,72,0.4)' };
    case 'UNSTABLE':
      return { bg: 'rgba(239,83,80,0.15)', text: '#ef5350', border: 'rgba(239,83,80,0.4)' };
    default:
      return { bg: 'rgba(120,123,134,0.15)', text: '#787b86', border: 'rgba(120,123,134,0.4)' };
  }
}

/**
 * Format a period object { start, end } for display.
 */
function formatPeriod(period) {
  if (!period) return '—';
  const s = period.start || '?';
  const e = period.end || '?';
  return `${s} → ${e}`;
}

/**
 * Format a date string to short form (e.g., "Jan 2024" or "2024-01").
 */
function formatPeriodShort(dateStr) {
  if (!dateStr) return '?';
  // Try to shorten ISO date to Mon YY format
  const parts = dateStr.split('-');
  if (parts.length >= 2) {
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const monthIdx = parseInt(parts[1], 10) - 1;
    const year = parts[0].slice(2);
    if (monthIdx >= 0 && monthIdx < 12) {
      return `${months[monthIdx]}'${year}`;
    }
  }
  return dateStr;
}
