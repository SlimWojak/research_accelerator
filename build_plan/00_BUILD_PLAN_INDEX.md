# a8ra Research Accelerator — Build Plan

```yaml
purpose: Canonical planning artifacts for the Research Accelerator refactor
status: PLANNING — not yet implementation-ready
owner: Craig (CTO) + Opus (Architecture)
repo: https://github.com/SlimWojak/research_accelerator
date_created: 2026-03-08
```

## Document Index

| # | Document | Purpose | Status |
|---|----------|---------|--------|
| 01 | `01_RUNTIME_CONFIG_SCHEMA.yaml` | Machine-parseable config derived from v0.5 YAML | DRAFT |
| 02 | `02_MODULE_MANIFEST.md` | One entry per primitive module with regression expectations | DRAFT |
| 03 | `03_RIVER_ADAPTER_SPEC.md` | Read-only River consumption contract | DRAFT |
| 04 | `04_PHASE1_MISSION_BRIEF.md` | Droid Mission Control brief for detection engine build | DRAFT |

## Architecture Decisions (Locked for Build)

| Decision | Resolution |
|----------|-----------|
| Data source | River (read-only, parquet via DuckDB). No parallel data layer. |
| Isolation | No imports from Phoenix/Dexter. Clone detection logic. |
| Config format | YAML runtime config derived from SYNTHETIC_OLYA_METHOD_v0.5 |
| Graduation path | RA findings flow back to core as recommendations, not code |
| Regression gate | Current pipeline output on 5-day dataset = ground truth |
| Primary reference | `SYNTHETIC_OLYA_METHOD_v0.5.yaml` (canonical primitive spec) |

## Dependency Map

```
SYNTHETIC_OLYA_METHOD_v0.5.yaml  (what to detect, locked params)
        │
        ▼
01_RUNTIME_CONFIG_SCHEMA.yaml    (machine-parseable extract)
        │
        ▼
02_MODULE_MANIFEST.md            (what to build, per-module)
        │
        ▼
03_RIVER_ADAPTER_SPEC.md         (how data enters the engine)
        │
        ▼
04_PHASE1_MISSION_BRIEF.md       (Droid Mission Control execution plan)
```
