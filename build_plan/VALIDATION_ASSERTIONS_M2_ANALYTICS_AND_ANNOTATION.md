# Phase 3 — Milestone 2: Analytics & Annotation — Validation Assertions

> **Milestone:** M2 (analytics-and-annotation)
> **Scope:** Heatmap Tab, Walk-Forward Tab, Divergence Navigator, Ground Truth Annotation, Lock Panel
> **Source schemas:** 4C (divergence_index), 4D (grid_sweep), 4E (walk_forward)
> **Date:** 2026-03-09

---

## Area: Heatmap Tab (VAL-HEAT-xxx)

### VAL-HEAT-001 — Heatmap renders from Schema 4D grid data
**Behavioral description:** When the Heatmap tab is active and a valid Schema 4D JSON file is loaded (2D grid with ≥2 x-axis values and ≥2 y-axis values), a color-coded heatmap grid renders with one cell per `grid[i][j]` entry. The number of rendered cells equals `len(axes.x.values) × len(axes.y.values)`. No console errors during render.
**Evidence:** Screenshot of rendered heatmap with cell count matching grid dimensions; console-errors log is empty.

### VAL-HEAT-002 — Current lock marker visible on heatmap
**Behavioral description:** The heatmap displays a distinct marker (crosshair, ring, or highlighted cell border) at the position corresponding to `current_lock.x` and `current_lock.y` from Schema 4D. The marker is visually distinct from all regular cells (e.g., white border or contrasting outline). The marker's position matches the correct cell intersection on both axes.
**Evidence:** Screenshot showing lock marker at correct x/y position; overlay current_lock values from JSON for verification.

### VAL-HEAT-003 — Axis labels show param names and values
**Behavioral description:** The x-axis label displays `axes.x.param` (e.g., "atr_multiplier") and tick marks correspond to each value in `axes.x.values`. The y-axis label displays `axes.y.param` (e.g., "body_ratio") and tick marks correspond to each value in `axes.y.values`. All axis values are readable without truncation or overlap.
**Evidence:** Screenshot of heatmap with axis labels visible; verify param names match Schema 4D axes.

### VAL-HEAT-004 — Cell hover shows metric value and param values in tooltip
**Behavioral description:** Hovering over any heatmap cell displays a tooltip containing: (1) the metric value for that cell (`grid[i][j]`), (2) the x-axis param name and value (`axes.x.param: axes.x.values[i]`), (3) the y-axis param name and value (`axes.y.param: axes.y.values[j]`). Tooltip disappears when cursor leaves the cell.
**Evidence:** Screenshot of tooltip visible on hover; verify displayed values match JSON data for that cell.

### VAL-HEAT-005 — Color scale visible and appropriate for dark theme
**Behavioral description:** A color scale legend is visible adjacent to the heatmap showing the mapping from metric value range (min to max of grid values) to color. Colors are distinguishable on the dark background (#0a0e17 / #131722). The scale uses at minimum 3 distinct color stops. Cell colors correspond correctly to their metric values per the legend.
**Evidence:** Screenshot showing color scale legend with gradient; visual confirmation cells match legend.

### VAL-HEAT-006 — Heatmap title shows primitive name and metric
**Behavioral description:** A title element above or within the heatmap tab displays the `primitive` field and `metric` field from Schema 4D (e.g., "displacement — cascade_to_mss_rate"). The title updates if different sweep data is loaded.
**Evidence:** Screenshot showing title text; verify it matches `primitive` and `metric` from loaded JSON.

### VAL-HEAT-007 — 1D degenerate grid renders as line chart
**Behavioral description:** When Schema 4D data has `axes.y.param === "_single"` and `axes.y.values === [0]` (1D sweep), the heatmap tab renders a line chart instead of a 2D heatmap. The line chart has a single continuous line connecting all data points. No heatmap grid is shown.
**Evidence:** Screenshot of line chart for 1D data; verify no heatmap grid element is present in DOM.

### VAL-HEAT-008 — 1D line chart shows param values on x-axis and metric on y-axis
**Behavioral description:** For a 1D degenerate grid, the line chart x-axis displays the `axes.x.param` name as label and `axes.x.values` as tick values. The y-axis displays the metric values from `grid[0]`. Each point on the line corresponds to `(axes.x.values[j], grid[0][j])`. Current lock marker is visible as a highlighted point on the line at `current_lock.x`.
**Evidence:** Screenshot of 1D line chart with labeled axes; verify data points match JSON values.

### VAL-HEAT-009 — Data loads from separate sweep JSON file
**Behavioral description:** The heatmap tab fetches Schema 4D data from a dedicated JSON file (not embedded in Schema 4A inline). A network request for the sweep file is visible in the Network tab. If the file fails to load (404 or network error), a user-visible message is shown (not a blank tab) and no unhandled console errors occur.
**Evidence:** Network tab showing fetch request for sweep JSON; error-state screenshot for missing file.

### VAL-HEAT-010 — Plateau region outline rendered when detected
**Behavioral description:** When Schema 4D includes `plateau.detected === true`, the heatmap renders a visible outline (border or shaded overlay) around the region defined by `plateau.region.x_range` and `plateau.region.y_range`. The outlined area visually encompasses all cells within the plateau bounds. When `plateau.detected === false` or plateau is absent, no outline is drawn.
**Evidence:** Screenshot showing plateau outline; verify bounds match `plateau.region` from JSON.

### VAL-HEAT-011 — Null grid cells handled gracefully
**Behavioral description:** When `grid[i][j]` contains `null` (missing/failed evaluation), the corresponding cell renders with a visually distinct "no data" appearance (e.g., hatched pattern, gray fill, or empty) rather than crashing or treating null as 0. Tooltip for null cells indicates data is unavailable.
**Evidence:** Screenshot showing null cell distinct from regular cells; hover tooltip showing "N/A" or equivalent.

---

## Area: Walk-Forward Tab (VAL-WF-xxx)

### VAL-WF-001 — Line chart renders train and test metrics across windows
**Behavioral description:** When the Walk-Forward tab is active and valid Schema 4E data is loaded, a line chart renders with one data point per entry in `windows[]`. The x-axis represents window indices (or test period labels). Two lines are drawn: one for `train_metric` values and one for `test_metric` values across all windows. The chart has at least as many data points as `windows.length`.
**Evidence:** Screenshot of walk-forward line chart showing two lines; verify point count matches windows array length.

### VAL-WF-002 — Train and test lines visually distinct
**Behavioral description:** The train metric line and test metric line use different visual encodings (different colors, different dash styles, or both). A legend or inline label identifies which line is "Train" and which is "Test". The two lines are distinguishable without relying solely on color (accessible to colorblind users via dash style or markers).
**Evidence:** Screenshot showing two distinct lines with legend; verify contrast on dark theme.

### VAL-WF-003 — Shaded delta bands between train and test
**Behavioral description:** The area between the train metric line and the test metric line is filled with a semi-transparent shaded band. The band color or opacity may vary to indicate positive vs negative delta (test above vs below train). The shading is visible but does not obscure the lines themselves.
**Evidence:** Screenshot showing shaded region between the two lines.

### VAL-WF-004 — Pass/fail per window visually indicated
**Behavioral description:** Each window's data point (or the region between consecutive window boundaries) is color-coded based on `windows[].passed`: green-tinted for `true`, red-tinted for `false`. The visual indication is unambiguous — a failed window is immediately identifiable without hovering.
**Evidence:** Screenshot showing mixed pass/fail windows with distinct green/red coloring; verify against `passed` field in JSON.

### VAL-WF-005 — Summary verdict badge shows stability status
**Behavioral description:** A badge element displays the `summary.verdict` value (one of: "STABLE", "CONDITIONALLY_STABLE", "UNSTABLE") with color-coding: green for STABLE, amber/yellow for CONDITIONALLY_STABLE, red for UNSTABLE. The badge is visible without scrolling when the Walk-Forward tab is active.
**Evidence:** Screenshot showing verdict badge with correct text and color for loaded data.

### VAL-WF-006 — Summary stats displayed
**Behavioral description:** The Walk-Forward tab displays the following summary statistics from `summary`: `windows_total`, `windows_passed`, `windows_failed`, `mean_test_metric`, `std_test_metric`, `mean_delta`, and `pass_threshold_pct`. Values use monospace font and numeric formatting (e.g., 2 decimal places for metrics, percentage for threshold). All fields are labeled.
**Evidence:** Screenshot showing summary stats panel; verify each value matches Schema 4E summary fields.

### VAL-WF-007 — Window details on hover/click
**Behavioral description:** Hovering over or clicking a window data point on the chart reveals details including: `train_period.start`–`train_period.end`, `test_period.start`–`test_period.end`, `train_metric`, `test_metric`, `delta`, `delta_pct`, `regime_tags`, and `passed` status. The detail view (tooltip or side panel) is readable on the dark theme.
**Evidence:** Screenshot of window detail tooltip/panel; verify all fields present and matching JSON for that window_index.

### VAL-WF-008 — Pass threshold shown on chart
**Behavioral description:** A visual indicator on the chart represents the `pass_threshold_pct` (default 15%). This may be rendered as a shaded band around the train line (±15%), a reference line, or annotated delta boundary. The threshold value is labeled (e.g., "±15% threshold").
**Evidence:** Screenshot showing threshold indicator with label on the chart.

### VAL-WF-009 — Data loads from walk-forward JSON file
**Behavioral description:** The Walk-Forward tab fetches Schema 4E data from a dedicated JSON file. A network request is visible in the Network tab. If the file fails to load, a user-visible error or "no data" state is shown, not a blank tab. No unhandled console errors.
**Evidence:** Network tab showing fetch request; error-state screenshot for missing file.

### VAL-WF-010 — Worst window highlighted
**Behavioral description:** The window identified by `summary.worst_window.window_index` is visually emphasized (larger marker, special icon, or annotation) on the chart. The emphasis is distinct from the standard pass/fail coloring. The worst window's test period and metric value are displayed as an annotation or in the summary panel.
**Evidence:** Screenshot showing worst window with distinct visual treatment; verify index matches JSON.

### VAL-WF-011 — Degradation flag displayed when true
**Behavioral description:** When `summary.degradation_flag === true`, a warning indicator is visible in the summary area (e.g., warning icon, amber text, or "Degradation Detected" label). When `degradation_flag === false`, no warning indicator is shown.
**Evidence:** Screenshot showing degradation warning for data with flag=true; screenshot showing absence for flag=false.

---

## Area: Divergence Navigator (VAL-DIV-xxx)

### VAL-DIV-001 — Divergence list panel visible within Chart tab
**Behavioral description:** When the Chart tab is active, a divergence navigator panel is visible as a sidebar, drawer, or embedded list within the chart view. The panel has a clear heading (e.g., "Divergences" or "Divergence Navigator"). It does not occlude the chart when both are visible.
**Evidence:** Screenshot showing Chart tab with divergence panel visible alongside the chart.

### VAL-DIV-002 — List populated from Schema 4C divergence_index
**Behavioral description:** The divergence list displays one entry per item in `pairwise.{pair}.divergence_index[]` from Schema 4C. The total number of entries in the list matches the length of `divergence_index`. If the divergence_index is empty, the list shows an "No divergences" empty state.
**Evidence:** Screenshot showing list entries; count verification against JSON divergence_index length.

### VAL-DIV-003 — Each entry shows timestamp, primitive, TF, and config detection status
**Behavioral description:** Each divergence list entry displays: (1) `time` formatted as a readable timestamp, (2) `primitive` name, (3) `tf` value, (4) indication of which config(s) detected it — derived from `in_a` and `in_b` booleans (e.g., "A only", "B only", "Both"). All four fields are visible without expanding the entry.
**Evidence:** Screenshot of individual list entry; verify fields match a specific divergence_index entry from JSON.

### VAL-DIV-004 — Click entry scrolls chart to that timestamp
**Behavioral description:** Clicking a divergence list entry causes the chart's time scale to scroll/pan so that the entry's `time` timestamp is centered or visible in the chart viewport. The chart visually updates within 500ms of click. If the timestamp is already visible, the chart does not scroll unnecessarily.
**Evidence:** Screenshot before click (entry off-screen on chart) and after click (entry timestamp centered on chart).

### VAL-DIV-005 — Filter by primitive works
**Behavioral description:** A dropdown, checkbox group, or filter control allows filtering the divergence list by `primitive` name. Selecting a specific primitive shows only entries where `primitive` matches the selected value. Selecting "All" or clearing the filter restores all entries. The count summary updates to reflect the filtered set.
**Evidence:** Screenshot of filter control; screenshot showing filtered list with only matching primitive entries.

### VAL-DIV-006 — Count summary shown
**Behavioral description:** The divergence navigator displays a count summary including: total divergences, count where `in_a && !in_b` (only_in_a), count where `!in_a && in_b` (only_in_b), and optionally count where `in_a && in_b` (agreed). These counts are computed from the divergence_index and displayed in labeled fields.
**Evidence:** Screenshot of count summary; verify numbers match manual count from JSON divergence_index.

### VAL-DIV-007 — Entries color-coded by type
**Behavioral description:** Divergence list entries use distinct colors based on detection type: entries where `in_a && !in_b` use one color (e.g., teal/Config A color), entries where `!in_a && in_b` use another color (e.g., red/Config B color), and entries where `in_a && in_b` use a neutral or third color. The color coding is consistent with the legend or count summary labels.
**Evidence:** Screenshot showing differently colored entries; verify coloring matches `in_a`/`in_b` values from JSON.

### VAL-DIV-008 — List scrollable when many divergences
**Behavioral description:** When the divergence_index contains more entries than fit in the visible panel area (e.g., >20 entries), the list panel becomes scrollable (overflow-y: auto or scroll). Scrolling works via mouse wheel and drag. The list does not cause the page layout to overflow or push the chart off-screen.
**Evidence:** Screenshot showing scroll indicator on a list with >20 entries; verify chart remains fully visible.

---

## Area: Ground Truth Annotation (VAL-GT-xxx)

### VAL-GT-001 — Click detection marker opens label popover
**Behavioral description:** Clicking on any detection marker rendered on the chart (from Schema 4B detections[]) opens a popover/popup near the clicked marker. The popover appears within 300ms of click. Only one popover is open at a time (clicking another marker closes the previous one). Clicking outside the popover closes it.
**Evidence:** Screenshot showing popover adjacent to a clicked marker; verify popover position is near the marker.

### VAL-GT-002 — Popover shows three label options
**Behavioral description:** The label popover displays exactly three selectable options: "CORRECT" (with green indicator or ✓), "NOISE" (with red indicator or ✗), and "BORDERLINE" (with amber indicator or ?). Each option is a distinct clickable element. No other label values are available.
**Evidence:** Screenshot of open popover showing all three options with visual indicators.

### VAL-GT-003 — Selecting a label closes popover and updates marker visual
**Behavioral description:** Clicking one of the three label options immediately: (1) closes the popover, (2) updates the detection marker's visual appearance to reflect the selected label. The update is visible without page refresh. The marker change persists while the page is open.
**Evidence:** Screenshot before labeling (plain marker) and after labeling (marker with colored ring); verify popover is closed after selection.

### VAL-GT-004 — Labeled markers show colored ring
**Behavioral description:** After labeling, markers display a colored ring indicator: green ring for CORRECT, red ring for NOISE, amber ring for BORDERLINE. The ring is visually distinct from the base marker shape and color. Unlabeled markers have no ring. The ring color matches the label regardless of the marker's original color (bullish/bearish).
**Evidence:** Screenshot showing markers with all three ring colors alongside unlabeled markers.

### VAL-GT-005 — Labels persist to ground_truth_labels.json
**Behavioral description:** After applying a label, the label data is saved to a `ground_truth_labels.json` file (or equivalent persistence endpoint). The saved record contains at minimum: `detection_id`, `primitive`, `timeframe`, `label` (CORRECT/NOISE/BORDERLINE), and `labelled_date` (ISO 8601 timestamp). A network request (POST/PUT or file write) is observable when a label is applied.
**Evidence:** Network tab showing save request with payload; read contents of ground_truth_labels.json verifying record exists.

### VAL-GT-006 — Labels load automatically on page refresh
**Behavioral description:** After labeling markers and refreshing the page (F5 or navigation reload), previously labeled markers display their correct colored rings without any manual action. The page fetches ground_truth_labels.json on load and applies stored labels to matching detection markers.
**Evidence:** Screenshot after page refresh showing labeled markers with rings intact; network tab showing fetch of labels file.

### VAL-GT-007 — Previously labeled markers show their labels on reload
**Behavioral description:** On page load, for each entry in ground_truth_labels.json, the system matches `detection_id` to rendered detection markers and applies the stored `label` value's visual ring. All previously labeled markers across all visible days and timeframes show correct rings after load completes. No labels are lost or mismatched.
**Evidence:** Label 3+ markers across different primitives/times, reload page, verify all 3+ markers show correct ring colors.

### VAL-GT-008 — Can change a label
**Behavioral description:** Clicking a previously labeled marker opens the label popover showing the current label as selected/highlighted. Selecting a different label updates the marker's ring color to the new label and saves the updated label to ground_truth_labels.json (overwriting the previous value for that detection_id). The change persists across page refreshes.
**Evidence:** Screenshot showing re-labeling workflow: original label → popover with current highlighted → new label applied; verify updated value in JSON file after refresh.

### VAL-GT-009 — Labels are scoped per-primitive and per-timeframe
**Behavioral description:** Labels are stored with `primitive` and `timeframe` fields. A displacement detection labeled CORRECT on 5m does not affect the label state of any other primitive or timeframe. The detection_id includes primitive and timeframe information ensuring no cross-contamination of labels.
**Evidence:** Label a displacement 5m detection as CORRECT, verify no FVG or 1m markers are affected; inspect JSON showing primitive and timeframe fields.

### VAL-GT-010 — Popover positioned within viewport bounds
**Behavioral description:** The label popover is positioned so it remains fully visible within the viewport. When a marker is near the right edge, the popover opens to the left. When near the bottom, it opens upward. The popover never overflows off-screen or under the sidebar.
**Evidence:** Screenshots of popover on markers at chart edges (top-right, bottom-left corners) showing full popover visibility.

---

## Area: Lock Panel (VAL-LOCK-xxx)

### VAL-LOCK-001 — Lock panel section visible on the page
**Behavioral description:** A dedicated Lock Panel section is visible on the comparison interface page (as a sidebar section, tab panel, or dedicated area). The panel has a clear heading (e.g., "Lock & Provenance" or "Parameter Lock"). It is accessible without scrolling from the main view or via a clearly labeled UI control.
**Evidence:** Screenshot showing lock panel with heading visible.

### VAL-LOCK-002 — Shows current lock parameters
**Behavioral description:** The lock panel displays the currently locked parameter values sourced from the loaded config (e.g., `atr_multiplier: 1.5`, `body_ratio: 0.60`). Parameters are displayed as labeled key-value pairs using monospace font. The displayed values match the `current_lock` or config `params` from the loaded evaluation data.
**Evidence:** Screenshot of lock parameters display; verify values match loaded config JSON.

### VAL-LOCK-003 — Shows comparison summary
**Behavioral description:** The lock panel displays a comparison summary showing which configs were compared (e.g., "current_locked vs candidate_relaxed"). The summary includes at minimum the config names from `Schema 4A.configs[]`. If pairwise comparison data is loaded, agreement rate or key differentiator is shown.
**Evidence:** Screenshot showing comparison summary with config names; verify against Schema 4A configs field.

### VAL-LOCK-004 — Shows walk-forward verdict status
**Behavioral description:** The lock panel displays the walk-forward validation verdict from Schema 4E (`summary.verdict`). The verdict is color-coded: green for STABLE, amber for CONDITIONALLY_STABLE, red for UNSTABLE. If walk-forward data is not available (null), the panel shows "No walk-forward data" or equivalent, not an error.
**Evidence:** Screenshot showing verdict in lock panel with correct color; verify text matches Schema 4E verdict.

### VAL-LOCK-005 — Record lock button creates a lock record
**Behavioral description:** The lock panel contains a "Record Lock" button (or equivalent action). Clicking it creates a lock record containing at minimum: `primitive`, `variant`, `params_locked`, `locked_date` (auto-populated with current ISO 8601 timestamp), `dataset_evaluated`, and `configs_compared`. The button provides visual feedback on click (loading state or success confirmation).
**Evidence:** Click record lock button; verify visual feedback; inspect created record for required fields.

### VAL-LOCK-006 — Lock record saved to lock_records.json
**Behavioral description:** After clicking Record Lock, the lock record is persisted to a `lock_records.json` file (or equivalent endpoint). A network request (POST/PUT or file write) is observable. The file contains valid JSON with the new record appended (does not overwrite previous records if they exist). Reading the file after save confirms the record is present.
**Evidence:** Network tab showing save request; read lock_records.json contents verifying new record exists alongside any prior records.

### VAL-LOCK-007 — Lock record includes provenance fields
**Behavioral description:** The saved lock record includes full provenance: `configs_compared` (list of config names), `walk_forward_validation.status` (PASSED/CONDITIONALLY_PASSED/FAILED or the verdict), `walk_forward_validation.windows_passed` and `windows_failed` counts, and `locked_date` timestamp. These fields enable audit trail of why a parameter was locked.
**Evidence:** Read lock_records.json; verify all provenance fields are present and non-null in the saved record.

### VAL-LOCK-008 — Lock button disabled when walk-forward verdict is UNSTABLE
**Behavioral description:** When the walk-forward verdict is "UNSTABLE", the Record Lock button is disabled (grayed out, non-clickable) with a tooltip or label explaining why (e.g., "Walk-forward validation failed — cannot lock"). When verdict is STABLE or CONDITIONALLY_STABLE, the button is enabled. When no walk-forward data exists, the button behavior follows a defined policy (either disabled with explanation or enabled with warning).
**Evidence:** Screenshot showing disabled button with UNSTABLE verdict and tooltip; screenshot showing enabled button with STABLE verdict.
