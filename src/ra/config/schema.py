"""Pydantic v2 models for RA runtime config validation.

Mirrors the structure of build_plan/01_RUNTIME_CONFIG_SCHEMA.yaml.
Uses extra='forbid' to reject unknown parameters.
"""

from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict


# ─── Schema version the engine expects ────────────────────────────────────
SUPPORTED_SCHEMA_VERSION = "1.0"


# ─── Base model with extra='forbid' ──────────────────────────────────────

class StrictModel(BaseModel):
    """Base model that rejects unknown fields."""

    model_config = ConfigDict(extra="forbid")


# ─── Constants ────────────────────────────────────────────────────────────

class SessionWindow(StrictModel):
    start_ny: str
    end_ny: str


class SessionsConfig(StrictModel):
    asia: SessionWindow
    lokz: SessionWindow
    nyokz: SessionWindow


class KillZonesConfig(StrictModel):
    lokz: SessionWindow
    nyokz: SessionWindow


class NYWindowsConfig(StrictModel):
    a: SessionWindow
    b: SessionWindow


class PreSessionWindowsConfig(StrictModel):
    pre_london: SessionWindow
    pre_ny: SessionWindow


class ConstantsConfig(StrictModel):
    pip: float
    forex_day_boundary_ny: str
    sessions: SessionsConfig
    kill_zones: KillZonesConfig
    ny_windows: NYWindowsConfig
    pre_session_windows: PreSessionWindowsConfig


# ─── Timeframes ───────────────────────────────────────────────────────────

class TimeframesConfig(StrictModel):
    available: list[str]
    execution: list[str]
    reference: list[str]
    direction: list[str]
    primary: str
    aggregation_base: str


# ─── Dependency Graph ─────────────────────────────────────────────────────

class DependencyNode(StrictModel):
    upstream: list[str]


# ─── Per-TF value helper ─────────────────────────────────────────────────

class LockedValue(StrictModel):
    """A single per-TF locked value."""
    locked: Any


# ─── FVG Config ───────────────────────────────────────────────────────────

class FVGParamFloor(StrictModel):
    locked: float
    sweep_range: Optional[list[float]] = None


class FVGParams(StrictModel):
    floor_threshold_pips: FVGParamFloor


class FVGTransition(StrictModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    # Use aliases for the 'from' field since 'from' is a Python keyword
    from_state: Optional[str] = None
    to: Optional[str] = None
    trigger: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        pass


class FVGStateMachine(StrictModel):
    states: list[str]
    transitions: list[dict[str, str]]


class FVGConfig(StrictModel):
    variant: str
    status: str
    params: FVGParams
    per_tf_overrides: Optional[dict[str, Any]] = None
    state_machine: FVGStateMachine


# ─── IFVG Config ──────────────────────────────────────────────────────────

class IFVGConfig(StrictModel):
    variant: str
    status: str
    params: dict[str, Any]
    note: Optional[str] = None


# ─── BPR Config ───────────────────────────────────────────────────────────

class BPRParamOverlap(StrictModel):
    locked: Optional[float] = None
    sweep_range: Optional[list[float]] = None


class BPRParams(StrictModel):
    min_overlap_pips: BPRParamOverlap


class BPRConfig(StrictModel):
    variant: str
    status: str
    params: BPRParams
    note: Optional[str] = None


# ─── Swing Points Config ─────────────────────────────────────────────────

class SwingPointsNPerTF(StrictModel):
    """Per-TF N values for swing detection."""
    model_config = ConfigDict(extra="allow")  # dynamic TF keys


class SwingPointsParams(StrictModel):
    N: dict[str, Any]  # per_tf + sweep_range
    height_filter_pips: dict[str, Any]  # per_tf + sweep_range
    strength_cap: int
    strength_as_gate: bool


class SwingPointsConfig(StrictModel):
    variant: str
    status: str
    params: SwingPointsParams


# ─── Displacement Config ─────────────────────────────────────────────────

class DisplacementLTFConfig(StrictModel):
    applies_to: list[str]
    atr_multiplier: dict[str, Any]
    body_ratio: dict[str, Any]
    close_gate: dict[str, Any]
    structure_close_required: bool


class DisplacementHTFConfig(StrictModel):
    applies_to: list[str]
    atr_multiplier: dict[str, Any]
    body_ratio: dict[str, Any]
    close_gate: dict[str, Any]
    structure_close_required: bool


class DecisiveOverrideConfig(StrictModel):
    enabled: bool
    body_min: float
    close_max: float
    pip_floor: dict[str, float]


class ClusterConfig(StrictModel):
    cluster_2_enabled: bool
    cluster_3_enabled: bool
    net_efficiency_min: float
    overlap_max: float


class QualityGradeSpec(StrictModel):
    atr_ratio_min: float


class DisplacementCombinationMode(StrictModel):
    locked: str
    options: list[str]


class DisplacementParams(StrictModel):
    atr_period: int
    combination_mode: DisplacementCombinationMode
    ltf: DisplacementLTFConfig
    htf: DisplacementHTFConfig
    decisive_override: DecisiveOverrideConfig
    cluster: ClusterConfig


class DisplacementConfig(StrictModel):
    variant: str
    status: str
    params: DisplacementParams
    quality_grades: dict[str, QualityGradeSpec]
    evaluation_order: list[str]


# ─── Session Liquidity Config ─────────────────────────────────────────────

class FourGateModelConfig(StrictModel):
    efficiency_threshold: dict[str, Any]
    mid_cross_min: dict[str, Any]
    balance_score_min: dict[str, Any]


class BoxObjectWindow(StrictModel):
    window: SessionWindow
    range_cap_pips: float


class BoxObjectsConfig(StrictModel):
    asia: BoxObjectWindow
    pre_london: BoxObjectWindow
    pre_ny: BoxObjectWindow


class SessionLiquidityParams(StrictModel):
    four_gate_model: FourGateModelConfig
    box_objects: BoxObjectsConfig


class SessionLiquidityConfig(StrictModel):
    variant: str
    status: str
    params: SessionLiquidityParams


# ─── Asia Range Config ────────────────────────────────────────────────────

class AsiaClassificationConfig(StrictModel):
    tight_below_pips: float
    mid_below_pips: float
    wide_above_pips: float


class AsiaRangeParams(StrictModel):
    classification: AsiaClassificationConfig
    max_cap_pips: float
    thresholds: list[int] = [12, 15, 18, 20, 25, 30]


class AsiaRangeConfig(StrictModel):
    variant: str
    status: str
    params: AsiaRangeParams


# ─── MSS Config ───────────────────────────────────────────────────────────

class ImpulseSuppressionConfig(StrictModel):
    pullback_reset_pips: float
    pullback_reset_atr_factor: float
    opposite_displacement_reset: bool
    new_day_reset: bool


class MSSLTFConfig(StrictModel):
    applies_to: list[str]
    displacement_required: bool
    confirmation_window_bars: int
    close_beyond_swing: bool
    impulse_suppression: ImpulseSuppressionConfig


class MSSHTFConfig(StrictModel):
    applies_to: list[str]
    displacement_required: bool
    confirmation_window_bars: int
    close_beyond_swing: bool
    structure_close_required: bool
    impulse_suppression: ImpulseSuppressionConfig


class MSSParams(StrictModel):
    ltf: MSSLTFConfig
    htf: MSSHTFConfig
    fvg_tag_only: bool
    break_classification: list[str]
    swing_consumption: bool


class MSSConfig(StrictModel):
    variant: str
    status: str
    params: MSSParams


# ─── Order Block Config ──────────────────────────────────────────────────

class ThinCandleFilterConfig(StrictModel):
    min_body_pct: float


class FallbackScanConfig(StrictModel):
    mode: str
    lookback_bars: int
    reject_if_none_found: bool


class OBTransition(StrictModel):
    model_config = ConfigDict(extra="allow")


class OBStateMachine(StrictModel):
    states: list[str]
    transitions: list[dict[str, str]]


class OrderBlockParams(StrictModel):
    trigger: str
    zone_type: str
    thin_candle_filter: ThinCandleFilterConfig
    fallback_scan: FallbackScanConfig
    expiration_bars: dict[str, Any]
    min_displacement_grade: str


class OrderBlockConfig(StrictModel):
    variant: str
    status: str
    params: OrderBlockParams
    state_machine: OBStateMachine


# ─── Liquidity Sweep Config ──────────────────────────────────────────────

class PromotedSwingConfig(StrictModel):
    enabled: bool
    strength_min: int
    height_pips_min: float
    scope: str
    staleness_bars: int


class LevelSourceConfig(StrictModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool


class QualifiedSweepConfig(StrictModel):
    displacement_before_lookback: int
    displacement_after_forward: int


class DelayedSweepConfig(StrictModel):
    enabled: bool
    min_delayed_wick_pct: Optional[float] = None
    max_delay_bars: Optional[int] = None


class ReturnWindowConfig(StrictModel):
    per_tf: dict[str, int]


class LiquiditySweepParams(StrictModel):
    return_window_bars: Union[int, ReturnWindowConfig]
    rejection_wick_pct: dict[str, Any]
    min_breach_pips: dict[str, Any]
    min_reclaim_pips: dict[str, Any]
    max_sweep_size_atr_mult: float
    directional_close: bool
    level_sources: dict[str, Any]
    level_merge_tolerance_pips: float
    qualified_sweep: QualifiedSweepConfig
    delayed_sweep: DelayedSweepConfig


class LiquiditySweepConfig(StrictModel):
    variant: str
    status: str
    params: LiquiditySweepParams


# ─── HTF Liquidity Config ────────────────────────────────────────────────

class HTFLiquidityParams(StrictModel):
    detection_source: str
    price_tolerance_pips: dict[str, Any]
    min_bars_between_touches: dict[str, Any]
    rotation_required: dict[str, Any]
    max_lookback: dict[str, Any]
    asia_range_filter: bool
    invalidation_during_formation: bool
    merge_tolerance_factor: float
    min_touches: int


class HTFLiquidityConfig(StrictModel):
    variant: str
    status: str
    params: HTFLiquidityParams


# ─── OTE Config ───────────────────────────────────────────────────────────

class FibLevelsConfig(StrictModel):
    lower: float
    sweet_spot: float
    upper: float


class OTEParams(StrictModel):
    fib_levels: FibLevelsConfig
    anchor_rule: str
    kill_zone_gate: bool


class OTEConfig(StrictModel):
    variant: str
    status: str
    params: OTEParams


# ─── Reference Levels Config ─────────────────────────────────────────────

class PDHPDLConfig(StrictModel):
    boundary: str
    measurement: str


class MidnightOpenConfig(StrictModel):
    time_ny: str


class EquilibriumConfig(StrictModel):
    formula: str


class ReferenceLevelsParams(StrictModel):
    pdh_pdl: PDHPDLConfig
    midnight_open: MidnightOpenConfig
    equilibrium: EquilibriumConfig


class ReferenceLevelsConfig(StrictModel):
    variant: str
    status: str
    params: ReferenceLevelsParams


# ─── Equal HL Config ──────────────────────────────────────────────────────

class EqualHLToleranceConfig(StrictModel):
    fixed_floor_pips: float
    atr_factor: float


class EqualHLPullbackConfig(StrictModel):
    pip_floor: float
    atr_factor: float


class EqualHLParams(StrictModel):
    tolerance: EqualHLToleranceConfig
    time_proximity: dict[str, Any]
    pullback: EqualHLPullbackConfig
    min_touches: int
    session_gate: list[str]


class EqualHLConfig(StrictModel):
    variant: str
    status: str
    params: EqualHLParams


# ─── Primitives Container ────────────────────────────────────────────────

class PrimitivesConfig(StrictModel):
    fvg: FVGConfig
    ifvg: IFVGConfig
    bpr: BPRConfig
    swing_points: SwingPointsConfig
    displacement: DisplacementConfig
    session_liquidity: SessionLiquidityConfig
    asia_range: AsiaRangeConfig
    mss: MSSConfig
    order_block: OrderBlockConfig
    liquidity_sweep: LiquiditySweepConfig
    htf_liquidity: HTFLiquidityConfig
    ote: OTEConfig
    reference_levels: ReferenceLevelsConfig
    equal_hl: EqualHLConfig


# ─── Evaluation Config ────────────────────────────────────────────────────

class RegimeSlicingConfig(StrictModel):
    enabled: bool
    auto_tags: list[str]
    manual_tags: list[str]


class EvaluationConfig(StrictModel):
    comparison_mode: str
    metrics: list[str]
    regime_slicing: RegimeSlicingConfig


# ─── Cascade Config ───────────────────────────────────────────────────────

class CascadeConfig(StrictModel):
    """Optional cascade-level configuration.

    Supports per-primitive variant selection via variant_by_primitive.
    """

    variant_by_primitive: Optional[dict[str, str]] = None


# ─── Top-Level Config ─────────────────────────────────────────────────────

class RAConfig(StrictModel):
    """Top-level RA runtime configuration.

    Validates the full YAML config against the schema.
    Rejects unknown parameters via extra='forbid'.
    """

    schema_version: str
    source_spec: str
    source_spec_version: str
    instrument: str
    constants: ConstantsConfig
    timeframes: TimeframesConfig
    dependency_graph: dict[str, DependencyNode]
    primitives: PrimitivesConfig
    evaluation: EvaluationConfig
    cascade: Optional[CascadeConfig] = None
