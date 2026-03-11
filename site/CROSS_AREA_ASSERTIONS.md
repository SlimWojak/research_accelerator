# Phase 3 Cross-Area Validation Assertions — Comparison Interface

---

### VAL-CROSS-P3-001
**Title:** First-visit navigation flow from index to comparison tool  
**Behavioral description:** User opens `index.html` in a browser. The page renders without errors and displays a visible, clickable link/card to the comparison tool (`compare.html`). User clicks the link. `compare.html` loads successfully. The default tab (Chart) is active and displays candlestick price data with at least one config's detection markers overlaid. The three other tabs (Stats, Heatmap, Walk-Forward) are visible and clickable. Pass if: index.html renders with a comparison link, clicking it navigates to compare.html, the Chart tab is active by default, candlestick data is visible, and all four tab labels are present in the DOM.  
**Evidence:** Screenshot of index.html showing comparison link; screenshot of compare.html showing Chart tab active with candlestick data and all four tab labels visible; browser console log showing zero errors during the flow.

---

### VAL-CROSS-P3-002
**Title:** Config selection propagates across all tabs  
**Behavioral description:** On the Chart tab, user selects/deselects configs from the config selector (e.g., toggles "candidate_relaxed" on alongside "current_locked"). User then switches to Stats tab — the stats dashboard shows data for exactly the selected config(s) (matching `per_config` keys from Schema 4B). User switches to Heatmap tab — the `current_lock` marker in Schema 4D corresponds to one of the selected configs. User switches to Walk-Forward tab — the walk-forward data shown corresponds to one of the selected configs. Pass if: the config selection made on the Chart tab is reflected on Stats, Heatmap, and Walk-Forward tabs without requiring re-selection.  
**Evidence:** Screenshot of Chart tab with two configs selected; screenshot of Stats tab showing stats for both configs; screenshot of Heatmap tab with `current_lock` marker visible; screenshot of Walk-Forward tab with matching config name displayed; no console errors.

---

### VAL-CROSS-P3-003
**Title:** Tab state preservation on Chart tab  
**Behavioral description:** User is on the Chart tab. User navigates to a specific day or scrolls to a specific time region on the chart (visible time range is not the default). User then switches to the Stats tab, interacts briefly, and switches back to the Chart tab. The chart's visible time range (scroll position and zoom level) is preserved — the same candles are visible as before switching away. Pass if: the chart's visible time range after returning matches the visible time range before leaving (within ±2 candles tolerance).  
**Evidence:** Screenshot of Chart tab at custom scroll position before switching; screenshot of Chart tab after returning showing same time region; console log confirming no chart re-initialization on tab return.

---

### VAL-CROSS-P3-004
**Title:** Divergence navigator click scrolls chart to detection point  
**Behavioral description:** User navigates to the divergence navigator (which reads from Schema 4C `divergence_index`). The navigator displays a list of divergence entries showing time, primitive, and which config(s) detected. User clicks a divergence entry where `in_a=true, in_b=false`. The Chart tab activates (if not already active), and the chart auto-scrolls to center on the timestamp of that divergence entry. Detection markers are visible at or near that timestamp — config A's marker is present and config B's marker is absent at that point. Pass if: clicking a divergence entry navigates to the Chart tab, the chart viewport includes the divergence timestamp, and the detection marker presence matches the divergence entry's `in_a`/`in_b` flags.  
**Evidence:** Screenshot of divergence navigator with entry highlighted; screenshot of chart scrolled to divergence timestamp showing config A marker present and config B marker absent; console log showing no errors.

---

### VAL-CROSS-P3-005
**Title:** Ground truth annotation persists across page reload  
**Behavioral description:** User is on the Chart tab viewing detection markers. User clicks a detection marker and labels it as "CORRECT" via the ground truth annotation UI. A visual indicator (e.g., checkmark, color change, badge) appears on the marker confirming the label. User reloads the page (full browser refresh). After reload, user navigates back to the same chart region. The detection marker still displays the "CORRECT" visual indicator. The label is retrievable from localStorage (or equivalent persistence). Pass if: label visual indicator appears immediately after labeling, persists after full page reload, and the stored data includes the detection ID and label value.  
**Evidence:** Screenshot of marker before labeling; screenshot of marker after labeling showing visual indicator; screenshot after page reload showing indicator persists; console output or localStorage inspection showing the stored annotation keyed by detection ID.

---

### VAL-CROSS-P3-006
**Title:** Lock flow end-to-end with provenance from Stats, Heatmap, and Walk-Forward  
**Behavioral description:** User reviews the Stats tab (cascade funnel shows config metrics from Schema 4B). User switches to Heatmap tab — confirms the `current_lock` position from Schema 4D is within the `plateau.region` (i.e., `lock_position` is "CENTER" or within plateau bounds). User switches to Walk-Forward tab — confirms `summary.verdict` from Schema 4E is "STABLE" or "CONDITIONALLY_STABLE". User clicks the Lock button/action. The lock is recorded with provenance metadata that includes: the config name, the heatmap plateau status, the walk-forward verdict, and a timestamp. The lock confirmation is visible in the UI. Pass if: lock action succeeds, provenance includes config name + plateau status + walk-forward verdict + timestamp, and a confirmation indicator is displayed.  
**Evidence:** Screenshot of Stats tab showing cascade funnel; screenshot of Heatmap showing lock within plateau; screenshot of Walk-Forward showing STABLE/CONDITIONALLY_STABLE verdict; screenshot of lock confirmation with provenance details; localStorage or console inspection showing stored lock record with all provenance fields.

---

### VAL-CROSS-P3-007
**Title:** Graceful handling of missing eval data (empty/error states)  
**Behavioral description:** User opens `compare.html` when no eval JSON files exist in the expected data path (or the Schema 4A envelope file is missing/empty). The page loads without throwing uncaught exceptions. Each tab displays an informative empty state message (e.g., "No evaluation data found. Run eval.py to generate results.") instead of a blank screen or broken layout. If individual schema files are missing (e.g., `grid_sweep` is `null` in Schema 4A), only the Heatmap tab shows an empty state — other tabs with valid data render normally. Pass if: page loads without console errors (no uncaught exceptions), each tab with missing data shows a human-readable empty state message, and tabs with available data render correctly.  
**Evidence:** Screenshot of each tab when no data exists showing empty state messages; screenshot of Heatmap tab showing empty state when only `grid_sweep` is null while other tabs render normally; browser console log showing zero uncaught exceptions (warnings are acceptable).

---

### VAL-CROSS-P3-008
**Title:** Console-error-free operation during normal usage flow  
**Behavioral description:** User performs a complete normal usage session: opens compare.html, views Chart tab, selects/deselects configs, switches to Stats tab, views cascade funnel, switches to Heatmap tab, hovers over grid cells, switches to Walk-Forward tab, scrolls through windows, clicks a divergence entry, returns to Chart tab. Throughout this entire flow, the browser console contains zero errors (console.error calls, uncaught exceptions, failed network requests for expected resources, or undefined reference errors). Console warnings and info messages are acceptable. Pass if: the browser console shows zero entries at the "error" severity level during the entire session.  
**Evidence:** Browser console log captured with "error" filter active, showing zero entries after the complete usage flow described above.

---

### VAL-CROSS-P3-009
**Title:** Design consistency with existing dark theme design system  
**Behavioral description:** The `compare.html` page uses the same design tokens as the existing calibration pages (`index.html`, `displacement.html`, etc.): background `#0a0e17`, surface `#131722`, surface-2 `#1e222d`, border `#2a2e39`, text `#d1d4dc`, text-muted `#787b86`, accent-teal `#26a69a`, accent-red `#ef5350`, accent-blue `#2962ff`, font `IBM Plex Sans`, font-mono `IBM Plex Mono`. The page has the same header bar style, logo mark, and footer as existing pages. No element uses a color outside the defined palette. Font sizes follow the spec (11px labels, 13px body, 15px headings, 20px page title). Pass if: visual comparison of compare.html header/footer against index.html shows identical styling; CSS custom properties match the defined token values; no hardcoded colors outside the palette appear in the stylesheet.  
**Evidence:** Side-by-side screenshots of compare.html and index.html headers and footers; computed style inspection of `--bg`, `--surface`, `--text`, `--teal`, `--red`, `--blue` CSS variables confirming they match the spec values; grep of the HTML/CSS source confirming no hardcoded hex colors outside the defined palette.

---

### VAL-CROSS-P3-010
**Title:** Responsive chart area fills available space and resizes with window  
**Behavioral description:** On the Chart tab, the chart area fills the remaining horizontal space after any sidebar/controls (if present) and uses at least 500px vertical height. User resizes the browser window (from 1440px width down to 900px width). The chart area proportionally resizes — no horizontal scrollbar appears, chart content reflows, and the chart remains interactive (zoom/pan still work). The chart calls `resize()` or equivalent on window resize. Pass if: chart fills available width at both 1440px and 900px viewport widths, maintains minimum 500px height, no horizontal overflow, and chart interactions work at both sizes.  
**Evidence:** Screenshot at 1440px viewport width showing chart filling available space; screenshot at 900px viewport width showing chart resized without horizontal scrollbar; DOM measurement showing chart container width matches available space (±5px); demonstration that pan/zoom works after resize.

---

### VAL-CROSS-P3-011
**Title:** Stats-to-chart cross-reference via cascade funnel drill-down  
**Behavioral description:** User is on the Stats tab viewing the cascade funnel (Schema 4B `cascade_funnel.levels`). The funnel displays primitive levels with counts. User clicks or selects a specific primitive level (e.g., "displacement" with count 460). The Chart tab activates and displays only/highlights the detection markers for that primitive type, allowing the user to visually verify the detection locations. Pass if: clicking a cascade funnel level transitions to the Chart tab with the corresponding primitive's detections visually distinguished (highlighted, filtered, or annotated).  
**Evidence:** Screenshot of cascade funnel with a level selected; screenshot of Chart tab showing filtered/highlighted markers for the selected primitive; count of visible markers matches the funnel count for that level (±5% tolerance for viewport-limited markers).

---

### VAL-CROSS-P3-012
**Title:** Schema version validation on data load  
**Behavioral description:** When `compare.html` loads the eval JSON data, it reads the `schema_version` field from the Schema 4A envelope. If `schema_version` is missing or the major version does not match the expected version (e.g., page expects `"1.x"` but data has `"2.0"`), the page displays a visible warning banner indicating a schema version mismatch and does not silently render potentially incompatible data. If `schema_version` matches (e.g., `"1.0"` or `"1.1"`), the page renders normally with no warning. Pass if: loading data with mismatched major version shows a warning banner; loading data with matching version shows no warning; the warning includes the expected and actual version numbers.  
**Evidence:** Screenshot of page with matching schema_version showing no warning; screenshot of page with mismatched schema_version showing warning banner with version numbers; console log showing the version check logic executed.
