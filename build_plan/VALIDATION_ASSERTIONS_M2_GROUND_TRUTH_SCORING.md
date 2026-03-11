# Phase 4 — Milestone 2: Ground Truth Scoring — Validation Assertions

> **Milestone:** M2 (ground-truth-scoring)
> **Scope:** Label Ingestion, Precision/Recall/F1 Scoring Pipeline, Scored Comparison Output, Ground Truth Dashboard, Label Data Generation
> **Source schemas:** 4A–4E (existing), 4F (new — scored output)
> **Depends on:** Phase 3 ground-truth.js (localStorage), Phase 3.5 validate-gt.js (disk), eval.py compare, detect.py
> **Date:** 2026-03-10

---

## Area: Label Ingestion (VAL-LING-xxx)

### VAL-LING-001 — Loads labels from validate-mode disk JSON
**Behavioral description:** The ingestion module reads label files from `site/data/labels/*.json` (one file per week, e.g., `2025-W43.json`). Each file is a JSON array of label objects. The module discovers all `.json` files in the labels directory and loads them into a unified list. After loading, the combined label count equals the sum of entries across all per-week files. No errors are raised for well-formed files.
**Evidence:** Terminal output showing loaded label count per file and total; Python assertion that `len(all_labels) == sum(len(json.load(f)) for f in label_files)`.

### VAL-LING-002 — Loads labels from compare-mode export JSON
**Behavioral description:** The ingestion module accepts a compare-mode export file (`ground_truth_labels.json`) produced by the "Export Labels" button in `compare.html`. This file is a JSON array of objects with fields `{detection_id, primitive, timeframe, label, labelled_date}`. The module loads all entries and produces the same canonical format as validate-mode labels. Label count matches the number of entries in the export file.
**Evidence:** Terminal output showing loaded label count; Python assertion that `len(loaded) == len(json.load(open('ground_truth_labels.json')))`.

### VAL-LING-003 — Normalizes labels to canonical format
**Behavioral description:** Regardless of source (validate-mode disk or compare-mode export), every loaded label is normalized to the canonical schema: `{detection_id: str, primitive: str, timeframe: str, label: str, labelled_by: str}`. The `label` field is one of `CORRECT`, `NOISE`, or `BORDERLINE` (uppercase). The `labelled_by` field is set to `"validate"` for disk labels and `"compare"` for export labels. The `detection_id` follows the pattern `{primitive}_{tf}_{timestamp}_{direction}`. Validate-mode fields (`direction`, `forex_day`, `labeled_at`) are preserved as optional extras but the five canonical fields are always present.
**Evidence:** Python assertion checking all five required fields are present and non-null for every label; assertion that `label` ∈ `{CORRECT, NOISE, BORDERLINE}` for every entry; assertion that `labelled_by` ∈ `{validate, compare}`.

### VAL-LING-004 — Handles empty label directory gracefully
**Behavioral description:** When the `site/data/labels/` directory exists but contains no `.json` files, the ingestion module returns an empty list (not `None`, not an error). When the directory does not exist, the module returns an empty list and logs a warning (not an exception). When a label file exists but contains an empty JSON array `[]`, it is loaded without error and contributes zero labels.
**Evidence:** Terminal output showing `0 labels loaded` with no traceback; Python assertion `isinstance(result, list) and len(result) == 0`.

### VAL-LING-005 — Handles malformed label files gracefully
**Behavioral description:** When a label file contains invalid JSON (syntax error) or unexpected structure (e.g., a JSON object instead of array), the ingestion module skips that file, logs a warning identifying the file path and error, and continues loading remaining files. Valid files are still loaded successfully. The module does not crash or abort on a single bad file.
**Evidence:** Terminal output showing warning for bad file with path; Python assertion that labels from valid files are still present in the result.

### VAL-LING-006 — Label counts reported correctly
**Behavioral description:** After ingestion, the module reports: total label count, count per label value (CORRECT / NOISE / BORDERLINE), count per primitive, and count per source (`validate` vs `compare`). These counts are returned as a summary dict and optionally logged. The sum of per-label-value counts equals the total count. The sum of per-primitive counts equals the total count.
**Evidence:** Terminal log showing summary; Python assertion `counts['CORRECT'] + counts['NOISE'] + counts['BORDERLINE'] == counts['total']`; assertion `sum(counts_by_primitive.values()) == counts['total']`.

### VAL-LING-007 — Deduplication across sources
**Behavioral description:** When the same `detection_id` appears in both a validate-mode file and a compare-mode export file, the ingestion module keeps only one label per `detection_id`. The validate-mode label takes precedence (disk is authoritative over localStorage export). After deduplication, no two labels share the same `detection_id`.
**Evidence:** Python assertion `len(set(l['detection_id'] for l in labels)) == len(labels)`; test with overlapping labels confirms validate-mode version is retained.

---

## Area: Scoring Pipeline (VAL-SCORE-xxx)

### VAL-SCORE-001 — Computes precision per primitive
**Behavioral description:** For each primitive type that has labels, precision is computed as `correct_count / (correct_count + noise_count)`. BORDERLINE labels are excluded from the precision denominator (they are neither correct nor noise for precision purposes). If a primitive has 0 CORRECT and 0 NOISE labels (only BORDERLINE or no labels), precision is reported as `null` (not 0.0, not NaN). The value is a float in [0.0, 1.0].
**Evidence:** Python assertion: given labels `[CORRECT, CORRECT, NOISE, BORDERLINE]` for displacement, precision = `2 / (2 + 1)` = `0.667`; terminal output showing precision per primitive.

### VAL-SCORE-002 — Computes recall per primitive
**Behavioral description:** Recall is computed as `detected_correct / total_ground_truth_positives`. `detected_correct` is the count of labels marked CORRECT. `total_ground_truth_positives` is the count of labels marked CORRECT plus any known missed detections (if a ground truth annotation file provides "missed" entries). When only labelled detections exist (no missed entries), recall = `correct_count / (correct_count + missed_count)` where `missed_count` defaults to 0 — making recall = 1.0 when all labelled detections are from the engine output. The value is a float in [0.0, 1.0] or `null` when no ground truth positives exist.
**Evidence:** Python assertion for recall calculation; terminal output per primitive.

### VAL-SCORE-003 — Computes F1 per primitive
**Behavioral description:** F1 score is computed as the harmonic mean of precision and recall: `F1 = 2 * (precision * recall) / (precision + recall)`. When either precision or recall is `null`, F1 is `null`. When both precision and recall are 0.0, F1 is 0.0 (not a division-by-zero error). The value is a float in [0.0, 1.0] or `null`.
**Evidence:** Python assertion: precision=0.667, recall=1.0 → F1=`2 * 0.667 * 1.0 / (0.667 + 1.0)` ≈ 0.800; assertion that F1=null when precision=null.

### VAL-SCORE-004 — Breaks down scores by session
**Behavioral description:** Precision, recall, and F1 are computed per session (asia, lokz, nyokz) in addition to the aggregate per-primitive scores. Session assignment uses the `forex_day` and detection timestamp to determine which session window the detection falls in (matching the session definitions: Asia 19:00–00:00, LOKZ 02:00–05:00, NYOKZ 07:00–10:00). Detections outside all three named sessions are grouped under `"other"`. Each session has its own `{precision, recall, f1}` triplet.
**Evidence:** Terminal output showing per-session metrics; Python assertion that session breakdown keys ⊆ `{asia, lokz, nyokz, other}`.

### VAL-SCORE-005 — Breaks down scores by variant when multiple variants present
**Behavioral description:** When labels span multiple config variants (e.g., `current_locked` vs `candidate_relaxed`), scores are computed per variant in addition to the aggregate. Variant assignment uses the config name embedded in the evaluation run or label metadata. Each variant has its own `{precision, recall, f1}` triplet per primitive. When only one variant exists, the variant breakdown contains a single entry matching the aggregate.
**Evidence:** Python assertion that variant breakdown keys match the config names from the evaluation run; scores per variant are independent.

### VAL-SCORE-006 — Handles edge case: no labels for a primitive
**Behavioral description:** When a primitive (e.g., `liquidity_sweep`) has zero labels, the scoring pipeline returns `{precision: null, recall: null, f1: null, label_count: 0}` for that primitive. No division-by-zero errors, no KeyError, no NaN values. The primitive is still present in the output with its null scores.
**Evidence:** Python assertion that unlabeled primitive has all-null scores and `label_count == 0`; no traceback in terminal output.

### VAL-SCORE-007 — Handles edge case: all labels are BORDERLINE
**Behavioral description:** When all labels for a primitive are BORDERLINE (zero CORRECT, zero NOISE), precision = `null`, recall = `null`, F1 = `null`. The `borderline_count` field accurately reflects the count. This is distinct from the "no labels" case because `label_count > 0`.
**Evidence:** Python assertion: 5 BORDERLINE labels → `{precision: null, recall: null, f1: null, label_count: 5, borderline_count: 5}`.

### VAL-SCORE-008 — Handles edge case: zero detections for a labelled primitive
**Behavioral description:** When the evaluation run has zero detections for a primitive but labels exist (e.g., from a different run or manually created), the scoring pipeline still computes metrics using only the available labels. Precision and recall are computed from the label counts alone. No crash from empty detection arrays.
**Evidence:** Python assertion confirming scores computed from labels when detection count is 0.

### VAL-SCORE-009 — Output conforms to Schema 4F
**Behavioral description:** The scored output is a JSON object conforming to Schema 4F with structure: `{schema_version: "1.0", scored_at: ISO8601, label_source: {validate_count, compare_count, total}, per_primitive: {displacement: {precision, recall, f1, label_count, correct, noise, borderline, by_session: {...}, by_variant: {...}}, ...}, aggregate: {precision, recall, f1, total_labels}}`. All numeric fields are floats or null. All count fields are non-negative integers. The `schema_version` field is present.
**Evidence:** Python JSON schema validation against Schema 4F definition; `jsonschema.validate(output, schema_4f)` passes without error.

### VAL-SCORE-010 — Scoring is deterministic
**Behavioral description:** Running the scoring pipeline twice on the same labels and detection data produces byte-identical JSON output (excluding the `scored_at` timestamp field). Scores do not vary between runs due to floating-point ordering or set iteration order.
**Evidence:** Python assertion: `output1 == output2` after removing `scored_at` from both.

---

## Area: Scored Comparison (VAL-SCOMP-xxx)

### VAL-SCOMP-001 — eval.py compare includes precision/recall when labels exist
**Behavioral description:** Running `python3 eval.py compare --config <config> --data <data> --labels <labels_dir> --output <dir>` produces an evaluation_run.json that includes a `scored` section alongside the existing Schema 4A fields. The `scored` section contains per-primitive precision, recall, and F1 computed from the provided labels. The `--labels` flag points to a directory or file containing ground truth labels.
**Evidence:** Terminal output showing `Scored metrics included (N labels loaded)`; `jq '.scored.per_primitive.displacement.precision' evaluation_run.json` returns a float value.

### VAL-SCOMP-002 — Comparison output shows per-config precision/recall
**Behavioral description:** When two configs are compared and labels exist, the scored comparison output includes per-config scores: e.g., `"current_locked": {precision: 0.78, recall: 0.90, f1: 0.84}` and `"candidate_relaxed": {precision: 0.93, recall: 0.72, f1: 0.81}`. The scores are derived by joining each config's detections with the label set (matching by `detection_id`). The comparison clearly attributes scores to specific configs.
**Evidence:** Terminal output: `"Config A (current_locked): precision 0.78, Config B (candidate_relaxed): precision 0.93"`; JSON output showing distinct score objects per config key.

### VAL-SCOMP-003 — Works without labels (graceful degradation)
**Behavioral description:** When `eval.py compare` is run without `--labels` flag, or when the labels directory is empty/missing, the command completes successfully and produces the standard Schema 4A output without a `scored` section. No error is raised. A log message indicates `"No labels found — scored metrics skipped"`. The output is byte-compatible with existing Schema 4A consumers (compare.html, etc.).
**Evidence:** Terminal output showing `No labels found — scored metrics skipped`; `jq '.scored' evaluation_run.json` returns `null`; compare.html loads the output without errors.

### VAL-SCOMP-004 — Scored comparison includes delta between configs
**Behavioral description:** When two configs have scores, the output includes a `scored_delta` section showing the difference: `{precision_delta: +0.15, recall_delta: -0.18, f1_delta: -0.03}`. Positive delta means Config B is higher. This enables quick assessment of which config is more precise vs more sensitive.
**Evidence:** Python assertion: `scored_delta['precision_delta'] == config_b_precision - config_a_precision`; terminal output showing delta values.

### VAL-SCOMP-005 — Partial labels produce partial scores
**Behavioral description:** When labels exist for some primitives but not others (e.g., displacement is labelled but fvg is not), the scored output includes scores for labelled primitives and `null` scores for unlabelled ones. The aggregate precision/recall/F1 is computed only from primitives with labels. No primitive is omitted from the output structure.
**Evidence:** JSON output showing `displacement: {precision: 0.8, ...}` alongside `fvg: {precision: null, recall: null, f1: null, label_count: 0}`.

---

## Area: Ground Truth Dashboard (VAL-GTUI-xxx)

### VAL-GTUI-001 — Stats tab shows "Scored" section when label data loaded
**Behavioral description:** When the evaluation run JSON includes a `scored` section (Schema 4F data embedded or linked), the Stats tab in `compare.html` renders an additional "Scored" panel below or alongside the existing detection statistics. The panel has a heading "Ground Truth Scores" or equivalent. When no `scored` data exists, this panel is hidden entirely (not shown as empty).
**Evidence:** Screenshot of Stats tab showing the "Ground Truth Scores" panel; screenshot without scored data showing no such panel.

### VAL-GTUI-002 — Precision/recall/F1 displayed per primitive
**Behavioral description:** The Scored panel displays a table or card layout with one row/card per primitive that has scores. Each entry shows: primitive name, precision (formatted as percentage, e.g., "78.0%"), recall (percentage), F1 (percentage), and label count. Null values display as "—" (em dash), not "null" or "NaN". Colors follow the design system: precision ≥ 0.8 in teal (`#26a69a`), precision < 0.5 in red (`#ef5350`), otherwise default text color.
**Evidence:** Screenshot showing per-primitive score cards with formatted percentages; screenshot showing "—" for a primitive with null precision.

### VAL-GTUI-003 — Per-session breakdown visible
**Behavioral description:** Each primitive's score card is expandable or has a sub-section showing per-session (asia, lokz, nyokz, other) precision/recall/F1. Session names are displayed with their standard colors (Asia: purple, LOKZ: blue, NYOKZ: yellow). Sessions with null scores (no labels in that session) show "—". The breakdown is collapsible to avoid overwhelming the dashboard.
**Evidence:** Screenshot showing expanded session breakdown for displacement with per-session scores; screenshot showing collapsed state.

### VAL-GTUI-004 — Per-variant breakdown visible when variants present
**Behavioral description:** When the evaluation run compares multiple configs (variants), the Scored panel shows scores per variant alongside or instead of the aggregate. Variant names from `configs[]` are used as column headers or section labels. Each variant column shows its own precision/recall/F1 per primitive. When only one variant exists, no variant breakdown is shown (just the aggregate).
**Evidence:** Screenshot showing two-variant score comparison side-by-side; screenshot with single variant showing aggregate only.

### VAL-GTUI-005 — Dashboard handles no-label state gracefully
**Behavioral description:** When the evaluation run JSON has no `scored` section and no labels are available, the Stats tab renders its normal detection statistics without any scoring panel. No "Ground Truth Scores" heading, no empty tables, no error messages related to scoring. The Stats tab functions identically to its pre-Phase-4 behavior.
**Evidence:** Screenshot of Stats tab without scored data showing normal detection stats only; console showing zero errors.

### VAL-GTUI-006 — Score summary badge in tab bar or header
**Behavioral description:** When scored data is available, the Stats tab label or a header badge shows a summary indicator — e.g., "Stats (Scored)" or a small badge icon — to signal that ground truth scores are present. This gives the user immediate visibility without needing to navigate to the Stats tab. When no scores are present, the tab label is unchanged ("Stats").
**Evidence:** Screenshot of tab bar showing "Stats (Scored)" or badge when scored data present; screenshot showing plain "Stats" when not.

### VAL-GTUI-007 — Aggregate scores displayed prominently
**Behavioral description:** At the top of the Scored panel, aggregate scores are displayed prominently: overall precision, recall, F1, and total label count across all primitives. These are computed as label-count-weighted averages of per-primitive scores. The aggregate uses larger font size (≥15px) and is visually separated from per-primitive details.
**Evidence:** Screenshot showing aggregate score section with larger text; Python assertion that aggregate F1 matches weighted average of per-primitive F1.

### VAL-GTUI-008 — Label distribution chart
**Behavioral description:** The Scored panel includes a small Plotly bar chart or donut chart showing the label distribution: CORRECT (teal), NOISE (red), BORDERLINE (yellow) with their counts and percentages. The chart uses the same color constants as the label popover (`#26a69a`, `#ef5350`, `#f7c548`). The chart is compact (≤200px height) and informative.
**Evidence:** Screenshot showing label distribution chart with correct colors and counts matching the data.

---

## Area: Label Data Generation (VAL-LGEN-xxx)

### VAL-LGEN-001 — detect.py can generate data for specific dates
**Behavioral description:** `detect.py` accepts `--dates 2025-10-20,2025-10-21` (comma-separated ISO dates) as an alternative to `--start`/`--end` week ranges. When `--dates` is provided, the batch generator runs the cascade engine only for the specified dates (loading the minimal surrounding data needed for context bars). Output files are organized by the week containing each date. The `--dates` and `--start/--end` flags are mutually exclusive; providing both produces a clear error message.
**Evidence:** Terminal output: `python3 site/detect.py --dates 2025-10-20 --config ... --output ...` produces detection JSON for that date; error message when both `--dates` and `--start` are provided.

### VAL-LGEN-002 — Generated data compatible with validation tool
**Behavioral description:** Detection JSON generated by `detect.py` for specific dates has the identical structure to weekly batch output: `{week, config, generated_at, detections_by_primitive: {primitive: {tf: [detection, ...]}}}`. Each detection has the slim format: `{id, time, direction, type, price, properties}`. The generated file can be loaded by `validate.html` without modification — detection markers render on the chart, and clicking them opens the label popover.
**Evidence:** Load the generated file in `validate.html`; screenshot showing detection markers rendered; screenshot showing label popover opens on click.

### VAL-LGEN-003 — Date-specific generation produces correct week assignment
**Behavioral description:** When generating for `--dates 2025-10-20`, the output file is written to the correct ISO week directory (e.g., `detections/2025-W43.json`). The `week` field in the JSON matches the ISO week containing the requested date. If dates span multiple weeks, separate output files are created per week. The `weeks.json` manifest is updated to include entries for all affected weeks.
**Evidence:** Terminal output showing week assignment; `ls site/data/detections/` confirming file name matches ISO week; `jq '.week' detections/2025-W43.json` returns `"2025-W43"`.

### VAL-LGEN-004 — Generated candle data covers full forex day
**Behavioral description:** When generating for a specific date, the candle JSON includes bars for the complete forex day (Sunday 18:00 NY to next-day 17:00 NY for the requested date's forex day). The candle file has `1m`, `5m`, and `15m` arrays. Session boundaries are generated for the forex day covering the requested date. This ensures the validation tool has full context for labelling.
**Evidence:** Python assertion: candle `1m` array spans from 18:00 previous day to 17:00 requested day; session boundaries JSON includes asia/lokz/nyokz entries for the forex day.

### VAL-LGEN-005 — Date-specific generation includes surrounding context bars
**Behavioral description:** The cascade engine requires lookback bars (for ATR calculation, swing detection, etc.). When generating for a specific date, `detect.py` loads bars starting from at least 2 trading days before the target date to provide sufficient context. The detection output only includes detections with timestamps on the requested date(s), not the context bars. Context bars are used internally but not emitted.
**Evidence:** Terminal log showing `"Loading bars from {context_start} to {target_date} (2-day lookback for context)"`; detection JSON contains only timestamps within the requested date range.

---

_Total assertions: 7 Label Ingestion + 10 Scoring Pipeline + 5 Scored Comparison + 8 Ground Truth Dashboard + 5 Label Data Generation = 35 assertions_
