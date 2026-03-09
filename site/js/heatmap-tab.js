/* ═══════════════════════════════════════════════════════════════════════════════
 * heatmap-tab.js — Parameter Stability Heatmap (Schema 4D grid sweep data)
 * ═══════════════════════════════════════════════════════════════════════════════
 *
 * Renders a 2D Plotly heatmap from Schema 4D grid sweep data.
 * For 1D degenerate grids (axes.y.param === '_single'), renders a line chart.
 * Includes: lock marker overlay, plateau region outline, null cell handling,
 * color scale legend, hover tooltips, and dark theme.
 * ═══════════════════════════════════════════════════════════════════════════════ */

let heatmapInitialized = false;

/**
 * Initialize the Heatmap tab. Called by switchTab() in shared.js when tab is activated.
 */
function initHeatmapTab() {
  const container = document.getElementById('tab-heatmap');
  if (!container) return;

  // If already rendered and data hasn't changed, skip
  if (heatmapInitialized) return;

  const sweepData = app.sweepData;

  // No sweep data — show user-visible error
  if (!sweepData) {
    container.innerHTML = renderHeatmapError('No sweep data available. The sweep JSON file could not be loaded from eval/ directory.');
    heatmapInitialized = true;
    return;
  }

  // Validate minimum structure
  if (!sweepData.axes || !sweepData.axes.x || !sweepData.grid) {
    container.innerHTML = renderHeatmapError('Sweep data is malformed (missing axes or grid).');
    heatmapInitialized = true;
    return;
  }

  // Determine if 1D degenerate grid
  const is1D = sweepData.axes.y && sweepData.axes.y.param === '_single';

  // Build the tab HTML structure
  container.innerHTML = renderHeatmapShell(sweepData, is1D);

  // Render the appropriate chart
  if (is1D) {
    render1DLineChart(sweepData);
  } else {
    render2DHeatmap(sweepData);
  }

  heatmapInitialized = true;
}

/* ── HTML Shells ───────────────────────────────────────────────────────────── */

/**
 * Render the heatmap tab shell with title and chart container.
 */
function renderHeatmapShell(data, is1D) {
  const primitive = primLabel(data.primitive || 'Unknown');
  const metric = (data.metric || 'metric').replace(/_/g, ' ');
  const chartType = is1D ? 'Parameter Sweep (1D)' : 'Parameter Heatmap';

  return `
    <div class="heatmap-layout">
      <div class="heatmap-header">
        <div class="heatmap-title">${primitive} — ${metric}</div>
        <div class="heatmap-subtitle">${chartType}</div>
      </div>
      <div id="heatmap-chart-container" class="heatmap-chart-container"></div>
    </div>
  `;
}

/**
 * Render error state for heatmap tab.
 */
function renderHeatmapError(message) {
  return `
    <div class="tab-placeholder">
      <div class="ph-icon">⚠️</div>
      <div class="ph-title">Heatmap Unavailable</div>
      <div class="ph-desc">${message}</div>
    </div>
  `;
}

/* ── 2D Heatmap Rendering ──────────────────────────────────────────────────── */

/**
 * Render a 2D Plotly heatmap from Schema 4D data.
 */
function render2DHeatmap(data) {
  const chartEl = document.getElementById('heatmap-chart-container');
  if (!chartEl) return;

  // Purge any existing Plotly chart
  Plotly.purge(chartEl);

  const xValues = data.axes.x.values;
  const yValues = data.axes.y.values;
  const xParam = data.axes.x.param || 'x';
  const yParam = data.axes.y.param || 'y';
  const metric = (data.metric || 'metric').replace(/_/g, ' ');
  const grid = data.grid;

  // Transpose grid for Plotly: grid[i][j] = x_values[i], y_values[j]
  // Plotly heatmap z[j][i] where z rows = y, z cols = x
  const zData = [];
  const customData = [];
  const hasNulls = gridHasNulls(grid);

  for (let j = 0; j < yValues.length; j++) {
    const row = [];
    const customRow = [];
    for (let i = 0; i < xValues.length; i++) {
      const val = (i < grid.length && j < grid[i].length) ? grid[i][j] : null;
      row.push(val);
      customRow.push({
        xParam: xParam,
        xVal: xValues[i],
        yParam: yParam,
        yVal: yValues[j],
        metric: metric,
        metricVal: val,
      });
    }
    zData.push(row);
    customData.push(customRow);
  }

  // Build heatmap trace
  const traces = [];

  // Main heatmap trace
  const heatmapTrace = {
    type: 'heatmap',
    z: zData,
    x: xValues.map(String),
    y: yValues.map(String),
    customdata: customData,
    colorscale: buildDarkColorscale(hasNulls),
    colorbar: {
      title: { text: metric, font: { color: '#d1d4dc', size: 11, family: "'IBM Plex Mono', monospace" } },
      tickfont: { color: '#d1d4dc', size: 10, family: "'IBM Plex Mono', monospace" },
      bgcolor: '#131722',
      bordercolor: '#2a2e39',
      borderwidth: 1,
      outlinecolor: '#2a2e39',
      outlinewidth: 1,
      len: 0.85,
    },
    hovertemplate:
      '<b>%{customdata.metric}</b>: %{customdata.metricVal}<br>' +
      '%{customdata.xParam}: %{customdata.xVal}<br>' +
      '%{customdata.yParam}: %{customdata.yVal}' +
      '<extra></extra>',
    zmin: hasNulls ? undefined : undefined,
    connectgaps: false,
  };

  // Handle null cells: replace with NaN for Plotly (shows as gaps)
  for (let j = 0; j < zData.length; j++) {
    for (let i = 0; i < zData[j].length; i++) {
      if (zData[j][i] === null) {
        zData[j][i] = NaN;
        customData[j][i].metricVal = 'N/A';
      }
    }
  }

  traces.push(heatmapTrace);

  // Lock marker overlay — scatter point at current lock position
  const lock = data.current_lock;
  if (lock && lock.x != null && lock.y != null) {
    traces.push({
      type: 'scatter',
      x: [String(lock.x)],
      y: [String(lock.y)],
      mode: 'markers',
      marker: {
        size: 18,
        color: 'rgba(0,0,0,0)',
        line: { color: '#ffffff', width: 3 },
        symbol: 'circle',
      },
      name: 'Current Lock',
      hovertemplate:
        '<b>Current Lock</b><br>' +
        xParam + ': ' + lock.x + '<br>' +
        yParam + ': ' + lock.y + '<br>' +
        'Metric: ' + (lock.metric_value != null ? lock.metric_value : '—') +
        '<extra></extra>',
      showlegend: false,
    });

    // Crosshair lines
    traces.push({
      type: 'scatter',
      x: [String(lock.x), String(lock.x)],
      y: [String(yValues[0]), String(yValues[yValues.length - 1])],
      mode: 'lines',
      line: { color: 'rgba(255,255,255,0.35)', width: 1, dash: 'dot' },
      hoverinfo: 'skip',
      showlegend: false,
    });
    traces.push({
      type: 'scatter',
      x: [String(xValues[0]), String(xValues[xValues.length - 1])],
      y: [String(lock.y), String(lock.y)],
      mode: 'lines',
      line: { color: 'rgba(255,255,255,0.35)', width: 1, dash: 'dot' },
      hoverinfo: 'skip',
      showlegend: false,
    });
  }

  // Plateau region outline
  const plateau = data.plateau;
  if (plateau && plateau.detected === true && plateau.region) {
    const region = plateau.region;
    const xr = region.x_range || [];
    const yr = region.y_range || [];
    if (xr.length === 2 && yr.length === 2) {
      traces.push({
        type: 'scatter',
        x: [String(xr[0]), String(xr[1]), String(xr[1]), String(xr[0]), String(xr[0])],
        y: [String(yr[0]), String(yr[0]), String(yr[1]), String(yr[1]), String(yr[0])],
        mode: 'lines',
        line: { color: '#f7c548', width: 2, dash: 'dash' },
        hoverinfo: 'skip',
        showlegend: false,
        name: 'Plateau Region',
      });
    }
  }

  // Layout
  const layout = plotlyLayout({
    title: {
      text: '',
      font: { size: 1 },
    },
    xaxis: {
      title: { text: xParam, font: { color: '#d1d4dc', size: 12 } },
      type: 'category',
      tickfont: { size: 10, family: "'IBM Plex Mono', monospace" },
      gridcolor: '#1e222d',
      linecolor: '#2a2e39',
    },
    yaxis: {
      title: { text: yParam, font: { color: '#d1d4dc', size: 12 } },
      type: 'category',
      tickfont: { size: 10, family: "'IBM Plex Mono', monospace" },
      gridcolor: '#1e222d',
      linecolor: '#2a2e39',
    },
    margin: { l: 80, r: 100, t: 20, b: 60 },
  });

  Plotly.newPlot(chartEl, traces, layout, PLOTLY_CONFIG);
}

/* ── 1D Line Chart Rendering ───────────────────────────────────────────────── */

/**
 * Render a 1D line chart for degenerate grid (y.param === '_single').
 */
function render1DLineChart(data) {
  const chartEl = document.getElementById('heatmap-chart-container');
  if (!chartEl) return;

  // Purge any existing Plotly chart
  Plotly.purge(chartEl);

  const xValues = data.axes.x.values;
  const xParam = data.axes.x.param || 'x';
  const metric = (data.metric || 'metric').replace(/_/g, ' ');

  // grid[0] is the single row for 1D sweep
  const gridRow = data.grid[0] || [];
  const yVals = [];
  const nullMask = [];

  for (let i = 0; i < xValues.length; i++) {
    const val = i < gridRow.length ? gridRow[i] : null;
    yVals.push(val);
    nullMask.push(val === null);
  }

  const traces = [];

  // Main line trace
  traces.push({
    type: 'scatter',
    x: xValues,
    y: yVals,
    mode: 'lines+markers',
    line: { color: '#26a69a', width: 2 },
    marker: {
      color: yVals.map(v => v === null ? '#4a4e59' : '#26a69a'),
      size: 8,
      line: { color: '#0a0e17', width: 1 },
    },
    name: metric,
    hovertemplate: xValues.map((xv, i) =>
      '<b>' + metric + '</b>: ' + (yVals[i] != null ? yVals[i] : 'N/A') +
      '<br>' + xParam + ': ' + xv + '<extra></extra>'
    ),
    connectgaps: false,
  });

  // Lock marker — highlighted point
  const lock = data.current_lock;
  if (lock && lock.x != null) {
    const lockIdx = xValues.indexOf(lock.x);
    const lockY = lockIdx >= 0 && lockIdx < yVals.length ? yVals[lockIdx] : lock.metric_value;
    if (lockY != null) {
      traces.push({
        type: 'scatter',
        x: [lock.x],
        y: [lockY],
        mode: 'markers',
        marker: {
          size: 16,
          color: '#f7c548',
          symbol: 'diamond',
          line: { color: '#ffffff', width: 2 },
        },
        name: 'Current Lock',
        hovertemplate:
          '<b>Current Lock</b><br>' +
          xParam + ': ' + lock.x + '<br>' +
          metric + ': ' + lockY +
          '<extra></extra>',
        showlegend: true,
      });
    }
  }

  // Layout
  const layout = plotlyLayout({
    title: { text: '' },
    xaxis: {
      title: { text: xParam, font: { color: '#d1d4dc', size: 12 } },
      tickfont: { size: 10, family: "'IBM Plex Mono', monospace" },
      gridcolor: '#1e222d',
      linecolor: '#2a2e39',
    },
    yaxis: {
      title: { text: metric, font: { color: '#d1d4dc', size: 12 } },
      tickfont: { size: 10, family: "'IBM Plex Mono', monospace" },
      gridcolor: '#1e222d',
      linecolor: '#2a2e39',
    },
    margin: { l: 80, r: 40, t: 20, b: 60 },
    showlegend: true,
    legend: {
      font: { color: '#d1d4dc', size: 11, family: "'IBM Plex Mono', monospace" },
      bgcolor: 'rgba(19,23,34,0.8)',
      bordercolor: '#2a2e39',
      borderwidth: 1,
    },
  });

  Plotly.newPlot(chartEl, traces, layout, PLOTLY_CONFIG);
}

/* ── Helpers ───────────────────────────────────────────────────────────────── */

/**
 * Check if any grid cell is null.
 */
function gridHasNulls(grid) {
  for (let i = 0; i < grid.length; i++) {
    for (let j = 0; j < grid[i].length; j++) {
      if (grid[i][j] === null) return true;
    }
  }
  return false;
}

/**
 * Build a dark-theme-appropriate colorscale for heatmaps.
 * Uses a teal-to-yellow gradient that works well on dark backgrounds.
 */
function buildDarkColorscale() {
  return [
    [0.0, '#0d3b66'],
    [0.2, '#1b6b7d'],
    [0.4, '#26a69a'],
    [0.6, '#5cc489'],
    [0.8, '#bcd35f'],
    [1.0, '#f7c548'],
  ];
}
