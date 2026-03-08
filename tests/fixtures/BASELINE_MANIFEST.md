# Regression Baseline Manifest

```yaml
captured: 2026-03-08
source: pipeline/preprocess_data_v2.py (current pipeline, unmodified)
dataset: data/eurusd_1m_2024-01-07_to_2024-01-12.csv (7,177 bars)
files: 32 JSON files (16MB total)
```

## Exact Detection Counts (from pipeline stdout)

These are the numbers the refactored engine MUST reproduce exactly.

### Per-Timeframe Primitive Counts

| Primitive | 1m | 5m | 15m |
|-----------|-----|-----|------|
| FVG | 2,017 (1026 bull, 991 bear) | 345 (179 bull, 166 bear) | 118 (58 bull, 60 bear) |
| Swings | 833 (420 high, 413 low) | 267 (135 high, 132 low) | 124 (62 high, 62 low) |
| Displacement | 4,170 (608 FVG-creating) | 819 (171 FVG-creating) | 258 (76 FVG-creating) |
| MSS | 179 (88 rev, 91 cont, 129 fvg) | 44 (20 rev, 24 cont, 35 fvg) | 20 (10 rev, 10 cont, 17 fvg) |
| Order Block | 138 | 37 | 17 |
| NY Win A / B | 104 / 95 | 30 / 23 | 11 / 13 |

### Liquidity Sweep Counts

| TF | Base (1-bar) | Qualified | Delayed | Continuation |
|----|-------------|-----------|---------|--------------|
| 1m | 7 | 5 | 22 | 18 |
| 5m | 14 | 11 | 15 | 10 |
| 15m | 11 | 10 | 15 | 14 |

### Sweep Source Distribution (5m)

ASIA_H_L:3, LONDON_H_L:2, LTF_BOX:6, PDH_PDL:2, PROMOTED_SWING:1

### HTF Liquidity Pools

| TF | Bars | Swings | Pools | Untouched | Taken |
|----|------|--------|-------|-----------|-------|
| H1 | 120 | 34 | 3 | 2 | 1 |
| H4 | 31 | 9 | 1 | 1 | 0 |
| D1 | 5 | 0 | 0 | 0 | 0 |
| W1 | 2 | 0 | 0 | 0 | 0 |

### Session Liquidity Boxes (15 total)

| Day | Asia | PreLondon | PreNY |
|-----|------|-----------|-------|
| Jan 8 | CONSOL 22.4p | TREND_UP 14.7p | TREND_UP 16.4p |
| Jan 9 | CONSOL 17.0p | TREND_DN 8.2p | TREND_DN 19.4p |
| Jan 10 | CONSOL 10.3p | TREND_DN 10.4p | CONSOL 13.7p |
| Jan 11 | CONSOL 11.7p | TREND_UP 14.0p | TREND_UP 23.8p |
| Jan 12 | CONSOL 12.7p | CONSOL 7.2p | TREND_DN 17.5p |

### Asia Range (5 sessions)

| Day | Pips |
|-----|------|
| Jan 8 | 22.4 |
| Jan 9 | 17.0 |
| Jan 10 | 10.3 |
| Jan 11 | 11.7 |
| Jan 12 | 12.7 |

### Reference Levels

PWH: 1.10001, PWL: 1.09104

### Bar Counts

| TF | Total | Per Day (approx) |
|----|-------|------------------|
| 1m | 7,177 | ~1,435 |
| 5m | 1,440 | 288 |
| 15m | 480 | 96 |

### EQL/EQH (DEFERRED — captured but not regression-critical)

| TF | EQH Pools | EQL Pools |
|----|-----------|-----------|
| 1m | 11 | 10 |
| 5m | 9 | 9 |
| 15m | 7 | 9 |
| Session-gated Tier 2 | 55 EQH | 53 EQL |

## IMPORTANT NOTES

1. Displacement count in pipeline output (4,170 on 1m) differs from v0.5
   calibration_data (2,277 on 1m). The pipeline emits ALL candidates including
   those below ATR threshold — the v0.5 number is after filtering. The regression
   test should match the JSON output structure, which includes threshold-filtered
   and unfiltered views. Examine the JSON to determine exact structure.

2. Swing count (267 on 5m) differs from PROJECT_STATE.md (163 on 5m).
   PROJECT_STATE.md was written at an earlier pipeline version. The current
   pipeline output is the ground truth.

3. OB count (37 on 5m) differs from PROJECT_STATE.md (106 on 5m).
   This is because the v0.5 OB now requires MSS (not just displacement).
   Current pipeline output is ground truth.
