# Research Directory Index

## State Detection Logic

| File | Description |
|------|-------------|
| `STATE_DETECTION_LOGIC_v2.yaml` | Canonical v2.1 spec — event-cycle model, 3 HTF phases, direction permission, classifier thresholds. 937 lines. |
| `HTF_FORENSIC_ANALYSIS_BRIEF.md` | Methodology brief for forensic analysis of 4 trades against v2 model. |

## Ground Truth

| File | Description |
|------|-------------|
| `ground_truth/annotated_trades.yaml` | Olya's trade annotations. 4 trades pre-populated. Schema in file header. |

## Reports

| File | Description |
|------|-------------|
| `../reports/htf_forensic_analysis_2026-03-15.yaml` | HTF parameter candidates derived from forensic cross-trade analysis. |
| `../reports/v2_trade_validation_2026-03-15.yaml` | 4-trade validation report with bar-by-bar phase walkthrough. |
| `../reports/autoresearch/eval_*.yaml` | AutoResearch evaluation run outputs. |

## Research Archive

Other files in this directory are Phase 1 research documents (ICT primitives, gap analysis, deep research on FVG/BPR/displacement/swing points). Reference material, not actively maintained.

## Status

- v2.1 validated against 4 trades (4/4 PASS)
- HTF L1.5 parameters: PROPOSED (pending Olya visual confirmation)
- AutoResearch harness: built, sweep deferred until 10+ trades
