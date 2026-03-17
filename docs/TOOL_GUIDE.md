# Tool Guide — Quick Operations Reference

Not architecture — operations. How to run each tool.

---

## How to Run

### Static Server (calibration pages)
```bash
cd site && python3 -m http.server 8100
# Open http://localhost:8100
```

### Full Server (validation + strategy + comparison)
```bash
python3 site/serve.py
# Open http://localhost:8200/validate.html
# Open http://localhost:8200/strategy.html
# Open http://localhost:8200/compare.html
```

### Detection Generation
```bash
# Standard (slim output for validate.html)
python3 site/detect.py --start 2025-09-01 --end 2026-02-28 --config configs/locked_baseline.yaml --output site/data/

# Enriched (full output for strategy.html)
python3 site/detect.py --full --start 2025-09-01 --end 2026-02-28 --config configs/locked_baseline.yaml --output site/data/
```

### AutoResearch Evaluate
```bash
python3 tools/autoresearch/evaluate.py

# With parameter overrides
python3 tools/autoresearch/evaluate.py --param-overrides h1_counter_persistence_bars=4 momentum_stall_window_daily_bars=2
```

### AutoResearch Sweep
```bash
# Dry run (show search space)
python3 tools/autoresearch/sweep.py --dry-run

# Full sweep (5,120 combinations — wait until 10+ trades)
python3 tools/autoresearch/sweep.py
```

### Tests
```bash
# All tests
python3 -m pytest tests/ -v

# Core primitives only
python3 -m pytest tests/test_cascade.py tests/test_fvg.py tests/test_mss.py tests/test_swing_points.py tests/test_displacement.py -q

# Regression suite
python3 -m pytest tests/test_regression.py -v
```

---

## How to Add a Week

1. Run detect.py with the new week's date range:
```bash
python3 site/detect.py --full --start 2026-03-01 --end 2026-03-07 --output site/data/
```
2. Data auto-appears in all tools (weeks.json updated automatically).

---

## How to Add a Trade Annotation

1. Edit `research/ground_truth/annotated_trades.yaml`
2. Follow the schema:
```yaml
- id: trade_005
  date: "YYYY-MM-DD"
  pair: EURUSD
  execution_time: "HH:MM"
  kill_zone: LOKZ | NYOKZ | N/A
  direction: LONG | SHORT
  expected_state:
    htf_phase: EXPANSION | RETRACE | RANGE | INDEPENDENT
    direction_permission: WITH_EXPANSION | COUNTER_ALLOWED | BOTH | INDEPENDENT
    daily_direction: BULLISH | BEARISH | NEUTRAL
    authority_tf: Daily | 4H | 1H | N/A
  execution_chain:
    steps:
      - primitive: sweep | mss | displacement | fvg | ob | ote
        tf: 15m | 5m
        time: "HH:MM"
    notes: "any special conditions"
  htf_context:
    description: "plain text HTF narrative"
  strategy_type: state_gated | asia_range_scalp
```
3. Run: `python3 tools/autoresearch/evaluate.py`
4. Review report in `reports/autoresearch/`

---

## How to Run Olya Calibration Session

1. Start server: `python3 site/serve.py`
2. Open calibration tool: `http://localhost:8100`
3. Select TF and navigate to relevant week
4. Review detections with Olya on each primitive chart
5. Adjust thresholds in `configs/locked_baseline.yaml`
6. Regenerate: `python3 site/detect.py --full --start ... --end ... --output site/data/`
7. Verify on chart
8. Lock when confirmed

---

## How to Deploy to GitHub Pages

```bash
cd ~/ra-tools
# Copy updated files from research_accelerator/site/
cp -r /Users/echopeso/research_accelerator/site/* .
git add . && git commit -m "Update from RA" && git push origin main
```
Note: persistence uses localStorage on static hosting (no serve.py).
