"""Tests for ground truth label ingestion module.

TDD tests covering:
- Loading validate-mode disk labels from site/data/labels/*.json
- Loading compare-mode export labels from ground_truth_labels.json
- Normalization to 5-field canonical format
- Label value uppercasing
- labelled_by source tagging
- Deduplication (validate-mode takes precedence)
- Empty/missing directory handling
- Summary counts (total, per-label, per-primitive, per-source)

Assertions fulfilled: VAL-LING-001, VAL-LING-002, VAL-LING-003, VAL-LING-004
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from ra.evaluation.label_ingestion import (
    load_validate_labels,
    load_compare_labels,
    load_all_labels,
    normalize_label,
    compute_label_summary,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def validate_labels_dir(tmp_path):
    """Create a temp directory with validate-mode label files."""
    labels_dir = tmp_path / "labels"
    labels_dir.mkdir()

    week1 = [
        {
            "detection_id": "displacement_5m_2025-10-20T03:55:00_bear",
            "primitive": "displacement",
            "timeframe": "5m",
            "direction": "bearish",
            "label": "CORRECT",
            "forex_day": "2025-10-20",
            "labeled_at": "2026-03-09T11:55:21.660Z",
        },
        {
            "detection_id": "mss_5m_2025-10-20T08:30:00_bull",
            "primitive": "mss",
            "timeframe": "5m",
            "direction": "bullish",
            "label": "NOISE",
            "forex_day": "2025-10-20",
            "labeled_at": "2026-03-09T12:00:00.000Z",
        },
    ]

    week2 = [
        {
            "detection_id": "order_block_15m_2025-10-27T09:00:00_bear",
            "primitive": "order_block",
            "timeframe": "15m",
            "direction": "bearish",
            "label": "BORDERLINE",
            "forex_day": "2025-10-27",
            "labeled_at": "2026-03-09T13:00:00.000Z",
        },
    ]

    (labels_dir / "2025-W43.json").write_text(json.dumps(week1, indent=2))
    (labels_dir / "2025-W44.json").write_text(json.dumps(week2, indent=2))

    return labels_dir


@pytest.fixture
def compare_labels_file(tmp_path):
    """Create a compare-mode export JSON file."""
    labels = [
        {
            "detection_id": "displacement_5m_2024-01-08T09:35:00_bear",
            "primitive": "displacement",
            "timeframe": "5m",
            "label": "CORRECT",
            "labelled_date": "2026-03-09T14:00:00.000Z",
        },
        {
            "detection_id": "mss_5m_2024-01-08T10:15:00_bull",
            "primitive": "mss",
            "timeframe": "5m",
            "label": "NOISE",
            "labelled_date": "2026-03-09T14:05:00.000Z",
        },
    ]

    filepath = tmp_path / "ground_truth_labels.json"
    filepath.write_text(json.dumps(labels, indent=2))
    return filepath


@pytest.fixture
def overlapping_labels(tmp_path):
    """Create validate and compare labels with overlapping detection_ids."""
    labels_dir = tmp_path / "labels"
    labels_dir.mkdir()

    # Validate-mode label for a detection
    validate_labels = [
        {
            "detection_id": "displacement_5m_2025-10-20T03:55:00_bear",
            "primitive": "displacement",
            "timeframe": "5m",
            "direction": "bearish",
            "label": "CORRECT",
            "forex_day": "2025-10-20",
            "labeled_at": "2026-03-09T11:55:21.660Z",
        },
    ]
    (labels_dir / "2025-W43.json").write_text(json.dumps(validate_labels, indent=2))

    # Compare-mode label for the SAME detection_id but different label
    compare_labels = [
        {
            "detection_id": "displacement_5m_2025-10-20T03:55:00_bear",
            "primitive": "displacement",
            "timeframe": "5m",
            "label": "NOISE",
            "labelled_date": "2026-03-09T14:00:00.000Z",
        },
        {
            "detection_id": "mss_5m_2025-10-20T08:30:00_bull",
            "primitive": "mss",
            "timeframe": "5m",
            "label": "BORDERLINE",
            "labelled_date": "2026-03-09T14:05:00.000Z",
        },
    ]
    compare_file = tmp_path / "ground_truth_labels.json"
    compare_file.write_text(json.dumps(compare_labels, indent=2))

    return labels_dir, compare_file


# ── VAL-LING-001: Loads labels from validate-mode disk JSON ───────────────────


class TestLoadValidateLabels:
    """VAL-LING-001: Loads labels from validate-mode disk JSON."""

    def test_loads_all_files(self, validate_labels_dir):
        """Combined label count equals sum across all files."""
        labels = load_validate_labels(validate_labels_dir)
        assert len(labels) == 3  # 2 from week1 + 1 from week2

    def test_labels_are_canonical(self, validate_labels_dir):
        """Every label has exactly 5 canonical fields."""
        labels = load_validate_labels(validate_labels_dir)
        required_fields = {"detection_id", "primitive", "timeframe", "label", "labelled_by"}
        for label in labels:
            assert set(label.keys()) == required_fields, (
                f"Label has unexpected fields: {set(label.keys())} (expected {required_fields})"
            )

    def test_labelled_by_is_validate(self, validate_labels_dir):
        """All validate-mode labels have labelled_by='validate'."""
        labels = load_validate_labels(validate_labels_dir)
        for label in labels:
            assert label["labelled_by"] == "validate"

    def test_label_values_uppercase(self, validate_labels_dir):
        """All label values are uppercase."""
        labels = load_validate_labels(validate_labels_dir)
        for label in labels:
            assert label["label"] in ("CORRECT", "NOISE", "BORDERLINE")
            assert label["label"] == label["label"].upper()

    def test_no_errors_on_well_formed_files(self, validate_labels_dir):
        """No exceptions raised on well-formed files."""
        # Should not raise
        labels = load_validate_labels(validate_labels_dir)
        assert isinstance(labels, list)


# ── VAL-LING-002: Loads labels from compare-mode export JSON ──────────────────


class TestLoadCompareLabels:
    """VAL-LING-002: Loads labels from compare-mode export JSON."""

    def test_loads_compare_file(self, compare_labels_file):
        """Loaded count matches file entries."""
        labels = load_compare_labels(compare_labels_file)
        assert len(labels) == 2

    def test_canonical_format(self, compare_labels_file):
        """Produces same canonical format as validate-mode labels."""
        labels = load_compare_labels(compare_labels_file)
        required_fields = {"detection_id", "primitive", "timeframe", "label", "labelled_by"}
        for label in labels:
            assert set(label.keys()) == required_fields

    def test_labelled_by_is_compare(self, compare_labels_file):
        """All compare-mode labels have labelled_by='compare'."""
        labels = load_compare_labels(compare_labels_file)
        for label in labels:
            assert label["labelled_by"] == "compare"


# ── VAL-LING-003: Normalizes to canonical format ─────────────────────────────


class TestNormalization:
    """VAL-LING-003: Every label normalized to {detection_id, primitive, timeframe, label, labelled_by}."""

    def test_normalize_validate_label(self):
        """Validate-mode label normalizes correctly."""
        raw = {
            "detection_id": "displacement_5m_2025-10-20T03:55:00_bear",
            "primitive": "displacement",
            "timeframe": "5m",
            "direction": "bearish",
            "label": "CORRECT",
            "forex_day": "2025-10-20",
            "labeled_at": "2026-03-09T11:55:21.660Z",
        }
        result = normalize_label(raw, source="validate")
        assert result == {
            "detection_id": "displacement_5m_2025-10-20T03:55:00_bear",
            "primitive": "displacement",
            "timeframe": "5m",
            "label": "CORRECT",
            "labelled_by": "validate",
        }

    def test_normalize_compare_label(self):
        """Compare-mode label normalizes correctly."""
        raw = {
            "detection_id": "displacement_5m_2024-01-08T09:35:00_bear",
            "primitive": "displacement",
            "timeframe": "5m",
            "label": "CORRECT",
            "labelled_date": "2026-03-09T14:00:00.000Z",
        }
        result = normalize_label(raw, source="compare")
        assert result == {
            "detection_id": "displacement_5m_2024-01-08T09:35:00_bear",
            "primitive": "displacement",
            "timeframe": "5m",
            "label": "CORRECT",
            "labelled_by": "compare",
        }

    def test_label_uppercased(self):
        """Lowercase label values are uppercased."""
        raw = {
            "detection_id": "mss_5m_2025-10-20T08:30:00_bull",
            "primitive": "mss",
            "timeframe": "5m",
            "label": "correct",
        }
        result = normalize_label(raw, source="validate")
        assert result["label"] == "CORRECT"

    def test_label_mixed_case_uppercased(self):
        """Mixed-case label values are uppercased."""
        raw = {
            "detection_id": "mss_5m_2025-10-20T08:30:00_bull",
            "primitive": "mss",
            "timeframe": "5m",
            "label": "Borderline",
        }
        result = normalize_label(raw, source="compare")
        assert result["label"] == "BORDERLINE"

    def test_only_five_fields(self):
        """Extra fields are stripped — only 5 canonical fields remain."""
        raw = {
            "detection_id": "fvg_5m_2025-10-20T03:55:00_bull",
            "primitive": "fvg",
            "timeframe": "5m",
            "label": "NOISE",
            "direction": "bullish",
            "forex_day": "2025-10-20",
            "labeled_at": "2026-03-09T11:55:21.660Z",
            "extra_field": "should_be_stripped",
        }
        result = normalize_label(raw, source="validate")
        assert len(result) == 5
        assert "direction" not in result
        assert "forex_day" not in result
        assert "labeled_at" not in result
        assert "extra_field" not in result


# ── VAL-LING-004: Handles empty/missing gracefully ───────────────────────────


class TestEmptyMissingGraceful:
    """VAL-LING-004: Empty/missing directory → empty list (no crash, no exception)."""

    def test_missing_directory(self, tmp_path):
        """Missing label directory returns empty list."""
        missing_dir = tmp_path / "nonexistent"
        labels = load_validate_labels(missing_dir)
        assert labels == []

    def test_empty_directory(self, tmp_path):
        """Empty label directory returns empty list."""
        empty_dir = tmp_path / "empty_labels"
        empty_dir.mkdir()
        labels = load_validate_labels(empty_dir)
        assert labels == []

    def test_empty_json_array_files(self, tmp_path):
        """Files with empty arrays are loaded without error."""
        labels_dir = tmp_path / "labels"
        labels_dir.mkdir()
        (labels_dir / "2025-W43.json").write_text("[]")
        labels = load_validate_labels(labels_dir)
        assert labels == []

    def test_missing_compare_file(self, tmp_path):
        """Missing compare-mode file returns empty list."""
        missing_file = tmp_path / "nonexistent.json"
        labels = load_compare_labels(missing_file)
        assert labels == []

    def test_empty_compare_file(self, tmp_path):
        """Compare-mode file with empty array returns empty list."""
        filepath = tmp_path / "empty.json"
        filepath.write_text("[]")
        labels = load_compare_labels(filepath)
        assert labels == []

    def test_none_paths(self):
        """None paths for both sources returns empty list."""
        labels = load_all_labels(validate_dir=None, compare_file=None)
        assert labels == []


# ── Deduplication ─────────────────────────────────────────────────────────────


class TestDeduplication:
    """Deduplication: same detection_id → validate-mode wins."""

    def test_validate_takes_precedence(self, overlapping_labels):
        """When same detection_id in both sources, validate-mode label wins."""
        labels_dir, compare_file = overlapping_labels
        labels = load_all_labels(validate_dir=labels_dir, compare_file=compare_file)

        # Find the overlapping detection
        overlapping = [
            l for l in labels
            if l["detection_id"] == "displacement_5m_2025-10-20T03:55:00_bear"
        ]
        assert len(overlapping) == 1
        assert overlapping[0]["label"] == "CORRECT"  # validate's label, not compare's NOISE
        assert overlapping[0]["labelled_by"] == "validate"

    def test_unique_compare_labels_preserved(self, overlapping_labels):
        """Compare-mode labels with unique detection_ids are preserved."""
        labels_dir, compare_file = overlapping_labels
        labels = load_all_labels(validate_dir=labels_dir, compare_file=compare_file)

        # The compare-only label should be present
        compare_only = [
            l for l in labels
            if l["detection_id"] == "mss_5m_2025-10-20T08:30:00_bull"
        ]
        assert len(compare_only) == 1
        assert compare_only[0]["labelled_by"] == "compare"
        assert compare_only[0]["label"] == "BORDERLINE"

    def test_total_after_dedup(self, overlapping_labels):
        """Total = unique detection_ids across both sources."""
        labels_dir, compare_file = overlapping_labels
        labels = load_all_labels(validate_dir=labels_dir, compare_file=compare_file)
        # validate has 1, compare has 2 (1 overlapping) → 2 unique
        assert len(labels) == 2

    def test_no_duplicate_detection_ids(self, overlapping_labels):
        """No duplicate detection_ids in output."""
        labels_dir, compare_file = overlapping_labels
        labels = load_all_labels(validate_dir=labels_dir, compare_file=compare_file)
        ids = [l["detection_id"] for l in labels]
        assert len(ids) == len(set(ids))


# ── Summary Counts ────────────────────────────────────────────────────────────


class TestSummaryCounts:
    """Summary dict: total, per-label counts, per-primitive counts, per-source counts."""

    def test_total_count(self, validate_labels_dir, compare_labels_file):
        """Total in summary equals len(labels)."""
        labels = load_all_labels(
            validate_dir=validate_labels_dir,
            compare_file=compare_labels_file,
        )
        summary = compute_label_summary(labels)
        assert summary["total"] == len(labels)

    def test_per_label_counts(self, validate_labels_dir, compare_labels_file):
        """Per-label counts cover CORRECT, NOISE, BORDERLINE."""
        labels = load_all_labels(
            validate_dir=validate_labels_dir,
            compare_file=compare_labels_file,
        )
        summary = compute_label_summary(labels)
        assert "per_label" in summary
        assert all(k in summary["per_label"] for k in ("CORRECT", "NOISE", "BORDERLINE"))

    def test_per_label_sum_equals_total(self, validate_labels_dir, compare_labels_file):
        """Sum of per-label counts == total."""
        labels = load_all_labels(
            validate_dir=validate_labels_dir,
            compare_file=compare_labels_file,
        )
        summary = compute_label_summary(labels)
        per_label_sum = sum(summary["per_label"].values())
        assert per_label_sum == summary["total"]

    def test_per_primitive_counts(self, validate_labels_dir, compare_labels_file):
        """Per-primitive counts present."""
        labels = load_all_labels(
            validate_dir=validate_labels_dir,
            compare_file=compare_labels_file,
        )
        summary = compute_label_summary(labels)
        assert "per_primitive" in summary
        # We have displacement, mss, order_block in our fixtures
        assert "displacement" in summary["per_primitive"]

    def test_per_source_counts(self, validate_labels_dir, compare_labels_file):
        """Per-source counts present with 'validate' and 'compare' keys."""
        labels = load_all_labels(
            validate_dir=validate_labels_dir,
            compare_file=compare_labels_file,
        )
        summary = compute_label_summary(labels)
        assert "per_source" in summary
        assert "validate" in summary["per_source"]
        assert "compare" in summary["per_source"]

    def test_per_source_sum_equals_total(self, validate_labels_dir, compare_labels_file):
        """Sum of per-source counts == total."""
        labels = load_all_labels(
            validate_dir=validate_labels_dir,
            compare_file=compare_labels_file,
        )
        summary = compute_label_summary(labels)
        per_source_sum = sum(summary["per_source"].values())
        assert per_source_sum == summary["total"]

    def test_empty_labels_summary(self):
        """Empty label list produces valid summary with zero counts."""
        summary = compute_label_summary([])
        assert summary["total"] == 0
        assert summary["per_label"] == {"CORRECT": 0, "NOISE": 0, "BORDERLINE": 0}
        assert summary["per_primitive"] == {}
        assert summary["per_source"] == {}


# ── Edge Cases ────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Additional edge cases for robustness."""

    def test_malformed_json_file_skipped(self, tmp_path):
        """Malformed JSON files are skipped gracefully."""
        labels_dir = tmp_path / "labels"
        labels_dir.mkdir()
        (labels_dir / "bad.json").write_text("not valid json {{{")
        (labels_dir / "good.json").write_text(json.dumps([
            {
                "detection_id": "fvg_5m_2025-10-20T03:55:00_bull",
                "primitive": "fvg",
                "timeframe": "5m",
                "label": "CORRECT",
            },
        ]))
        labels = load_validate_labels(labels_dir)
        assert len(labels) == 1

    def test_non_json_files_ignored(self, tmp_path):
        """Non-.json files in labels dir are ignored."""
        labels_dir = tmp_path / "labels"
        labels_dir.mkdir()
        (labels_dir / "readme.txt").write_text("not a label file")
        (labels_dir / "labels.csv").write_text("id,label\nfoo,CORRECT")
        labels = load_validate_labels(labels_dir)
        assert labels == []

    def test_validate_only(self, validate_labels_dir):
        """load_all_labels works with validate-only (no compare file)."""
        labels = load_all_labels(validate_dir=validate_labels_dir, compare_file=None)
        assert len(labels) == 3
        for label in labels:
            assert label["labelled_by"] == "validate"

    def test_compare_only(self, compare_labels_file):
        """load_all_labels works with compare-only (no validate dir)."""
        labels = load_all_labels(validate_dir=None, compare_file=compare_labels_file)
        assert len(labels) == 2
        for label in labels:
            assert label["labelled_by"] == "compare"

    def test_label_missing_required_field_skipped(self, tmp_path):
        """Labels missing detection_id are skipped."""
        labels_dir = tmp_path / "labels"
        labels_dir.mkdir()
        labels = [
            {
                # Missing detection_id
                "primitive": "displacement",
                "timeframe": "5m",
                "label": "CORRECT",
            },
            {
                "detection_id": "fvg_5m_2025-10-20T03:55:00_bull",
                "primitive": "fvg",
                "timeframe": "5m",
                "label": "NOISE",
            },
        ]
        (labels_dir / "week.json").write_text(json.dumps(labels))
        result = load_validate_labels(labels_dir)
        assert len(result) == 1
        assert result[0]["detection_id"] == "fvg_5m_2025-10-20T03:55:00_bull"

    def test_non_array_json_file_skipped(self, tmp_path):
        """JSON files that are objects (not arrays) are skipped."""
        labels_dir = tmp_path / "labels"
        labels_dir.mkdir()
        (labels_dir / "obj.json").write_text(json.dumps({"not": "an array"}))
        labels = load_validate_labels(labels_dir)
        assert labels == []
