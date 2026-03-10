"""Tests for ground truth scoring pipeline.

TDD tests covering:
- Precision per primitive: correct / (correct + noise), BORDERLINE excluded
- Recall per primitive: correct / (correct + missed), missed defaults to 0
- F1 = 2*P*R/(P+R), null when P or R is null
- null returned when no CORRECT/NOISE labels exist
- Per-session breakdown: asia, lokz, nyokz, other
- Per-variant breakdown when multiple variants present
- Schema 4F output format
- Edge cases: all BORDERLINE, zero labels, deterministic output

Assertions fulfilled: VAL-SCORE-001 through VAL-SCORE-006
"""

import json
import math

import pytest

from ra.evaluation.scoring import (
    compute_precision,
    compute_recall,
    compute_f1,
    score_labels,
    session_from_detection_id,
)


# ── Helper fixtures ───────────────────────────────────────────────────────────


def _make_label(detection_id: str, primitive: str, timeframe: str, label: str) -> dict:
    """Helper to create a canonical label dict."""
    return {
        "detection_id": detection_id,
        "primitive": primitive,
        "timeframe": timeframe,
        "label": label,
        "labelled_by": "validate",
    }


# ── VAL-SCORE-001: Precision per primitive ────────────────────────────────────


class TestPrecision:
    """VAL-SCORE-001: Precision = correct/(correct+noise), BORDERLINE excluded."""

    def test_basic_precision(self):
        """Precision with 2 CORRECT, 1 NOISE = 2/3."""
        p = compute_precision(correct=2, noise=1)
        assert p == pytest.approx(2 / 3)

    def test_precision_all_correct(self):
        """Precision = 1.0 when all are CORRECT."""
        p = compute_precision(correct=5, noise=0)
        assert p == pytest.approx(1.0)

    def test_precision_all_noise(self):
        """Precision = 0.0 when all are NOISE."""
        p = compute_precision(correct=0, noise=5)
        assert p == pytest.approx(0.0)

    def test_precision_no_labels(self):
        """Precision = None when 0 CORRECT and 0 NOISE."""
        p = compute_precision(correct=0, noise=0)
        assert p is None

    def test_precision_borderline_excluded(self):
        """BORDERLINE does not affect precision."""
        # Precision is computed from correct + noise only
        # Borderline is NOT passed to compute_precision
        labels = [
            _make_label("disp_5m_2024-01-08T09:35:00_bear", "displacement", "5m", "CORRECT"),
            _make_label("disp_5m_2024-01-08T10:15:00_bull", "displacement", "5m", "CORRECT"),
            _make_label("disp_5m_2024-01-08T11:00:00_bear", "displacement", "5m", "NOISE"),
            _make_label("disp_5m_2024-01-08T12:00:00_bull", "displacement", "5m", "BORDERLINE"),
        ]
        result = score_labels(labels)
        # 2 correct, 1 noise -> precision = 2/3
        disp = result["per_primitive"]["displacement"]
        assert disp["precision"] == pytest.approx(2 / 3)


# ── VAL-SCORE-002: Recall per primitive ───────────────────────────────────────


class TestRecall:
    """VAL-SCORE-002: Recall = correct/(correct+missed), missed defaults to 0."""

    def test_basic_recall_no_missed(self):
        """Recall = 1.0 when no missed entries (missed defaults to 0)."""
        r = compute_recall(correct=3, missed=0)
        assert r == pytest.approx(1.0)

    def test_recall_with_missed(self):
        """Recall with missed entries."""
        r = compute_recall(correct=3, missed=2)
        assert r == pytest.approx(3 / 5)

    def test_recall_zero_correct_with_missed(self):
        """Recall = 0.0 when 0 correct but some missed."""
        r = compute_recall(correct=0, missed=5)
        assert r == pytest.approx(0.0)

    def test_recall_null_when_no_ground_truth(self):
        """Recall = None when 0 correct and 0 missed."""
        r = compute_recall(correct=0, missed=0)
        assert r is None

    def test_recall_from_labels_only(self):
        """When only labelled detections exist, missed=0 -> recall=1.0."""
        labels = [
            _make_label("mss_5m_2024-01-08T08:30:00_bull", "mss", "5m", "CORRECT"),
            _make_label("mss_5m_2024-01-08T09:00:00_bear", "mss", "5m", "NOISE"),
        ]
        result = score_labels(labels)
        mss = result["per_primitive"]["mss"]
        # 1 correct, 0 missed -> recall = 1.0
        assert mss["recall"] == pytest.approx(1.0)


# ── VAL-SCORE-003: F1 per primitive ──────────────────────────────────────────


class TestF1:
    """VAL-SCORE-003: F1 = 2*P*R/(P+R), null when P or R is null."""

    def test_f1_basic(self):
        """F1 = 2*P*R/(P+R)."""
        f = compute_f1(precision=2 / 3, recall=1.0)
        expected = 2 * (2 / 3) * 1.0 / (2 / 3 + 1.0)
        assert f == pytest.approx(expected)

    def test_f1_perfect(self):
        """F1 = 1.0 when both P and R are 1.0."""
        f = compute_f1(precision=1.0, recall=1.0)
        assert f == pytest.approx(1.0)

    def test_f1_both_zero(self):
        """F1 = 0.0 when both P and R are 0.0."""
        f = compute_f1(precision=0.0, recall=0.0)
        assert f == pytest.approx(0.0)

    def test_f1_null_when_precision_null(self):
        """F1 = None when precision is None."""
        f = compute_f1(precision=None, recall=1.0)
        assert f is None

    def test_f1_null_when_recall_null(self):
        """F1 = None when recall is None."""
        f = compute_f1(precision=0.8, recall=None)
        assert f is None

    def test_f1_null_when_both_null(self):
        """F1 = None when both precision and recall are None."""
        f = compute_f1(precision=None, recall=None)
        assert f is None

    def test_f1_from_labels(self):
        """F1 computed end-to-end from labels."""
        labels = [
            _make_label("disp_5m_2024-01-08T09:35:00_bear", "displacement", "5m", "CORRECT"),
            _make_label("disp_5m_2024-01-08T10:15:00_bull", "displacement", "5m", "CORRECT"),
            _make_label("disp_5m_2024-01-08T11:00:00_bear", "displacement", "5m", "NOISE"),
        ]
        result = score_labels(labels)
        disp = result["per_primitive"]["displacement"]
        p = 2 / 3  # 2 correct, 1 noise
        r = 1.0  # 2 correct, 0 missed
        expected_f1 = 2 * p * r / (p + r)
        assert disp["f1"] == pytest.approx(expected_f1)


# ── VAL-SCORE-004: Per-session breakdown ──────────────────────────────────────


class TestPerSessionBreakdown:
    """VAL-SCORE-004: Per-session breakdown of precision/recall/F1."""

    def test_session_from_detection_id_asia(self):
        """Asia session: hour >= 19 NY."""
        # 19:30 NY = asia
        session = session_from_detection_id("disp_5m_2024-01-08T19:30:00_bear")
        assert session == "asia"

    def test_session_from_detection_id_lokz(self):
        """LOKZ session: 2 <= hour < 5 NY."""
        session = session_from_detection_id("mss_5m_2024-01-08T03:00:00_bull")
        assert session == "lokz"

    def test_session_from_detection_id_nyokz(self):
        """NYOKZ session: 7 <= hour < 10 NY."""
        session = session_from_detection_id("disp_5m_2024-01-08T08:30:00_bear")
        assert session == "nyokz"

    def test_session_from_detection_id_other(self):
        """Other session: 10 <= hour < 19 NY."""
        session = session_from_detection_id("disp_5m_2024-01-08T14:00:00_bull")
        assert session == "other"

    def test_session_from_detection_id_pre_london_maps_to_other(self):
        """Pre-London (0 <= hour < 2) maps to other."""
        session = session_from_detection_id("disp_5m_2024-01-08T01:00:00_bear")
        assert session == "other"

    def test_session_from_detection_id_pre_ny_maps_to_other(self):
        """Pre-NY (5 <= hour < 7) maps to other."""
        session = session_from_detection_id("disp_5m_2024-01-08T06:00:00_bull")
        assert session == "other"

    def test_per_session_in_output(self):
        """Per-session dict present in output for each primitive."""
        labels = [
            # Asia: 1 CORRECT
            _make_label("disp_5m_2024-01-08T19:30:00_bear", "displacement", "5m", "CORRECT"),
            # LOKZ: 1 CORRECT, 1 NOISE
            _make_label("disp_5m_2024-01-08T03:00:00_bull", "displacement", "5m", "CORRECT"),
            _make_label("disp_5m_2024-01-08T04:00:00_bear", "displacement", "5m", "NOISE"),
            # NYOKZ: 1 CORRECT
            _make_label("disp_5m_2024-01-08T08:30:00_bear", "displacement", "5m", "CORRECT"),
            # Other: 1 NOISE
            _make_label("disp_5m_2024-01-08T14:00:00_bull", "displacement", "5m", "NOISE"),
        ]
        result = score_labels(labels)
        disp = result["per_primitive"]["displacement"]
        assert "per_session" in disp

        ps = disp["per_session"]
        assert set(ps.keys()) == {"asia", "lokz", "nyokz", "other"}

    def test_per_session_asia_scores(self):
        """Asia session scores computed correctly."""
        labels = [
            # Asia: 2 CORRECT, 0 NOISE
            _make_label("disp_5m_2024-01-08T19:30:00_bear", "displacement", "5m", "CORRECT"),
            _make_label("disp_5m_2024-01-08T20:00:00_bull", "displacement", "5m", "CORRECT"),
            # NYOKZ: 1 NOISE (to make aggregate different from asia)
            _make_label("disp_5m_2024-01-08T08:30:00_bear", "displacement", "5m", "NOISE"),
        ]
        result = score_labels(labels)
        asia = result["per_primitive"]["displacement"]["per_session"]["asia"]
        assert asia["precision"] == pytest.approx(1.0)
        assert asia["recall"] == pytest.approx(1.0)
        assert asia["f1"] == pytest.approx(1.0)
        assert asia["label_count"] == 2

    def test_per_session_lokz_scores(self):
        """LOKZ session: 1 correct, 1 noise -> precision=0.5."""
        labels = [
            _make_label("disp_5m_2024-01-08T03:00:00_bull", "displacement", "5m", "CORRECT"),
            _make_label("disp_5m_2024-01-08T04:00:00_bear", "displacement", "5m", "NOISE"),
        ]
        result = score_labels(labels)
        lokz = result["per_primitive"]["displacement"]["per_session"]["lokz"]
        assert lokz["precision"] == pytest.approx(0.5)
        assert lokz["label_count"] == 2

    def test_per_session_empty_session_null_scores(self):
        """Session with 0 labels has null precision/recall/f1 and label_count=0."""
        labels = [
            # Only LOKZ labels
            _make_label("disp_5m_2024-01-08T03:00:00_bull", "displacement", "5m", "CORRECT"),
        ]
        result = score_labels(labels)
        # Asia has no labels
        asia = result["per_primitive"]["displacement"]["per_session"]["asia"]
        assert asia["precision"] is None
        assert asia["recall"] is None
        assert asia["f1"] is None
        assert asia["label_count"] == 0


# ── VAL-SCORE-005: Per-variant breakdown ──────────────────────────────────────


class TestPerVariantBreakdown:
    """VAL-SCORE-005: Per-variant breakdown when multiple variants present."""

    def test_single_variant(self):
        """Single variant: per_variant has one entry matching aggregate."""
        labels = [
            _make_label("disp_5m_2024-01-08T09:35:00_bear", "displacement", "5m", "CORRECT"),
            _make_label("disp_5m_2024-01-08T10:15:00_bull", "displacement", "5m", "NOISE"),
        ]
        variant_map = {
            "disp_5m_2024-01-08T09:35:00_bear": "a8ra_v1",
            "disp_5m_2024-01-08T10:15:00_bull": "a8ra_v1",
        }
        result = score_labels(labels, variant_map=variant_map)
        disp = result["per_primitive"]["displacement"]
        assert "per_variant" in disp
        assert "a8ra_v1" in disp["per_variant"]
        a8ra = disp["per_variant"]["a8ra_v1"]
        assert a8ra["precision"] == pytest.approx(disp["precision"])

    def test_multiple_variants(self):
        """Multiple variants: separate scores per variant."""
        labels = [
            # a8ra_v1: 2 CORRECT
            _make_label("disp_5m_2024-01-08T09:35:00_bear", "displacement", "5m", "CORRECT"),
            _make_label("disp_5m_2024-01-08T10:15:00_bull", "displacement", "5m", "CORRECT"),
            # luxalgo_v1: 1 CORRECT, 2 NOISE
            _make_label("disp_5m_2024-01-08T11:00:00_bear", "displacement", "5m", "CORRECT"),
            _make_label("disp_5m_2024-01-08T12:00:00_bull", "displacement", "5m", "NOISE"),
            _make_label("disp_5m_2024-01-08T13:00:00_bear", "displacement", "5m", "NOISE"),
        ]
        variant_map = {
            "disp_5m_2024-01-08T09:35:00_bear": "a8ra_v1",
            "disp_5m_2024-01-08T10:15:00_bull": "a8ra_v1",
            "disp_5m_2024-01-08T11:00:00_bear": "luxalgo_v1",
            "disp_5m_2024-01-08T12:00:00_bull": "luxalgo_v1",
            "disp_5m_2024-01-08T13:00:00_bear": "luxalgo_v1",
        }
        result = score_labels(labels, variant_map=variant_map)
        disp = result["per_primitive"]["displacement"]
        pv = disp["per_variant"]

        # a8ra_v1: 2 correct, 0 noise -> precision=1.0
        assert pv["a8ra_v1"]["precision"] == pytest.approx(1.0)
        # luxalgo_v1: 1 correct, 2 noise -> precision=1/3
        assert pv["luxalgo_v1"]["precision"] == pytest.approx(1 / 3)

    def test_no_variant_map_no_per_variant(self):
        """Without variant_map, per_variant is empty dict."""
        labels = [
            _make_label("disp_5m_2024-01-08T09:35:00_bear", "displacement", "5m", "CORRECT"),
        ]
        result = score_labels(labels)
        disp = result["per_primitive"]["displacement"]
        assert disp["per_variant"] == {}

    def test_variant_map_partial_coverage(self):
        """Variant map doesn't cover all labels — unmapped labels excluded from per_variant."""
        labels = [
            _make_label("disp_5m_2024-01-08T09:35:00_bear", "displacement", "5m", "CORRECT"),
            _make_label("disp_5m_2024-01-08T10:15:00_bull", "displacement", "5m", "NOISE"),
        ]
        # Only map one label
        variant_map = {
            "disp_5m_2024-01-08T09:35:00_bear": "a8ra_v1",
        }
        result = score_labels(labels, variant_map=variant_map)
        disp = result["per_primitive"]["displacement"]
        # Aggregate still uses all labels
        assert disp["precision"] == pytest.approx(0.5)
        # per_variant only has a8ra_v1 with the mapped label
        assert "a8ra_v1" in disp["per_variant"]
        assert disp["per_variant"]["a8ra_v1"]["label_count"] == 1


# ── VAL-SCORE-006: Schema 4F output format ───────────────────────────────────


class TestSchema4FOutput:
    """VAL-SCORE-006: Output follows Schema 4F."""

    def test_top_level_fields(self):
        """Output has schema_version, scored_at, label_source, per_primitive, aggregate."""
        labels = [
            _make_label("disp_5m_2024-01-08T09:35:00_bear", "displacement", "5m", "CORRECT"),
        ]
        result = score_labels(labels)
        assert "schema_version" in result
        assert result["schema_version"] == "1.0"
        assert "scored_at" in result
        assert "label_source" in result
        assert "per_primitive" in result
        assert "aggregate" in result

    def test_label_source_fields(self):
        """label_source has validate_count, compare_count, total."""
        labels = [
            {
                "detection_id": "disp_5m_2024-01-08T09:35:00_bear",
                "primitive": "displacement",
                "timeframe": "5m",
                "label": "CORRECT",
                "labelled_by": "validate",
            },
            {
                "detection_id": "mss_5m_2024-01-08T10:15:00_bull",
                "primitive": "mss",
                "timeframe": "5m",
                "label": "NOISE",
                "labelled_by": "compare",
            },
        ]
        result = score_labels(labels)
        ls = result["label_source"]
        assert ls["validate_count"] == 1
        assert ls["compare_count"] == 1
        assert ls["total"] == 2

    def test_per_primitive_fields(self):
        """Each per_primitive entry has precision, recall, f1, label_count, correct, noise, borderline, per_session, per_variant."""
        labels = [
            _make_label("disp_5m_2024-01-08T09:35:00_bear", "displacement", "5m", "CORRECT"),
            _make_label("disp_5m_2024-01-08T10:15:00_bull", "displacement", "5m", "NOISE"),
            _make_label("disp_5m_2024-01-08T11:00:00_bear", "displacement", "5m", "BORDERLINE"),
        ]
        result = score_labels(labels)
        disp = result["per_primitive"]["displacement"]
        expected_keys = {
            "precision", "recall", "f1",
            "label_count", "correct", "noise", "borderline",
            "per_session", "per_variant",
        }
        assert expected_keys.issubset(set(disp.keys()))

    def test_per_primitive_counts(self):
        """Correct/noise/borderline counts accurate."""
        labels = [
            _make_label("disp_5m_2024-01-08T09:35:00_bear", "displacement", "5m", "CORRECT"),
            _make_label("disp_5m_2024-01-08T10:15:00_bull", "displacement", "5m", "CORRECT"),
            _make_label("disp_5m_2024-01-08T11:00:00_bear", "displacement", "5m", "NOISE"),
            _make_label("disp_5m_2024-01-08T12:00:00_bull", "displacement", "5m", "BORDERLINE"),
        ]
        result = score_labels(labels)
        disp = result["per_primitive"]["displacement"]
        assert disp["correct"] == 2
        assert disp["noise"] == 1
        assert disp["borderline"] == 1
        assert disp["label_count"] == 4

    def test_aggregate_fields(self):
        """Aggregate has precision, recall, f1, total_labels."""
        labels = [
            _make_label("disp_5m_2024-01-08T09:35:00_bear", "displacement", "5m", "CORRECT"),
            _make_label("mss_5m_2024-01-08T10:15:00_bull", "mss", "5m", "NOISE"),
        ]
        result = score_labels(labels)
        agg = result["aggregate"]
        assert "precision" in agg
        assert "recall" in agg
        assert "f1" in agg
        assert "total_labels" in agg
        assert agg["total_labels"] == 2

    def test_aggregate_precision_across_primitives(self):
        """Aggregate precision is computed from total correct / (total correct + total noise)."""
        labels = [
            # displacement: 2 correct, 1 noise
            _make_label("disp_5m_2024-01-08T09:35:00_bear", "displacement", "5m", "CORRECT"),
            _make_label("disp_5m_2024-01-08T10:15:00_bull", "displacement", "5m", "CORRECT"),
            _make_label("disp_5m_2024-01-08T11:00:00_bear", "displacement", "5m", "NOISE"),
            # mss: 1 correct, 0 noise
            _make_label("mss_5m_2024-01-08T08:30:00_bull", "mss", "5m", "CORRECT"),
        ]
        result = score_labels(labels)
        # Total: 3 correct, 1 noise -> precision = 3/4
        assert result["aggregate"]["precision"] == pytest.approx(3 / 4)

    def test_per_session_all_four_sessions(self):
        """per_session always has exactly 4 keys: asia, lokz, nyokz, other."""
        labels = [
            _make_label("disp_5m_2024-01-08T08:30:00_bear", "displacement", "5m", "CORRECT"),
        ]
        result = score_labels(labels)
        ps = result["per_primitive"]["displacement"]["per_session"]
        assert set(ps.keys()) == {"asia", "lokz", "nyokz", "other"}

    def test_per_session_entry_fields(self):
        """Each per_session entry has precision, recall, f1, label_count."""
        labels = [
            _make_label("disp_5m_2024-01-08T08:30:00_bear", "displacement", "5m", "CORRECT"),
        ]
        result = score_labels(labels)
        nyokz = result["per_primitive"]["displacement"]["per_session"]["nyokz"]
        assert "precision" in nyokz
        assert "recall" in nyokz
        assert "f1" in nyokz
        assert "label_count" in nyokz

    def test_json_serializable(self):
        """Output is JSON-serializable (no numpy, no NaN)."""
        labels = [
            _make_label("disp_5m_2024-01-08T09:35:00_bear", "displacement", "5m", "CORRECT"),
            _make_label("disp_5m_2024-01-08T10:15:00_bull", "displacement", "5m", "NOISE"),
        ]
        result = score_labels(labels)
        serialized = json.dumps(result)
        # Should not contain NaN
        assert "NaN" not in serialized
        assert "Infinity" not in serialized

    def test_null_values_for_no_label_primitive(self):
        """Primitive with only BORDERLINE → precision=null, recall=null, f1=null."""
        labels = [
            _make_label("disp_5m_2024-01-08T09:35:00_bear", "displacement", "5m", "BORDERLINE"),
            _make_label("disp_5m_2024-01-08T10:15:00_bull", "displacement", "5m", "BORDERLINE"),
        ]
        result = score_labels(labels)
        disp = result["per_primitive"]["displacement"]
        assert disp["precision"] is None
        assert disp["recall"] is None
        assert disp["f1"] is None
        assert disp["label_count"] == 2
        assert disp["borderline"] == 2


# ── Edge cases ────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Additional edge cases for scoring robustness."""

    def test_empty_labels_list(self):
        """Empty labels → aggregate all null, per_primitive empty."""
        result = score_labels([])
        assert result["aggregate"]["precision"] is None
        assert result["aggregate"]["recall"] is None
        assert result["aggregate"]["f1"] is None
        assert result["aggregate"]["total_labels"] == 0
        assert result["per_primitive"] == {}

    def test_all_borderline_aggregate(self):
        """All BORDERLINE labels → aggregate null scores."""
        labels = [
            _make_label("disp_5m_2024-01-08T09:35:00_bear", "displacement", "5m", "BORDERLINE"),
        ]
        result = score_labels(labels)
        assert result["aggregate"]["precision"] is None
        assert result["aggregate"]["recall"] is None
        assert result["aggregate"]["f1"] is None
        assert result["aggregate"]["total_labels"] == 1

    def test_multiple_primitives(self):
        """Multiple primitives each get their own scores."""
        labels = [
            _make_label("disp_5m_2024-01-08T09:35:00_bear", "displacement", "5m", "CORRECT"),
            _make_label("mss_5m_2024-01-08T08:30:00_bull", "mss", "5m", "CORRECT"),
            _make_label("mss_5m_2024-01-08T09:00:00_bear", "mss", "5m", "NOISE"),
            _make_label("ob_5m_2024-01-08T10:00:00_bull", "order_block", "5m", "BORDERLINE"),
        ]
        result = score_labels(labels)
        assert "displacement" in result["per_primitive"]
        assert "mss" in result["per_primitive"]
        assert "order_block" in result["per_primitive"]

        # displacement: 1 correct, 0 noise -> precision = 1.0
        assert result["per_primitive"]["displacement"]["precision"] == pytest.approx(1.0)
        # mss: 1 correct, 1 noise -> precision = 0.5
        assert result["per_primitive"]["mss"]["precision"] == pytest.approx(0.5)
        # order_block: only BORDERLINE -> precision = None
        assert result["per_primitive"]["order_block"]["precision"] is None

    def test_deterministic_output(self):
        """Same labels produce identical output (excluding scored_at)."""
        labels = [
            _make_label("disp_5m_2024-01-08T09:35:00_bear", "displacement", "5m", "CORRECT"),
            _make_label("mss_5m_2024-01-08T08:30:00_bull", "mss", "5m", "NOISE"),
            _make_label("mss_5m_2024-01-08T09:00:00_bear", "mss", "5m", "CORRECT"),
        ]
        result1 = score_labels(labels)
        result2 = score_labels(labels)
        # Remove scored_at for comparison
        r1 = {k: v for k, v in result1.items() if k != "scored_at"}
        r2 = {k: v for k, v in result2.items() if k != "scored_at"}
        assert r1 == r2

    def test_missed_labels_affect_recall(self):
        """Labels with label=MISSED reduce recall."""
        labels = [
            _make_label("disp_5m_2024-01-08T09:35:00_bear", "displacement", "5m", "CORRECT"),
            _make_label("disp_5m_2024-01-08T10:15:00_bull", "displacement", "5m", "CORRECT"),
            # MISSED entries represent ground truth positives that the engine didn't detect
            _make_label("disp_5m_2024-01-08T11:00:00_bear", "displacement", "5m", "MISSED"),
        ]
        result = score_labels(labels)
        disp = result["per_primitive"]["displacement"]
        # 2 correct, 1 missed -> recall = 2/3
        assert disp["recall"] == pytest.approx(2 / 3)
        # Precision: MISSED not in denominator (only CORRECT+NOISE)
        # 2 correct, 0 noise -> precision = 1.0
        assert disp["precision"] == pytest.approx(1.0)

    def test_per_variant_scores_independent(self):
        """Per-variant scores are computed independently."""
        labels = [
            # a8ra: all correct
            _make_label("disp_5m_2024-01-08T09:35:00_bear", "displacement", "5m", "CORRECT"),
            _make_label("disp_5m_2024-01-08T10:15:00_bull", "displacement", "5m", "CORRECT"),
            # luxalgo: 1 correct, 1 noise
            _make_label("disp_5m_2024-01-08T11:00:00_bear", "displacement", "5m", "CORRECT"),
            _make_label("disp_5m_2024-01-08T12:00:00_bull", "displacement", "5m", "NOISE"),
        ]
        variant_map = {
            "disp_5m_2024-01-08T09:35:00_bear": "a8ra_v1",
            "disp_5m_2024-01-08T10:15:00_bull": "a8ra_v1",
            "disp_5m_2024-01-08T11:00:00_bear": "luxalgo_v1",
            "disp_5m_2024-01-08T12:00:00_bull": "luxalgo_v1",
        }
        result = score_labels(labels, variant_map=variant_map)
        pv = result["per_primitive"]["displacement"]["per_variant"]
        # a8ra: precision=1.0, recall=1.0, f1=1.0
        assert pv["a8ra_v1"]["precision"] == pytest.approx(1.0)
        assert pv["a8ra_v1"]["recall"] == pytest.approx(1.0)
        assert pv["a8ra_v1"]["f1"] == pytest.approx(1.0)
        # luxalgo: precision=0.5, recall=1.0
        assert pv["luxalgo_v1"]["precision"] == pytest.approx(0.5)
        assert pv["luxalgo_v1"]["recall"] == pytest.approx(1.0)

    def test_per_variant_entry_fields(self):
        """Each per_variant entry has precision, recall, f1, label_count."""
        labels = [
            _make_label("disp_5m_2024-01-08T09:35:00_bear", "displacement", "5m", "CORRECT"),
        ]
        variant_map = {"disp_5m_2024-01-08T09:35:00_bear": "a8ra_v1"}
        result = score_labels(labels, variant_map=variant_map)
        a8ra = result["per_primitive"]["displacement"]["per_variant"]["a8ra_v1"]
        assert "precision" in a8ra
        assert "recall" in a8ra
        assert "f1" in a8ra
        assert "label_count" in a8ra
