# Phase 3 Milestone 1 — Validation Contract Assertions
# Scope: Foundation + Chart Tab + Stats Tab (comparison-core)

---

## Area: Foundation (VAL-FOUND-xxx)

### VAL-FOUND-001 — Page loads without console errors
**Behavioral description:** Opening `compare.html` in a browser produces zero errors in the developer console. The page reaches interactive state (all tabs visible, no blank screen). No uncaught exceptions, no failed resource loads.
**Evidence:** Screenshot of the rendered page + screenshot of browser console showing zero errors.

### VAL-FOUND-002 — Tab navigation renders 4 tabs
**Behavioral description:** The page displays exactly 4 tab buttons labeled "Chart", "Stats", "Heatmap", and "Walk-Forward". The Chart tab is active by default (has `.active` styling). All 4 tab labels are visible without scrolling or overflow.
**Evidence:** Screenshot of the tab bar showing all 4 tabs with Chart tab highlighted.

### VAL-FOUND-003 — Tab switching changes visible content
**Behavioral description:** Clicking each tab (Chart → Stats → Heatmap → Walk-Forward → Chart) shows the corresponding content panel and hides all others. Only one panel is visible at a time. The clicked tab receives `.active` styling and previously active tab loses it.
**Evidence:** 4 screenshots, one per tab click, showing the correct panel visible and the correct tab highlighted.

### VAL-FOUND-004 — Lightweight Charts CDN loads successfully
**Behavioral description:** `window.LightweightCharts` is defined and is an object after page load. Specifically, `LightweightCharts.createChart` is a function. The CDN script tag references `lightweight-charts@4.1.3`.
**Evidence:** Console evaluation of `typeof LightweightCharts.createChart === 'function'` returning `true`.

### VAL-FOUND-005 — Plotly.js CDN loads successfully
**Behavioral description:** `window.Plotly` is defined and is an object after page load. Specifically, `Plotly.newPlot` is a function. Plotly is required for Stats tab bar charts and funnel charts.
**Evidence:** Console evaluation of `typeof Plotly.newPlot === 'function'` returning `true`.

### VAL-FOUND-006 — Design system: dark theme applied correctly
**Behavioral description:** The page background color is `#0a0e17` (--bg). Surface panels use `#131722` (--surface). Borders are `#2a2e39` (--border). Primary text is `#d1d4dc` (--text). Font family for body text is IBM Plex Sans. Monospaced numbers use IBM Plex Mono.
**Evidence:** Screenshot of full page + computed style inspection of body background, a panel background, border color, and font-family on a text element and a numeric element.

### VAL-FOUND-007 — Schema 4A JSON loads and parses correctly
**Behavioral description:** The page fetches the evaluation run JSON file from the `eval/` directory. The parsed JSON has the fields: `schema_version`, `run_id`, `configs` (array), `per_config` (object with ≥1 key), and `pairwise`. No parse errors in console.
**Evidence:** Console evaluation showing the top-level keys of the loaded data object matching Schema 4A structure. Network tab showing successful 200 response for the JSON file.

### VAL-FOUND-008 — Loading state visible during data fetch
**Behavioral description:** While the JSON data is being fetched (simulated with network throttling or observable on slow connections), a loading overlay or spinner is visible over the content area. The overlay disappears once data is loaded and rendered. The overlay uses the pattern: centered content on `var(--surface)` background with `z-index: 100`.
**Evidence:** Screenshot captured during loading (network throttled to Slow 3G) showing the loading indicator, then screenshot after load completes showing the indicator gone.

### VAL-FOUND-009 — Error handling for missing JSON files
**Behavioral description:** When the evaluation JSON file is absent or returns 404, the page displays a user-visible error message (not just a console error). The error message is readable (not raw exception text) and indicates the data file could not be loaded. The page does not crash or show a blank white screen.
**Evidence:** Screenshot with JSON file removed showing the error state + console showing graceful error handling (caught error, no uncaught exception).

### VAL-FOUND-010 — Link from index.html navigates to compare.html
**Behavioral description:** The `index.html` page includes a visible link/card that navigates to `compare.html`. Clicking it loads the comparison page successfully. The link text indicates it is the comparison/evaluation tool.
**Evidence:** Screenshot of `index.html` showing the compare link + screenshot after clicking it showing `compare.html` loaded.

### VAL-FOUND-011 — Run metadata displayed in header
**Behavioral description:** The page header or info bar displays the evaluation run metadata: `run_id`, dataset name, date range, and the config names being compared. This information comes from the Schema 4A envelope fields.
**Evidence:** Screenshot of header area showing run_id, dataset info, and config names rendered.

### VAL-FOUND-012 — Responsive resize does not break layout
**Behavioral description:** Resizing the browser window from 1920×1080 down to 1280×720 does not cause layout overflow, overlapping elements, or hidden controls. The chart area resizes smoothly. Tab navigation remains accessible.
**Evidence:** Screenshots at 1920×1080 and 1280×720 showing intact layout.

---

## Area: Chart Tab (VAL-CHART-xxx)

### VAL-CHART-001 — Candlestick chart renders with correct OHLC data
**Behavioral description:** The Chart tab displays a TradingView Lightweight Charts candlestick chart. Candles are visible with correct coloring: green/teal (`#26a69a`) for bullish (close > open), red (`#ef5350`) for bearish (close < open). The price axis shows reasonable FX prices. At least 50 candles are visible in the default view.
**Evidence:** Screenshot of the candlestick chart with visible candles + console log of the first 3 candle data points confirming OHLC values match the source JSON.

### VAL-CHART-002 — Multi-config overlay: distinct color sets per config
**Behavioral description:** When two configs are loaded (Config A and Config B from Schema 4A.per_config), detection markers for Config A use one color set and Config B uses a visually distinct color set. The colors are distinguishable at a glance. A legend or label identifies which color belongs to which config.
**Evidence:** Screenshot showing markers from both configs on the chart with visible color distinction + screenshot of the legend/label identifying configs.

### VAL-CHART-003 — Config toggle: show/hide individual config markers
**Behavioral description:** Toggle controls exist for each config (e.g., checkboxes or buttons labeled with config names). Unchecking/toggling Config A hides all Config A markers while Config B markers remain. Toggling Config A back on restores its markers. Both configs can be hidden simultaneously, showing only candles.
**Evidence:** 3 screenshots: (1) both configs visible, (2) Config A hidden / Config B visible, (3) both hidden.

### VAL-CHART-004 — Primitive layer toggle: show/hide FVG markers
**Behavioral description:** A toggle control for "FVG" exists. When enabled, FVG detection markers (from the per_primitive.fvg data) appear on the chart. When disabled, FVG markers are removed. Other primitive markers are unaffected.
**Evidence:** Screenshots showing FVG toggle on vs off, with other primitives unchanged.

### VAL-CHART-005 — Primitive layer toggle: show/hide displacement markers
**Behavioral description:** A toggle control for "Displacement" exists. When enabled, displacement detection markers appear. When disabled, they are hidden. Other primitives unaffected.
**Evidence:** Screenshots showing displacement toggle on vs off.

### VAL-CHART-006 — Primitive layer toggle: show/hide MSS markers
**Behavioral description:** A toggle control for "MSS" exists. When enabled, MSS (Market Structure Shift) detection markers appear. When disabled, they are hidden. Works independently of other toggles.
**Evidence:** Screenshots showing MSS toggle on vs off.

### VAL-CHART-007 — Primitive layer toggle: show/hide OB markers
**Behavioral description:** A toggle control for "Order Block" (OB) exists. When enabled, OB markers appear (square markers with 'OB' text per the existing pattern). When disabled, they are hidden.
**Evidence:** Screenshots showing OB toggle on vs off.

### VAL-CHART-008 — Primitive layer toggle: show/hide sweep markers
**Behavioral description:** A toggle control for "Liquidity Sweep" exists. When enabled, sweep markers appear. When disabled, they are hidden.
**Evidence:** Screenshots showing sweep toggle on vs off.

### VAL-CHART-009 — TF switching: 1m candles and detections
**Behavioral description:** Clicking the "1m" TF button reloads candles at 1-minute resolution and displays detection markers aligned to 1m bars. The candle count is significantly higher than 5m view (approximately 5× more bars for the same time period). The TF button shows "1m" as active.
**Evidence:** Screenshot of chart at 1m TF + count of visible candles confirming 1m resolution.

### VAL-CHART-010 — TF switching: 5m candles and detections
**Behavioral description:** Clicking the "5m" TF button displays 5-minute candles with detection markers aligned to 5m bars. This is the default TF. Detection counts shown in the summary match the `per_tf["5m"]` data from Schema 4B.
**Evidence:** Screenshot of chart at 5m TF + verification that detection count matches JSON data for 5m.

### VAL-CHART-011 — TF switching: 15m candles and detections
**Behavioral description:** Clicking the "15m" TF button displays 15-minute candles with detection markers aligned to 15m bars. Candle count is approximately 1/3 of the 5m view for the same time period.
**Evidence:** Screenshot of chart at 15m TF + candle count comparison with 5m view.

### VAL-CHART-012 — Day navigation: 5 day tabs visible
**Behavioral description:** Exactly 5 day navigation tabs are displayed. Each tab shows a day label (e.g., "Mon Jan 8", "Tue Jan 9", etc.). One tab is active by default (styled with `--blue` or `--red` border-bottom).
**Evidence:** Screenshot showing all 5 day tabs with one active.

### VAL-CHART-013 — Day navigation: clicking tab switches chart data
**Behavioral description:** Clicking a different day tab loads candle data for that day and displays it. The active tab styling moves to the clicked tab. Detection markers update to show only detections for the selected day's time range. Price levels change to reflect the new day's data.
**Evidence:** Screenshots of 2 different days showing different price levels and different detection markers.

### VAL-CHART-014 — Session boundary bands visible
**Behavioral description:** Vertical colored bands are rendered behind the candles indicating trading sessions: Asia (19:00–00:00), LOKZ (02:00–05:00), NYOKZ (07:00–10:00). Each session uses a distinct fill color with transparency. Bands render at `zOrder: 'bottom'` (behind candles).
**Evidence:** Screenshot showing the colored session bands behind candles with visible color differentiation between the 3 sessions.

### VAL-CHART-015 — Session boundary colors match design system
**Behavioral description:** Session bands use the established color scheme. The session legend (in the chart info bar or sidebar) labels each session with its name and time range, matching the `SES_LABELS` constants.
**Evidence:** Screenshot of session legend + screenshot of bands with color-matched labels.

### VAL-CHART-016 — Detection count summary updates per config per primitive
**Behavioral description:** A summary panel shows detection counts for each primitive (FVG, displacement, MSS, OB, sweep) broken down by config. When the TF or day is changed, the counts update to reflect the currently visible data. Counts match the `detection_count` values from Schema 4B `per_primitive.{p}.per_tf.{tf}`.
**Evidence:** Screenshot of the summary panel + comparison of displayed counts with JSON source data for the current TF.

### VAL-CHART-017 — Chart is scrollable (pan left/right)
**Behavioral description:** Click-dragging horizontally on the chart pans the time axis left and right, revealing candles beyond the initial viewport. The `handleScroll.pressedMouseMove: true` option is active.
**Evidence:** Screenshots showing the chart before and after panning, with the visible time range shifted.

### VAL-CHART-018 — Chart is zoomable (mouse wheel)
**Behavioral description:** Mouse wheel scrolling on the chart zooms in/out on the time axis. Zooming in shows fewer candles with more detail. Zooming out shows more candles. The `handleScale.mouseWheel: true` option is active.
**Evidence:** Screenshots showing the chart at default zoom vs zoomed in vs zoomed out.

### VAL-CHART-019 — Marker positioning: bullish below bar, bearish above bar
**Behavioral description:** Bullish detection markers (direction === "bullish") are positioned below the candle bar (`position: 'belowBar'`, `shape: 'arrowUp'`). Bearish detection markers (direction === "bearish") are positioned above the candle bar (`position: 'aboveBar'`, `shape: 'arrowDown'`). No markers are mispositioned.
**Evidence:** Screenshot showing at least one bullish marker below a bar and one bearish marker above a bar, with direction labels or color confirming the assignment.

### VAL-CHART-020 — Zero detections for a primitive renders gracefully
**Behavioral description:** When a primitive has zero detections for the current day/TF combination (e.g., no liquidity sweeps detected on a given day), the chart renders without errors. The primitive's toggle is still visible and functional. The detection count summary shows "0" for that primitive, not blank or undefined.
**Evidence:** Screenshot of the summary panel showing "0" for a primitive + console showing no errors.

### VAL-CHART-021 — Single config mode renders correctly
**Behavioral description:** When the evaluation run contains only one config (Schema 4A `configs` array has length 1), the chart renders all markers in a single color set without errors. Config toggle controls adapt to show only one config. No "Config B" placeholder or broken UI.
**Evidence:** Screenshot with single-config data loaded showing markers + controls adapted to one config.

### VAL-CHART-022 — Crosshair displays time and price
**Behavioral description:** Moving the mouse over the chart shows a crosshair (vertical + horizontal lines) with time label on the x-axis and price label on the y-axis. Crosshair mode is `Normal`. Line color is `#4a4e5a`, width 1, style dashed.
**Evidence:** Screenshot showing the crosshair with visible time and price labels.

---

## Area: Stats Tab (VAL-STATS-xxx)

### VAL-STATS-001 — Side-by-side stats tables render for compared configs
**Behavioral description:** Switching to the Stats tab displays statistics tables laid out side-by-side (or in a clear comparative layout) for each config in the evaluation run. Column headers or section headers show config names (from Schema 4A `configs[]`). Both tables are visible without horizontal scrolling.
**Evidence:** Screenshot of the Stats tab showing both config stats tables side-by-side.

### VAL-STATS-002 — Detection count shown per primitive per config
**Behavioral description:** For each config, the stats display shows the total detection count for each primitive type (displacement, fvg, mss, order_block, liquidity_sweep). Values match `per_primitive.{p}.per_tf.{tf}.detection_count` from Schema 4B for the currently selected TF.
**Evidence:** Screenshot of detection counts + verification against JSON source data for at least 2 primitives.

### VAL-STATS-003 — Detections per day (mean ± std) shown
**Behavioral description:** For each config and primitive, the mean detections-per-day and standard deviation are displayed (e.g., "7.4 ± 2.1"). Values match `detections_per_day` and `detections_per_day_std` from Schema 4B.
**Evidence:** Screenshot showing mean ± std values + comparison with JSON source data.

### VAL-STATS-004 — Session distribution bar chart renders (Plotly grouped bars)
**Behavioral description:** A Plotly.js grouped bar chart is visible showing detection counts (or percentages) by session (Asia, LOKZ, NYOKZ, Other) with separate bars per config. The x-axis shows 4 session labels. Each config has a distinct bar color. Bar values match `by_session.{session}.count` from Schema 4B.
**Evidence:** Screenshot of the grouped bar chart with visible session labels, config-colored bars, and correct value alignment with source data.

### VAL-STATS-005 — Session percentages sum to 100% per config
**Behavioral description:** The session distribution percentages displayed for each config sum to exactly 100% (within ±0.5% for rounding). Values match `by_session.{session}.pct` from Schema 4B. E.g., asia.pct + lokz.pct + nyokz.pct + other.pct ≈ 100.0 for each config.
**Evidence:** Manual sum of displayed percentages per config confirming they equal 100% (±0.5%).

### VAL-STATS-006 — Direction split: bullish/bearish counts and percentages shown
**Behavioral description:** For each config and the selected primitive, bullish and bearish counts and percentages are displayed. Bullish values use teal color (`#26a69a`), bearish use red (`#ef5350`). Values match `by_direction.bullish.{count, pct}` and `by_direction.bearish.{count, pct}` from Schema 4B. Bull pct + bear pct = 100%.
**Evidence:** Screenshot showing direction split with colored values + verification against JSON data.

### VAL-STATS-007 — Cascade funnel chart renders (Plotly funnel)
**Behavioral description:** A Plotly.js funnel chart is visible showing the cascade funnel levels from Schema 4B `cascade_funnel.levels[]`. The funnel narrows from top (highest count) to bottom (lowest count). Each level bar is labeled with its name and count.
**Evidence:** Screenshot of the funnel chart with visible level names and counts.

### VAL-STATS-008 — Funnel shows correct level ordering (leaf → composite → terminal)
**Behavioral description:** The funnel levels appear in the order defined by `cascade_funnel.levels[]` array from Schema 4B. Leaf primitives (swing_points, displacement, fvg) appear at the top/widest, composite primitives (mss, order_block) in the middle, and terminal primitives (liquidity_sweep) at the narrowest bottom. The `type` field (leaf/composite/terminal) is visually indicated (e.g., color coding or labels).
**Evidence:** Screenshot of funnel with level ordering matching the Schema 4B levels array + type labels visible.

### VAL-STATS-009 — Conversion rates labeled between funnel levels
**Behavioral description:** Between funnel levels, conversion rate labels are displayed (e.g., "from_displacement: 9.6%", "from_mss: 84%"). These values come from `cascade_funnel.levels[].conversion_rates` in Schema 4B. Labels are positioned between the relevant levels.
**Evidence:** Screenshot of funnel with conversion rate labels visible between levels.

### VAL-STATS-010 — Primitive selector switches displayed stats
**Behavioral description:** A primitive selector control (dropdown, radio buttons, or tab bar) allows choosing which primitive's stats are shown in the detail view. Options include at minimum: displacement, fvg, mss, order_block, liquidity_sweep. Selecting a different primitive updates all stats (counts, session distribution, direction split) to reflect the selected primitive's data.
**Evidence:** Screenshots showing stats for 2 different primitives after switching the selector, confirming values changed.

### VAL-STATS-011 — Stats update when different primitive selected
**Behavioral description:** After switching the primitive selector from "displacement" to "fvg", all numerical values update: detection count, detections_per_day, session distribution counts/percentages, direction split counts/percentages. The session bar chart re-renders with new data. No stale data remains from the previous selection.
**Evidence:** Screenshots of stats before and after primitive switch, confirming all values changed to match the new primitive's Schema 4B data.

### VAL-STATS-012 — Zero-detection primitive displays gracefully
**Behavioral description:** When a primitive has zero detections for the current TF (detection_count = 0), the stats tab shows "0" for counts, "0.0 ± 0.0" for per-day stats, all session percentages as "0%" or "—", direction split as "0 / 0", and the bar chart shows empty bars. The funnel still renders with a zero-width bar for that level. No division-by-zero errors, no NaN displayed, no console errors.
**Evidence:** Screenshot of stats tab with a zero-detection primitive selected + console showing no errors.

### VAL-STATS-013 — Single config mode renders stats without comparison layout
**Behavioral description:** When only one config is present (Schema 4A `configs` has length 1), the Stats tab renders a single column of stats (not side-by-side with an empty column). The session bar chart shows single bars (not grouped). The funnel renders for the single config. No empty placeholders or "Config B: N/A" artifacts.
**Evidence:** Screenshot of Stats tab with single-config data showing clean single-config layout.

### VAL-STATS-014 — Pairwise comparison stats displayed
**Behavioral description:** When two configs are compared, pairwise statistics from Schema 4C are displayed: agreement_rate, only_in_a count, only_in_b count, and per-session agreement rates. These values are shown alongside or below the per-config stats. The `config_a` and `config_b` names are labeled correctly.
**Evidence:** Screenshot showing pairwise comparison metrics + verification of agreement_rate value against Schema 4C JSON data.

### VAL-STATS-015 — Stats tab TF consistency with Chart tab
**Behavioral description:** The TF selected on the Chart tab (1m/5m/15m) determines which TF's data is shown on the Stats tab. If the user switches to 5m on Chart, then navigates to Stats, the stats reflect `per_tf["5m"]` data. A TF indicator is visible on the Stats tab confirming which TF's data is displayed.
**Evidence:** Screenshot of Stats tab showing TF indicator + verification that displayed counts match the selected TF's Schema 4B data.

---

_Total assertions: 12 Foundation + 22 Chart + 15 Stats = 49 assertions_
