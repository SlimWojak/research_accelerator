# Phase 2 → Phase 3 Output Schemas (Interface Contract)

> **Purpose:** Canonical JSON output schemas for Phase 2 evaluation engine.
> Workers implementing `evaluation/` and `output/` modules MUST serialize to these exact structures.
> Phase 3 comparison interface will consume these schemas directly.
>
> **Source:** `results/PHASE2_PHASE3_INTERFACE_ALIGNMENT.md` — Schemas 4A–4E
>
> **schema_version:** Every top-level output file MUST include a `schema_version` field (e.g., `"1.0"`) so Phase 3 can detect breaking changes. Bump the minor version for additive changes, major for breaking.

---

## Serialization Rules

All JSON output MUST follow these numpy/pandas serialization conventions:

| Python / NumPy Type | JSON Serialization |
|---|---|
| `numpy.int64` | `int` (plain JSON integer) |
| `numpy.float64` | `float` (plain JSON number) |
| `numpy.nan` / `float('nan')` | `null` |
| `pandas.Timestamp` | ISO 8601 string (`"2024-01-08T09:35:00"`) |
| `pandas.NaT` | `null` |
| `numpy.bool_` | `bool` (JSON `true`/`false`) |

Workers MUST use a custom JSON encoder or explicit conversion to ensure no numpy/pandas types leak into output.

---

## Schema 4A: Evaluation Run Output (Top-Level Envelope)

The top-level structure wrapping all evaluation results for a single run.

```json
{
  "schema_version": "1.0",
  "run_id": "eval_2026-03-09_001",
  "dataset": {
    "name": "EURUSD_2024_Q1",
    "bars_1m": 370000,
    "range": ["2024-01-01", "2024-03-31"]
  },
  "configs": ["current_locked", "candidate_relaxed"],
  "timestamp": "2026-03-09T14:30:00",

  "per_config": {
    "current_locked": { "$ref": "Schema 4B" },
    "candidate_relaxed": { "$ref": "Schema 4B" }
  },

  "pairwise": {
    "current_locked__vs__candidate_relaxed": { "$ref": "Schema 4C" }
  },

  "grid_sweep": { "$ref": "Schema 4D" },
  "walk_forward": { "$ref": "Schema 4E" }
}
```

**Fields:**
- `run_id` — Unique identifier for this evaluation run.
- `dataset` — Dataset metadata (name, bar count, date range).
- `configs` — List of config names evaluated.
- `per_config` — Dict keyed by config name → Schema 4B.
- `pairwise` — Dict keyed by `configA__vs__configB` → Schema 4C.
- `grid_sweep` — Schema 4D (nullable if no sweep was run).
- `walk_forward` — Schema 4E (nullable if no walk-forward was run).

---

## Schema 4B: Per-Config Result

Per-config detection results, aggregate statistics, and cascade funnel.

```json
{
  "config_name": "current_locked",
  "params": {
    "displacement": { "atr_multiplier": 1.5, "body_ratio": 0.60 }
  },

  "per_primitive": {
    "displacement": {
      "per_tf": {
        "5m": {
          "detection_count": 460,
          "detections_per_day": 7.4,
          "detections_per_day_std": 2.1,
          "by_session": {
            "asia":  { "count": 78, "pct": 16.9 },
            "lokz":  { "count": 110, "pct": 23.9 },
            "nyokz": { "count": 155, "pct": 33.7 },
            "other": { "count": 117, "pct": 25.5 }
          },
          "by_direction": {
            "bullish": { "count": 220, "pct": 47.8 },
            "bearish": { "count": 240, "pct": 52.2 }
          },
          "detections": [
            {
              "id": "disp_5m_2024-01-08T09:35:00_bear",
              "time": "2024-01-08T09:35:00",
              "direction": "bearish",
              "type": "atr_single",
              "price": 1.0945,
              "properties": {
                "atr_ratio": 1.82,
                "body_pct": 0.71,
                "quality_grade": "STRONG"
              },
              "tags": {
                "session": "nyokz",
                "kill_zone": "NYOKZ",
                "forex_day": "2024-01-08"
              },
              "upstream_refs": []
            }
          ]
        }
      }
    }
  },

  "cascade_funnel": {
    "timeframe": "5m",
    "levels": [
      { "name": "swing_points", "count": 267, "type": "leaf" },
      { "name": "displacement", "count": 460, "type": "leaf" },
      { "name": "fvg", "count": 345, "type": "leaf" },
      {
        "name": "mss", "count": 44, "type": "composite",
        "conversion_rates": {
          "from_displacement": 0.096,
          "with_fvg_tag": 0.80
        },
        "breakdown": { "reversal": 20, "continuation": 24 }
      },
      {
        "name": "order_block", "count": 37, "type": "composite",
        "conversion_rates": { "from_mss": 0.84 }
      },
      {
        "name": "liquidity_sweep", "count": 14, "type": "terminal",
        "by_source": {
          "session_hl": 5, "pdh_pdl": 3,
          "promoted_swing": 2, "htf_eql": 1, "ltf_box": 3
        }
      }
    ],
    "convergence": {
      "mss_in_kill_zone": 28,
      "ob_in_kill_zone": 22
    }
  }
}
```

**Key notes:**
- `by_session` is a nested dict `{session_name: {count: int, pct: float}}` — one entry per session (`asia`, `lokz`, `nyokz`, `other`). Maps directly to grouped bar charts.
- `detections` is the full detection array for chart overlay rendering (multi-config markers).
- `cascade_funnel.levels[]` provides both counts (for funnel bars) AND conversion rates (for labels). `type` is one of: `"leaf"`, `"composite"`, `"terminal"`.

---

## Schema 4C: Pairwise Comparison Result

Pairwise statistical comparison between two configs, including per-detection divergence index.

```json
{
  "config_a": "current_locked",
  "config_b": "candidate_relaxed",

  "per_primitive": {
    "displacement": {
      "per_tf": {
        "5m": {
          "count_a": 460,
          "count_b": 612,
          "agreement_rate": 0.68,
          "only_in_a": 142,
          "only_in_b": 294,
          "by_session_agreement": {
            "asia":  { "agreement": 0.55 },
            "lokz":  { "agreement": 0.72 },
            "nyokz": { "agreement": 0.74 },
            "other": { "agreement": 0.61 }
          }
        }
      }
    }
  },

  "divergence_index": [
    {
      "time": "2024-01-08T09:35:00",
      "primitive": "displacement",
      "tf": "5m",
      "in_a": true,
      "in_b": true,
      "detection_id_a": "disp_5m_2024-01-08T09:35:00_bear",
      "detection_id_b": "disp_5m_2024-01-08T09:35:00_bear"
    },
    {
      "time": "2024-01-08T10:15:00",
      "primitive": "displacement",
      "tf": "5m",
      "in_a": false,
      "in_b": true,
      "detection_id_a": null,
      "detection_id_b": "disp_5m_2024-01-08T10:15:00_bull"
    }
  ]
}
```

**Key notes:**
- `divergence_index` is the per-detection diff list that Phase 3 uses for "click to jump to divergence" navigation. Each entry shows which config(s) detected at a given time.
- `detection_id_a` / `detection_id_b` are `null` when the detection is absent in that config.

---

## Schema 4D: Grid Sweep Result

2D parameter sweep heatmap data for parameter stability analysis.

```json
{
  "sweep_id": "sweep_displacement_atr_body_20260309",
  "primitive": "displacement",
  "variant": "a8ra_v1",
  "dataset": "EURUSD_2024_Q1",
  "metric": "cascade_to_mss_rate",

  "axes": {
    "x": {
      "param": "atr_multiplier",
      "values": [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 3.0]
    },
    "y": {
      "param": "body_ratio",
      "values": [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]
    }
  },

  "grid": [
    [0.12, 0.15, 0.18, 0.22, 0.31, 0.45, 0.52, 0.58, 0.61, 0.60, 0.55, 0.48, 0.35],
    [0.14, 0.17, 0.21, 0.28, 0.38, 0.51, 0.59, 0.64, 0.67, 0.65, 0.60, 0.52, 0.40]
  ],

  "current_lock": { "x": 1.5, "y": 0.60, "metric_value": 0.74 },

  "plateau": {
    "detected": true,
    "region": { "x_range": [1.0, 2.0], "y_range": [0.50, 0.70] },
    "metric_variance_within": 0.03,
    "metric_mean_within": 0.74,
    "lock_position": "CENTER"
  },

  "cliff_edges": [
    { "axis": "atr_multiplier", "direction": "below", "threshold": 0.8, "metric_drop_to": 0.31 },
    { "axis": "body_ratio", "direction": "above", "threshold": 0.80, "metric_drop_to": 0.38 }
  ]
}
```

### Grid Encoding Convention

**Row-major 2D array:** `grid[i][j]` = metric value at `axes.x.values[i]`, `axes.y.values[j]`.

- `grid` has `len(axes.x.values)` rows, each row has `len(axes.y.values)` columns.
- This is the standard encoding for heatmap libraries (D3, Plotly, etc.).
- All values are plain JSON numbers (no NaN — use `null` for missing/failed evaluations).

### 1D Grid Sweep (Degenerate Y-Axis)

When sweeping a single parameter, the y-axis is degenerate:

```json
{
  "axes": {
    "x": { "param": "atr_multiplier", "values": [0.5, 0.6, ..., 3.0] },
    "y": { "param": "_single", "values": [0] }
  },
  "grid": [[0.12, 0.18, 0.31, 0.45, 0.58, 0.61, 0.55, 0.35]]
}
```

- `y.param` is `"_single"` and `y.values` is `[0]` (one dummy value).
- `grid` has exactly 1 row with `len(axes.x.values)` columns.
- Phase 3 renders this as a line chart instead of a heatmap.

---

## Schema 4E: Walk-Forward Result

Rolling train/test validation results with regime cross-reference.

```json
{
  "config": "current_locked",
  "primitive": "displacement",
  "metric": "cascade_to_mss_rate",
  "window_config": { "train_months": 3, "test_months": 1, "step_months": 1 },

  "windows": [
    {
      "window_index": 0,
      "train_period": { "start": "2024-01-01", "end": "2024-03-31" },
      "test_period": { "start": "2024-04-01", "end": "2024-04-30" },
      "train_metric": 0.74,
      "test_metric": 0.71,
      "delta": -0.03,
      "delta_pct": -4.1,
      "regime_tags": ["trending", "normal_vol"],
      "passed": true
    },
    {
      "window_index": 3,
      "train_period": { "start": "2024-04-01", "end": "2024-06-30" },
      "test_period": { "start": "2024-07-01", "end": "2024-07-31" },
      "train_metric": 0.71,
      "test_metric": 0.42,
      "delta": -0.29,
      "delta_pct": -40.8,
      "regime_tags": ["ranging", "low_vol", "summer"],
      "passed": false
    }
  ],

  "summary": {
    "windows_total": 9,
    "windows_passed": 8,
    "windows_failed": 1,
    "mean_test_metric": 0.66,
    "std_test_metric": 0.09,
    "mean_delta": -0.05,
    "worst_window": {
      "window_index": 3,
      "test_period": "Jul 2024",
      "test_metric": 0.42,
      "regime": "low_vol_summer"
    },
    "degradation_flag": true,
    "pass_threshold_pct": 15.0,
    "verdict": "CONDITIONALLY_STABLE"
  }
}
```

**Key notes:**
- `windows[]` is ordered by `window_index`. Each window has regime tags embedded directly (not a separate lookup).
- `verdict` is one of: `"STABLE"`, `"CONDITIONALLY_STABLE"`, `"UNSTABLE"`.
- `passed` per window is `true` when `abs(delta_pct) <= pass_threshold_pct`.
- `degradation_flag` is `true` when any window fails.

---

## Quick Reference: Schema Nesting

```
Schema 4A (top-level envelope)
├── per_config.{name}     → Schema 4B (per-config result)
│   ├── per_primitive.{p}.per_tf.{tf}.detections[]   (full detection arrays)
│   ├── per_primitive.{p}.per_tf.{tf}.by_session      (session distribution)
│   └── cascade_funnel.levels[]                        (multi-level funnel)
├── pairwise.{a__vs__b}  → Schema 4C (pairwise comparison)
│   └── divergence_index[]                             (per-detection diff)
├── grid_sweep            → Schema 4D (parameter stability heatmap)
│   └── grid[][]                                       (row-major 2D metric values)
└── walk_forward          → Schema 4E (walk-forward validation)
    ├── windows[]                                      (per-window results)
    └── summary                                        (aggregate verdict)
```
