# Phase 4 — Milestone 3: Parameter Search — Validation Assertions

> **Milestone:** M3 (parameter-search)
> **Scope:** Search CLI, Config Perturbation, Fitness Scoring, Provenance Recording, Winner Review
> **Prerequisites:** Phase 2 eval runner, Phase 3 compare.html, ground truth labels
> **Date:** 2026-03-10

---

## Area: Search CLI (VAL-SRCH-xxx)

### VAL-SRCH-001 — search.py accepts required CLI flags
**Behavioral description:** Running `python search.py --config <path> --search-space <path> --labels <path> --iterations 10` parses all four flags without error. The `--config` flag points to a base YAML config file. The `--search-space` flag points to a YAML/JSON file defining parameter sweep ranges and bounds. The `--labels` flag points to a ground truth labels JSON file. The `--iterations` flag accepts a positive integer. Missing any required flag produces a clear argparse error naming the missing flag.
**Evidence:** Terminal output of `python search.py --help` showing all four flags with descriptions; terminal output of a successful launch with all flags provided; terminal output of launch with `--labels` omitted showing argparse error.

### VAL-SRCH-002 — Search runs the specified number of iterations
**Behavioral description:** Running `python search.py --config base.yaml --search-space space.yaml --labels gt.json --iterations 5` executes exactly 5 evaluation iterations. Each iteration produces a scored candidate. The final summary line reports "5/5 iterations completed". Setting `--iterations 1` runs exactly 1 iteration.
**Evidence:** Terminal output showing iteration progress (e.g., `[1/5] score=0.72 ...` through `[5/5] score=0.81 ...`) and final summary line confirming 5 completed.

### VAL-SRCH-003 — Produces ranked output file with candidates
**Behavioral description:** After all iterations complete, search.py writes a JSON output file (default: `results/search_results.json` or path specified by `--output`). The file contains a `candidates` array sorted by fitness score descending. Each candidate entry includes: `rank` (1-indexed), `score` (float), `config` (the full parameter dict used), and `iteration` (which iteration produced it). The top-ranked candidate has the highest score.
**Evidence:** Terminal output showing output file path; `cat` or inspection of the output JSON showing candidates array sorted by descending score; verification that `candidates[0].rank == 1` and `candidates[0].score >= candidates[1].score`.

### VAL-SRCH-004 — Handles Ctrl+C gracefully
**Behavioral description:** When the user sends SIGINT (Ctrl+C) during a running search (e.g., mid-iteration 3 of 10), the process catches the signal, saves all completed iterations to the output file, prints a message like "Interrupted — saving 3 completed iterations", and exits with code 0 (or a clean exit code). The output file contains valid JSON with the 3 completed candidates ranked. No partial/corrupt JSON is written. No completed iteration results are lost.
**Evidence:** Terminal output showing interrupt message and saved iteration count; inspection of output JSON confirming valid structure with exactly the completed iterations; `echo $?` showing clean exit code.

### VAL-SRCH-005 — Progress display shows iteration count, best score, and improvement rate
**Behavioral description:** During execution, each completed iteration prints a progress line containing: (1) iteration counter `[N/total]`, (2) current iteration's score, (3) current best score seen so far (marked with `★` or `best` label when a new best is found), and (4) improvement rate (percentage or absolute delta from baseline). The display updates in real-time (not buffered to end). After the final iteration, a summary block shows: total iterations, best score, best iteration number, and overall improvement from baseline.
**Evidence:** Terminal output captured during a 10-iteration run showing progress lines with all four fields; final summary block visible after completion.

### VAL-SRCH-006 — Optional --seed flag for reproducible runs
**Behavioral description:** Running `python search.py --config base.yaml --search-space space.yaml --labels gt.json --iterations 5 --seed 42` produces deterministic results. Running the same command twice with `--seed 42` produces identical candidate configs and scores in the same order. Running without `--seed` (or with a different seed) produces different candidates.
**Evidence:** Terminal output of two runs with `--seed 42` showing identical iteration scores; diff of the two output JSON files showing zero differences; terminal output of a run with `--seed 99` showing different scores.

### VAL-SRCH-007 — Invalid flag values produce clear errors
**Behavioral description:** Running with `--iterations 0` or `--iterations -1` produces an error message stating iterations must be a positive integer. Running with `--config nonexistent.yaml` produces an error stating the config file was not found. Running with `--search-space` pointing to a malformed YAML produces a parse error with file path and line number. None of these cases produce a raw Python traceback — errors are user-facing messages.
**Evidence:** Terminal output for each invalid-input case showing descriptive error message without raw traceback.

---

## Area: Perturbation (VAL-PERT-xxx)

### VAL-PERT-001 — Numeric params perturbed within sweep_range bounds
**Behavioral description:** Given a search-space config that defines `atr_multiplier: {base: 1.5, min: 1.0, max: 3.0, step: 0.25}`, every perturbed value of `atr_multiplier` across all iterations falls within `[1.0, 3.0]` inclusive. No perturbed value is below `min` or above `max`. The perturbation magnitude per iteration is within ±10-20% of the base value (i.e., between `base × 0.80` and `base × 1.20`), further clamped to `[min, max]`.
**Evidence:** Provenance JSON inspection showing all `atr_multiplier` values across iterations; programmatic assertion that `min <= value <= max` for every value; histogram or listing confirming perturbation magnitudes fall within ±20% of base (pre-clamp).

### VAL-PERT-002 — Categorical params toggled between defined options
**Behavioral description:** Given a search-space config that defines `quality_gate: {type: categorical, options: ["strict", "relaxed", "off"]}`, every perturbed value of `quality_gate` is one of the three defined options. No iteration produces a value outside the options list. Over a sufficient number of iterations (≥10), at least 2 of the 3 options appear in the candidate set.
**Evidence:** Provenance JSON inspection showing all `quality_gate` values; assertion that each is in `["strict", "relaxed", "off"]`; count of distinct values observed confirming ≥2 options used.

### VAL-PERT-003 — Perturbations are reproducible with seed
**Behavioral description:** Running the perturbation engine with `seed=42` for 10 iterations produces an identical sequence of perturbed configs on every invocation. The Nth iteration always produces the same parameter values when the same seed is used. This holds across process restarts (the RNG state is initialized from seed alone, not from system time or PID).
**Evidence:** Two independent runs with `seed=42` producing identical provenance JSON files (byte-for-byte or semantically identical); diff showing zero differences in config values across all iterations.

### VAL-PERT-004 — Each iteration produces a valid config
**Behavioral description:** Every perturbed config produced by the perturbation engine is a valid input to `eval.py` (or the evaluation runner). Specifically: (1) all required config keys are present, (2) no numeric value is NaN or Infinity, (3) no value violates its type constraint (e.g., int param stays int, float stays float), (4) nested config structure is preserved (e.g., `displacement.ltf.atr_multiplier` remains nested under `displacement.ltf`). Passing any perturbed config to `eval.py` does not raise a config validation error.
**Evidence:** Programmatic test: generate 20 perturbed configs, feed each to the config validator or `eval.py --dry-run`, confirm zero validation errors; provenance JSON showing all configs have correct structure.

### VAL-PERT-005 — Multi-param joint perturbation produces diverse combinations
**Behavioral description:** When the search space defines multiple perturbable params (e.g., `atr_multiplier`, `body_ratio`, `close_gate`), each iteration perturbs all eligible params independently. Over 10+ iterations, the combination of param values varies — no two iterations produce the exact same config (probability of collision is negligible with continuous params). The parameter space is explored, not just one dimension at a time.
**Evidence:** Provenance JSON showing at least 10 iterations; programmatic check that no two iteration configs are identical; scatter plot or listing showing variation across multiple params simultaneously.

### VAL-PERT-006 — Step size respected for discrete numeric params
**Behavioral description:** When a search-space param defines `step: 0.25` (e.g., `atr_multiplier: {base: 1.5, min: 1.0, max: 3.0, step: 0.25}`), all perturbed values are multiples of 0.25 within the range (e.g., 1.0, 1.25, 1.5, ..., 3.0). No intermediate values like 1.33 or 2.17 appear. When `step` is absent or null, continuous perturbation is allowed.
**Evidence:** Provenance JSON showing all values of the stepped param; assertion that `(value - min) % step == 0` for every value (within float tolerance).

### VAL-PERT-007 — Boolean params toggled correctly
**Behavioral description:** When a search-space param defines `type: boolean` (e.g., `use_cluster_check: {type: boolean, base: true}`), perturbed values are strictly `true` or `false`. Over sufficient iterations, both values appear. No other values (0, 1, "true", null) are produced.
**Evidence:** Provenance JSON showing `use_cluster_check` values; assertion that each is a boolean; confirmation both true and false appear.

---

## Area: Fitness (VAL-FIT-xxx)

### VAL-FIT-001 — Fitness score equals precision + recall against ground truth
**Behavioral description:** For each candidate config, the fitness score is computed as `precision + recall` where precision = (true positives) / (total detections) and recall = (true positives) / (total ground truth labels). Detections are matched against ground truth labels using the same matching logic as the evaluation runner (timestamp + primitive type match within tolerance). The computed score is a float in `[0.0, 2.0]`. A candidate with perfect precision and perfect recall scores exactly 2.0.
**Evidence:** Provenance JSON for one iteration showing `score`, `precision`, `recall`, `true_positives`, `total_detections`, `total_labels`; manual verification that `precision = tp / total_detections`, `recall = tp / total_labels`, `score = precision + recall`.

### VAL-FIT-002 — Walk-forward stability check on top N candidates
**Behavioral description:** After all iterations complete, the top N candidates (N configurable, default 5) undergo a walk-forward stability check. Each candidate's config is evaluated on a held-out time window (or rolling train/test split). Candidates whose walk-forward score drops by more than a configurable threshold (e.g., >20% degradation from in-sample score) are flagged as "unstable". The stability flag is recorded in the output alongside the candidate's score.
**Evidence:** Output JSON showing top N candidates with fields `in_sample_score`, `walk_forward_score`, `stability` (stable/unstable), and `degradation_pct`; verification that candidates with >20% degradation are marked unstable.

### VAL-FIT-003 — Candidates improving on baseline are kept
**Behavioral description:** The baseline score is computed by evaluating the base config (from `--config`) against the ground truth labels before the search begins. Any candidate whose fitness score exceeds the baseline score is marked `kept: true` in the results. The baseline score is recorded in the output metadata. At least the top-ranked candidate (if it improves on baseline) is marked as kept.
**Evidence:** Output JSON showing `baseline_score` in metadata; candidates with `score > baseline_score` have `kept: true`; candidates with `score <= baseline_score` have `kept: false`.

### VAL-FIT-004 — Candidates not improving are discarded with score recorded
**Behavioral description:** Candidates whose fitness score is equal to or below the baseline score are marked `kept: false` but their full record (config, score, iteration number) is preserved in the output for audit purposes. They are not deleted or omitted. In the ranked output, they appear after all kept candidates, still sorted by score descending within the discarded group.
**Evidence:** Output JSON showing discarded candidates with `kept: false`, valid `score`, and full `config`; verification that no candidates are silently dropped — total candidates in output equals `--iterations` count.

### VAL-FIT-005 — Fitness handles edge case of zero detections
**Behavioral description:** If a perturbed config produces zero detections (e.g., thresholds too restrictive), the fitness score is 0.0 (precision is defined as 0 when there are no detections, recall is 0). The iteration does not crash or produce NaN. The zero-detection candidate is recorded with `score: 0.0`, `precision: 0.0`, `recall: 0.0`, `total_detections: 0`.
**Evidence:** Provenance JSON showing a zero-detection iteration with score 0.0 and no errors; terminal output showing the iteration completed normally.

### VAL-FIT-006 — Fitness handles edge case of zero ground truth labels
**Behavioral description:** If the ground truth labels file contains zero labels (empty array), the search exits immediately with a clear error message: "No ground truth labels found — cannot compute fitness". The search does not run any iterations or produce misleading scores.
**Evidence:** Terminal output showing the error message when launched with an empty labels file; no output JSON created; clean exit.

---

## Area: Provenance (VAL-PROV-xxx)

### VAL-PROV-001 — Every iteration recorded with config, score, and delta
**Behavioral description:** The provenance output contains one record per iteration. Each record includes: `iteration` (1-indexed int), `config` (complete parameter dict used for that iteration), `score` (float), `precision` (float), `recall` (float), `delta_from_baseline` (float, can be negative), `kept` (boolean), and `timestamp` (ISO 8601 when the iteration completed). No iteration is missing from the provenance — the total record count equals the number of completed iterations.
**Evidence:** Provenance JSON showing all iteration records; programmatic count confirming `len(records) == iterations`; spot-check of one record showing all required fields present with correct types.

### VAL-PROV-002 — Final output is a ranked list with full audit trail
**Behavioral description:** The output JSON contains two top-level sections: `metadata` (run parameters, baseline score, timestamps, seed) and `candidates` (array sorted by score descending). Each candidate in the array includes all provenance fields from VAL-PROV-001 plus a `rank` field (1-indexed, 1 = best). The `metadata` section includes: `base_config_path`, `search_space_path`, `labels_path`, `iterations_requested`, `iterations_completed`, `seed`, `baseline_score`, `best_score`, `start_time`, `end_time`, `duration_seconds`.
**Evidence:** Output JSON inspection showing `metadata` and `candidates` sections; verification that `candidates[0].rank == 1` and scores are in descending order; metadata fields present and populated.

### VAL-PROV-003 — Output format is machine-readable JSON
**Behavioral description:** The output file is valid JSON (parseable by `json.loads()` without error). The file uses UTF-8 encoding. The JSON is pretty-printed with 2-space indentation for readability. Float values are serialized with sufficient precision (at least 4 decimal places for scores). No Python-specific serialization artifacts (no `NaN`, `Infinity`, `True`/`False` capitalization — uses JSON-standard `null`, `true`, `false`).
**Evidence:** `python -c "import json; json.load(open('results/search_results.json'))"` succeeds without error; inspection confirming 2-space indentation, JSON-standard booleans/nulls, and float precision.

### VAL-PROV-004 — Human-readable summary generated alongside
**Behavioral description:** In addition to the JSON output, search.py generates a human-readable summary file (e.g., `results/search_summary.txt` or `.md`). The summary includes: (1) run parameters (config, search space, iterations, seed), (2) baseline score, (3) top 5 candidates with rank, score, delta, and key param changes from baseline, (4) overall improvement percentage, (5) stability flags if walk-forward was run. The summary is formatted for terminal display or Markdown rendering — not raw JSON.
**Evidence:** Contents of the summary file showing all five sections; verification that it is human-readable (not JSON); key metrics match the JSON output.

### VAL-PROV-005 — Provenance includes search space definition
**Behavioral description:** The output JSON `metadata` section includes a `search_space` field containing the full search space definition used for the run (param names, ranges, bounds, types). This allows any output file to be fully self-describing — a reviewer can understand what was searched without needing the original search-space file.
**Evidence:** Output JSON `metadata.search_space` field containing param definitions; verification that it matches the input search-space file content.

### VAL-PROV-006 — Provenance records param-level deltas from base config
**Behavioral description:** Each candidate record includes a `param_deltas` field showing, for each perturbed param, the base value, the perturbed value, and the absolute/percentage change. For example: `"atr_multiplier": {"base": 1.5, "value": 1.75, "delta": 0.25, "pct_change": 16.7}`. This allows quick identification of which param changes drove score improvements.
**Evidence:** Provenance JSON showing `param_deltas` for a candidate; verification that `base` matches the base config, `value` matches the candidate's config, and `delta` and `pct_change` are computed correctly.

---

## Area: Winner Review (VAL-WIN-xxx)

### VAL-WIN-001 — Top candidate config exportable as comparison fixture
**Behavioral description:** The search output includes a command or script to export the top-ranked candidate's config as a comparison fixture loadable by `compare.html`. Running the export (e.g., `python search.py --export-winner results/search_results.json`) produces a Schema 4A-compatible JSON file in the `site/eval/` directory containing evaluation results for both the baseline config and the winner config. The exported file follows the same structure as existing comparison fixtures.
**Evidence:** Terminal output of the export command; inspection of the exported JSON in `site/eval/` confirming Schema 4A structure with two config entries (baseline + winner); `compare.html` loading the file without errors.

### VAL-WIN-002 — compare.html loads winner vs baseline for visual review
**Behavioral description:** Opening `compare.html` with the exported winner fixture loaded displays both configs in the comparison view. The Chart tab shows candlestick data with detection markers for both baseline and winner configs in distinct colors. The Stats tab shows side-by-side metrics. Config toggle controls work for both configs. The winner config is labeled with its search rank and score (e.g., "winner (rank 1, score 1.85)"). No console errors during load or interaction.
**Evidence:** Screenshot of Chart tab showing baseline and winner markers in distinct colors; screenshot of Stats tab showing side-by-side metrics; screenshot of config labels showing winner metadata; browser console showing zero errors.

### VAL-WIN-003 — Stats dashboard shows improvement metrics
**Behavioral description:** When viewing the winner fixture in `compare.html`, the Stats tab displays improvement metrics: (1) baseline score vs winner score, (2) absolute improvement (delta), (3) percentage improvement, (4) per-primitive detection count changes (e.g., "displacement: +12 detections, precision +5%"), (5) stability flag from walk-forward (if available). These metrics are rendered in the existing stats dashboard layout with appropriate color coding (green for improvements, red for regressions).
**Evidence:** Screenshot of Stats tab showing improvement metrics with values; verification that displayed delta matches `winner_score - baseline_score`; color coding visible (green for positive deltas).

### VAL-WIN-004 — Multiple winners exportable for comparison
**Behavioral description:** The export command supports exporting the top N candidates (e.g., `--top 3`) as a multi-config comparison fixture. The exported Schema 4A JSON contains N+1 configs (baseline + N winners). `compare.html` can toggle between all configs independently. Each winner is labeled with its rank and score.
**Evidence:** Terminal output of export with `--top 3`; inspection of exported JSON showing 4 config entries; screenshot of `compare.html` showing toggle controls for baseline + 3 winners.

### VAL-WIN-005 — Winner config exportable as standalone YAML
**Behavioral description:** The export command supports `--format yaml` to produce a standalone YAML config file containing the winner's full parameter set. This YAML file is directly usable as a `--config` argument to `eval.py` or `search.py` (for subsequent search refinement). The YAML includes a comment header with provenance: source search run ID, rank, score, and date.
**Evidence:** Exported YAML file contents showing full config with comment header; successful run of `eval.py --config winner.yaml` without config errors; comment header containing run ID, rank, score, and date.

### VAL-WIN-006 — Winner review includes detection-level diff
**Behavioral description:** The exported comparison fixture includes per-detection divergence data (Schema 4C format) showing which detections are unique to the winner, unique to the baseline, and shared. The divergence navigator in `compare.html` allows clicking through detection differences between baseline and winner, scrolling the chart to each divergence point.
**Evidence:** Exported JSON containing `divergence_index` array; screenshot of divergence navigator in `compare.html` listing winner-vs-baseline differences; screenshot of chart scrolled to a divergence point showing the detection present in winner but absent in baseline.
