"""Tests for fitness scoring module (src/ra/evaluation/fitness.py).

TDD tests covering:
  VAL-FIT-001: Precision + recall against ground truth — fitness score
               combines P and R. Higher P+R = higher fitness.
  VAL-FIT-002: Walk-forward stability on top candidates — top N candidates
               (configurable, default 3) undergo walk-forward validation.
               Candidates flagged UNSTABLE are demoted in ranking.
  VAL-FIT-003: Improvement tracking — candidates improving on baseline
               marked 'kept', others 'discarded' with score recorded.
  VAL-PROV-001: Every iteration recorded — config tested, score, delta,
                kept/discarded, iteration number.
  VAL-PROV-002: Machine-readable JSON output — valid JSON parseable by
                standard tools, consistent schema.
  VAL-PROV-003: Human-readable summary — total iterations, best score,
                improvement from baseline, top 3 candidates.

Edge cases: null P/R, zero baseline, empty candidates, all discarded,
all kept, single candidate, walk-forward on zero candidates.
"""

import json
from typing import Any

import pytest

from ra.evaluation.fitness import (
    compute_fitness,
    evaluate_candidate,
    rank_candidates,
)


# ── VAL-FIT-001: Fitness = f(precision, recall) ──────────────────────────────


class TestComputeFitness:
    """VAL-FIT-001: Fitness combines precision and recall. Higher P+R = higher."""

    def test_fitness_sum_of_precision_and_recall(self):
        """Fitness = precision + recall."""
        assert compute_fitness(0.8, 0.9) == pytest.approx(1.7)

    def test_fitness_perfect_is_2(self):
        """Perfect precision and recall → fitness 2.0."""
        assert compute_fitness(1.0, 1.0) == pytest.approx(2.0)

    def test_fitness_zero_is_0(self):
        """Zero precision and recall → fitness 0.0."""
        assert compute_fitness(0.0, 0.0) == pytest.approx(0.0)

    def test_fitness_null_precision(self):
        """Null precision treated as 0."""
        assert compute_fitness(None, 0.7) == pytest.approx(0.7)

    def test_fitness_null_recall(self):
        """Null recall treated as 0."""
        assert compute_fitness(0.6, None) == pytest.approx(0.6)

    def test_fitness_both_null(self):
        """Both null → 0.0."""
        assert compute_fitness(None, None) == pytest.approx(0.0)

    def test_higher_pr_higher_fitness(self):
        """Higher P+R always produces higher fitness."""
        low = compute_fitness(0.5, 0.5)  # 1.0
        high = compute_fitness(0.9, 0.8)  # 1.7
        assert high > low

    def test_fitness_range(self):
        """Fitness is in [0.0, 2.0] for valid inputs."""
        for p in [0.0, 0.25, 0.5, 0.75, 1.0]:
            for r in [0.0, 0.25, 0.5, 0.75, 1.0]:
                f = compute_fitness(p, r)
                assert 0.0 <= f <= 2.0, f"p={p}, r={r}, fitness={f}"


# ── VAL-FIT-003: Improvement tracking (kept/discarded) ──────────────────────


class TestEvaluateCandidate:
    """VAL-FIT-003: Candidates improving on baseline marked 'kept', others 'discarded'."""

    def _make_scoring_result(
        self, precision: float = 0.8, recall: float = 0.9
    ) -> dict[str, Any]:
        """Create a minimal Schema 4F scoring result."""
        return {
            "aggregate": {
                "precision": precision,
                "recall": recall,
                "f1": (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0,
                "total_labels": 10,
            }
        }

    def test_kept_when_above_baseline(self):
        """Score above baseline → kept=True."""
        scoring = self._make_scoring_result(0.9, 0.9)  # fitness = 1.8
        result = evaluate_candidate(scoring, baseline_score=1.0)
        assert result["kept"] is True
        assert result["score"] == pytest.approx(1.8)
        assert result["delta_from_baseline"] > 0

    def test_discarded_when_below_baseline(self):
        """Score below baseline → kept=False (discarded)."""
        scoring = self._make_scoring_result(0.3, 0.2)  # fitness = 0.5
        result = evaluate_candidate(scoring, baseline_score=1.0)
        assert result["kept"] is False
        assert result["delta_from_baseline"] < 0

    def test_discarded_when_equal_to_baseline(self):
        """Score equal to baseline → kept=False (must strictly improve)."""
        scoring = self._make_scoring_result(0.5, 0.5)  # fitness = 1.0
        result = evaluate_candidate(scoring, baseline_score=1.0)
        assert result["kept"] is False
        assert result["delta_from_baseline"] == pytest.approx(0.0)

    def test_evaluate_returns_required_fields(self):
        """Returned dict has score, precision, recall, delta_from_baseline, kept."""
        scoring = self._make_scoring_result(0.7, 0.8)
        result = evaluate_candidate(scoring, baseline_score=1.0)
        assert "score" in result
        assert "precision" in result
        assert "recall" in result
        assert "delta_from_baseline" in result
        assert "kept" in result

    def test_evaluate_with_null_precision(self):
        """Null precision in scoring → fitness uses 0."""
        scoring = {"aggregate": {"precision": None, "recall": 0.5}}
        result = evaluate_candidate(scoring, baseline_score=0.3)
        assert result["score"] == pytest.approx(0.5)
        assert result["kept"] is True

    def test_evaluate_with_zero_baseline(self):
        """Zero baseline → any positive score is an improvement."""
        scoring = self._make_scoring_result(0.1, 0.1)  # fitness = 0.2
        result = evaluate_candidate(scoring, baseline_score=0.0)
        assert result["kept"] is True
        assert result["delta_from_baseline"] == pytest.approx(0.2)


# ── rank_candidates ──────────────────────────────────────────────────────────


class TestRankCandidates:
    """Tests for rank_candidates sorting and ranking."""

    def test_sorted_by_score_descending(self):
        """Candidates sorted by score descending."""
        candidates = [
            {"score": 0.5, "iteration": 1, "kept": False},
            {"score": 1.5, "iteration": 2, "kept": True},
            {"score": 1.0, "iteration": 3, "kept": True},
        ]
        ranked = rank_candidates(candidates)
        scores = [c["score"] for c in ranked]
        assert scores == [1.5, 1.0, 0.5]

    def test_ranks_are_1_indexed(self):
        """Ranks are 1, 2, 3, ..."""
        candidates = [
            {"score": 1.5, "iteration": 1},
            {"score": 0.5, "iteration": 2},
            {"score": 1.0, "iteration": 3},
        ]
        ranked = rank_candidates(candidates)
        ranks = [c["rank"] for c in ranked]
        assert ranks == [1, 2, 3]

    def test_empty_candidates(self):
        """Empty input returns empty output."""
        assert rank_candidates([]) == []

    def test_single_candidate(self):
        """Single candidate gets rank 1."""
        candidates = [{"score": 1.0, "iteration": 1}]
        ranked = rank_candidates(candidates)
        assert ranked[0]["rank"] == 1


# ── VAL-FIT-002: Walk-forward stability on top candidates ────────────────────


class TestWalkForwardStability:
    """VAL-FIT-002: Walk-forward on top N candidates. UNSTABLE demoted."""

    def test_import_walk_forward_stability(self):
        """walk_forward_stability_check is importable."""
        from ra.evaluation.fitness import walk_forward_stability_check
        assert callable(walk_forward_stability_check)

    def test_top_n_default_is_3(self):
        """Default top_n parameter is 3."""
        from ra.evaluation.fitness import walk_forward_stability_check
        import inspect
        sig = inspect.signature(walk_forward_stability_check)
        assert sig.parameters["top_n"].default == 3

    def test_stable_candidates_retain_rank(self):
        """Candidates with STABLE walk-forward keep their rank position."""
        from ra.evaluation.fitness import walk_forward_stability_check

        candidates = [
            {"score": 1.8, "iteration": 1, "rank": 1, "config": {"p": 1}},
            {"score": 1.5, "iteration": 2, "rank": 2, "config": {"p": 2}},
            {"score": 1.2, "iteration": 3, "rank": 3, "config": {"p": 3}},
        ]

        # Simulate walk-forward that returns all STABLE
        def mock_wf_runner(candidate_config):
            return {"summary": {"verdict": "STABLE"}}

        result = walk_forward_stability_check(
            candidates, wf_runner_fn=mock_wf_runner, top_n=3,
        )
        # All stable → ranks preserved
        for c in result:
            assert c.get("walk_forward_verdict") == "STABLE"
            assert c.get("walk_forward_demoted") is False

    def test_unstable_candidate_demoted(self):
        """UNSTABLE candidate is demoted in ranking."""
        from ra.evaluation.fitness import walk_forward_stability_check

        candidates = [
            {"score": 1.8, "iteration": 1, "rank": 1, "config": {"p": 1}},
            {"score": 1.5, "iteration": 2, "rank": 2, "config": {"p": 2}},
            {"score": 1.2, "iteration": 3, "rank": 3, "config": {"p": 3}},
        ]

        def mock_wf_runner(candidate_config):
            # First candidate is unstable, others stable
            if candidate_config == {"p": 1}:
                return {"summary": {"verdict": "UNSTABLE"}}
            return {"summary": {"verdict": "STABLE"}}

        result = walk_forward_stability_check(
            candidates, wf_runner_fn=mock_wf_runner, top_n=3,
        )

        # The unstable candidate should be demoted (rank > original rank)
        unstable = [c for c in result if c["iteration"] == 1][0]
        assert unstable["walk_forward_verdict"] == "UNSTABLE"
        assert unstable["walk_forward_demoted"] is True

        # Stable candidates should be ranked above unstable ones
        stable_ranks = [
            c["rank"] for c in result if c["walk_forward_verdict"] == "STABLE"
        ]
        unstable_rank = unstable["rank"]
        for sr in stable_ranks:
            assert sr < unstable_rank

    def test_only_top_n_checked(self):
        """Only top N candidates undergo walk-forward check."""
        from ra.evaluation.fitness import walk_forward_stability_check

        call_count = 0

        def counting_wf_runner(candidate_config):
            nonlocal call_count
            call_count += 1
            return {"summary": {"verdict": "STABLE"}}

        candidates = [
            {"score": 1.8, "iteration": 1, "rank": 1, "config": {"p": 1}},
            {"score": 1.5, "iteration": 2, "rank": 2, "config": {"p": 2}},
            {"score": 1.2, "iteration": 3, "rank": 3, "config": {"p": 3}},
            {"score": 0.9, "iteration": 4, "rank": 4, "config": {"p": 4}},
            {"score": 0.6, "iteration": 5, "rank": 5, "config": {"p": 5}},
        ]

        walk_forward_stability_check(
            candidates, wf_runner_fn=counting_wf_runner, top_n=2,
        )
        assert call_count == 2

    def test_conditionally_stable_not_demoted(self):
        """CONDITIONALLY_STABLE candidates are NOT demoted."""
        from ra.evaluation.fitness import walk_forward_stability_check

        candidates = [
            {"score": 1.8, "iteration": 1, "rank": 1, "config": {"p": 1}},
        ]

        def mock_wf_runner(candidate_config):
            return {"summary": {"verdict": "CONDITIONALLY_STABLE"}}

        result = walk_forward_stability_check(
            candidates, wf_runner_fn=mock_wf_runner, top_n=1,
        )
        assert result[0]["walk_forward_verdict"] == "CONDITIONALLY_STABLE"
        assert result[0]["walk_forward_demoted"] is False

    def test_zero_candidates_no_error(self):
        """Empty candidate list doesn't crash."""
        from ra.evaluation.fitness import walk_forward_stability_check

        result = walk_forward_stability_check(
            [], wf_runner_fn=lambda c: {"summary": {"verdict": "STABLE"}}, top_n=3,
        )
        assert result == []

    def test_fewer_candidates_than_top_n(self):
        """When fewer candidates than top_n, check all available."""
        from ra.evaluation.fitness import walk_forward_stability_check

        call_count = 0

        def counting_wf_runner(candidate_config):
            nonlocal call_count
            call_count += 1
            return {"summary": {"verdict": "STABLE"}}

        candidates = [
            {"score": 1.8, "iteration": 1, "rank": 1, "config": {"p": 1}},
        ]

        walk_forward_stability_check(
            candidates, wf_runner_fn=counting_wf_runner, top_n=5,
        )
        assert call_count == 1

    def test_walk_forward_result_stored(self):
        """Walk-forward result is stored in candidate dict."""
        from ra.evaluation.fitness import walk_forward_stability_check

        candidates = [
            {"score": 1.8, "iteration": 1, "rank": 1, "config": {"p": 1}},
        ]

        def mock_wf_runner(candidate_config):
            return {
                "summary": {"verdict": "STABLE", "windows_passed": 5, "windows_failed": 0},
            }

        result = walk_forward_stability_check(
            candidates, wf_runner_fn=mock_wf_runner, top_n=1,
        )
        assert "walk_forward_result" in result[0]
        assert result[0]["walk_forward_result"]["summary"]["verdict"] == "STABLE"

    def test_unchecked_candidates_no_wf_fields(self):
        """Candidates below top_n cutoff don't get walk_forward fields."""
        from ra.evaluation.fitness import walk_forward_stability_check

        candidates = [
            {"score": 1.8, "iteration": 1, "rank": 1, "config": {"p": 1}},
            {"score": 0.5, "iteration": 2, "rank": 2, "config": {"p": 2}},
        ]

        def mock_wf_runner(candidate_config):
            return {"summary": {"verdict": "STABLE"}}

        result = walk_forward_stability_check(
            candidates, wf_runner_fn=mock_wf_runner, top_n=1,
        )
        unchecked = [c for c in result if c["iteration"] == 2][0]
        assert unchecked.get("walk_forward_verdict") is None
        assert unchecked.get("walk_forward_demoted") is None


# ── VAL-PROV-001: Every iteration recorded ──────────────────────────────────


class TestProvenanceRecording:
    """VAL-PROV-001: Each iteration stored with config, score, delta, kept/discarded, iteration."""

    def test_import_build_provenance(self):
        """build_provenance function is importable."""
        from ra.evaluation.fitness import build_provenance
        assert callable(build_provenance)

    def test_provenance_has_all_fields_per_iteration(self):
        """Every iteration has: config, score, delta, kept/discarded, iteration number."""
        from ra.evaluation.fitness import build_provenance

        candidates = [
            {
                "iteration": 1,
                "config": {"displacement.ltf.atr_multiplier": 1.75},
                "score": 1.5,
                "delta_from_baseline": 0.3,
                "kept": True,
                "rank": 1,
            },
            {
                "iteration": 2,
                "config": {"displacement.ltf.atr_multiplier": 1.25},
                "score": 0.8,
                "delta_from_baseline": -0.4,
                "kept": False,
                "rank": 2,
            },
        ]

        metadata = {
            "baseline_score": 1.2,
            "iterations_requested": 2,
            "iterations_completed": 2,
        }

        provenance = build_provenance(candidates, metadata)

        assert "iterations" in provenance
        for iteration in provenance["iterations"]:
            assert "iteration" in iteration
            assert "config" in iteration
            assert "score" in iteration
            assert "delta_from_baseline" in iteration
            assert "kept" in iteration

    def test_provenance_iterations_match_candidates(self):
        """Number of provenance iterations matches number of candidates."""
        from ra.evaluation.fitness import build_provenance

        candidates = [
            {"iteration": i, "config": {}, "score": float(i),
             "delta_from_baseline": 0.0, "kept": True, "rank": i}
            for i in range(1, 6)
        ]

        provenance = build_provenance(candidates, {"baseline_score": 0.5,
                                                    "iterations_requested": 5,
                                                    "iterations_completed": 5})
        assert len(provenance["iterations"]) == 5

    def test_provenance_preserves_iteration_order(self):
        """Iterations are ordered by iteration number (not rank)."""
        from ra.evaluation.fitness import build_provenance

        candidates = [
            {"iteration": 3, "config": {"a": 3}, "score": 1.0,
             "delta_from_baseline": 0.0, "kept": True, "rank": 1},
            {"iteration": 1, "config": {"a": 1}, "score": 0.5,
             "delta_from_baseline": -0.5, "kept": False, "rank": 3},
            {"iteration": 2, "config": {"a": 2}, "score": 0.8,
             "delta_from_baseline": -0.2, "kept": False, "rank": 2},
        ]

        provenance = build_provenance(candidates, {"baseline_score": 1.0,
                                                    "iterations_requested": 3,
                                                    "iterations_completed": 3})
        iter_nums = [it["iteration"] for it in provenance["iterations"]]
        assert iter_nums == [1, 2, 3]

    def test_provenance_has_metadata(self):
        """Provenance includes baseline_score, iterations_requested, etc."""
        from ra.evaluation.fitness import build_provenance

        candidates = [
            {"iteration": 1, "config": {}, "score": 1.0,
             "delta_from_baseline": 0.1, "kept": True, "rank": 1},
        ]

        metadata = {
            "baseline_score": 0.9,
            "iterations_requested": 10,
            "iterations_completed": 1,
            "seed": 42,
        }

        provenance = build_provenance(candidates, metadata)
        assert provenance["baseline_score"] == 0.9
        assert provenance["iterations_requested"] == 10
        assert provenance["iterations_completed"] == 1


# ── VAL-PROV-002: Machine-readable JSON output ──────────────────────────────


class TestProvenanceJSON:
    """VAL-PROV-002: Output is valid JSON parseable by standard tools."""

    def test_import_format_provenance_json(self):
        """format_provenance_json is importable."""
        from ra.evaluation.fitness import format_provenance_json
        assert callable(format_provenance_json)

    def test_json_valid(self):
        """Output is valid JSON that can be parsed by json.loads()."""
        from ra.evaluation.fitness import build_provenance, format_provenance_json

        candidates = [
            {"iteration": 1, "config": {"p": 1.5}, "score": 1.2,
             "delta_from_baseline": 0.1, "kept": True, "rank": 1},
        ]
        metadata = {"baseline_score": 1.1, "iterations_requested": 1,
                     "iterations_completed": 1}

        provenance = build_provenance(candidates, metadata)
        json_str = format_provenance_json(provenance)

        # Must not raise
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)

    def test_json_schema_consistent(self):
        """JSON output has consistent structure: schema_version, metadata,
        iterations, ranked_candidates, summary."""
        from ra.evaluation.fitness import build_provenance, format_provenance_json

        candidates = [
            {"iteration": 1, "config": {"p": 1.5}, "score": 1.2,
             "delta_from_baseline": 0.1, "kept": True, "rank": 1},
            {"iteration": 2, "config": {"p": 2.0}, "score": 0.8,
             "delta_from_baseline": -0.3, "kept": False, "rank": 2},
        ]
        metadata = {"baseline_score": 1.1, "iterations_requested": 2,
                     "iterations_completed": 2}

        provenance = build_provenance(candidates, metadata)
        json_str = format_provenance_json(provenance)
        parsed = json.loads(json_str)

        assert "schema_version" in parsed
        assert "iterations" in parsed
        assert "ranked_candidates" in parsed
        assert "summary" in parsed

    def test_json_ranked_candidates_sorted(self):
        """ranked_candidates in JSON are sorted by rank."""
        from ra.evaluation.fitness import build_provenance, format_provenance_json

        candidates = [
            {"iteration": 1, "config": {"p": 1.5}, "score": 1.2,
             "delta_from_baseline": 0.1, "kept": True, "rank": 1},
            {"iteration": 2, "config": {"p": 2.0}, "score": 0.8,
             "delta_from_baseline": -0.3, "kept": False, "rank": 2},
        ]
        metadata = {"baseline_score": 1.1, "iterations_requested": 2,
                     "iterations_completed": 2}

        provenance = build_provenance(candidates, metadata)
        json_str = format_provenance_json(provenance)
        parsed = json.loads(json_str)

        ranks = [c["rank"] for c in parsed["ranked_candidates"]]
        assert ranks == sorted(ranks)


# ── VAL-PROV-003: Human-readable summary ─────────────────────────────────────


class TestHumanReadableSummary:
    """VAL-PROV-003: Summary text: total iterations, best score, improvement, top 3."""

    def test_import_format_summary(self):
        """format_summary is importable."""
        from ra.evaluation.fitness import format_summary
        assert callable(format_summary)

    def test_summary_contains_total_iterations(self):
        """Summary includes total iterations count."""
        from ra.evaluation.fitness import build_provenance, format_summary

        candidates = [
            {"iteration": 1, "config": {}, "score": 1.0,
             "delta_from_baseline": 0.1, "kept": True, "rank": 1},
            {"iteration": 2, "config": {}, "score": 0.8,
             "delta_from_baseline": -0.1, "kept": False, "rank": 2},
        ]
        metadata = {"baseline_score": 0.9, "iterations_requested": 2,
                     "iterations_completed": 2}
        provenance = build_provenance(candidates, metadata)
        summary = format_summary(provenance)

        assert "2" in summary  # iterations count

    def test_summary_contains_best_score(self):
        """Summary includes best score value."""
        from ra.evaluation.fitness import build_provenance, format_summary

        candidates = [
            {"iteration": 1, "config": {}, "score": 1.5,
             "delta_from_baseline": 0.5, "kept": True, "rank": 1},
        ]
        metadata = {"baseline_score": 1.0, "iterations_requested": 1,
                     "iterations_completed": 1}
        provenance = build_provenance(candidates, metadata)
        summary = format_summary(provenance)

        assert "1.5" in summary

    def test_summary_contains_improvement(self):
        """Summary includes improvement from baseline."""
        from ra.evaluation.fitness import build_provenance, format_summary

        candidates = [
            {"iteration": 1, "config": {"p": 1}, "score": 1.5,
             "delta_from_baseline": 0.5, "kept": True, "rank": 1},
        ]
        metadata = {"baseline_score": 1.0, "iterations_requested": 1,
                     "iterations_completed": 1}
        provenance = build_provenance(candidates, metadata)
        summary = format_summary(provenance)

        # Should contain improvement info (either "+0.5" or "0.5" or "50%")
        assert "0.5" in summary or "improvement" in summary.lower()

    def test_summary_contains_top_3(self):
        """Summary includes top 3 candidates info."""
        from ra.evaluation.fitness import build_provenance, format_summary

        candidates = [
            {"iteration": 1, "config": {"p": 1}, "score": 1.8,
             "delta_from_baseline": 0.8, "kept": True, "rank": 1},
            {"iteration": 2, "config": {"p": 2}, "score": 1.5,
             "delta_from_baseline": 0.5, "kept": True, "rank": 2},
            {"iteration": 3, "config": {"p": 3}, "score": 1.2,
             "delta_from_baseline": 0.2, "kept": True, "rank": 3},
            {"iteration": 4, "config": {"p": 4}, "score": 0.5,
             "delta_from_baseline": -0.5, "kept": False, "rank": 4},
        ]
        metadata = {"baseline_score": 1.0, "iterations_requested": 4,
                     "iterations_completed": 4}
        provenance = build_provenance(candidates, metadata)
        summary = format_summary(provenance)

        # Should mention top 3 with their scores
        assert "1.8" in summary
        assert "1.5" in summary
        assert "1.2" in summary
        # Should mention "top" or "#1", "#2", "#3"
        assert "top" in summary.lower() or "#1" in summary

    def test_summary_with_fewer_than_3_candidates(self):
        """Summary works with fewer than 3 candidates."""
        from ra.evaluation.fitness import build_provenance, format_summary

        candidates = [
            {"iteration": 1, "config": {}, "score": 1.2,
             "delta_from_baseline": 0.2, "kept": True, "rank": 1},
        ]
        metadata = {"baseline_score": 1.0, "iterations_requested": 1,
                     "iterations_completed": 1}
        provenance = build_provenance(candidates, metadata)
        summary = format_summary(provenance)

        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_summary_with_zero_candidates(self):
        """Summary handles zero candidates gracefully."""
        from ra.evaluation.fitness import build_provenance, format_summary

        provenance = build_provenance(
            [], {"baseline_score": 1.0, "iterations_requested": 0,
                 "iterations_completed": 0}
        )
        summary = format_summary(provenance)
        assert isinstance(summary, str)

    def test_summary_is_string(self):
        """Summary returns a string (not dict)."""
        from ra.evaluation.fitness import build_provenance, format_summary

        candidates = [
            {"iteration": 1, "config": {}, "score": 1.0,
             "delta_from_baseline": 0.0, "kept": False, "rank": 1},
        ]
        metadata = {"baseline_score": 1.0, "iterations_requested": 1,
                     "iterations_completed": 1}
        provenance = build_provenance(candidates, metadata)
        summary = format_summary(provenance)
        assert isinstance(summary, str)


# ── Integration: full fitness pipeline ────────────────────────────────────────


class TestFitnessPipeline:
    """Integration tests for the full fitness pipeline."""

    def test_end_to_end_scoring_and_provenance(self):
        """compute_fitness → evaluate_candidate → rank → provenance → JSON."""
        from ra.evaluation.fitness import (
            build_provenance,
            format_provenance_json,
            format_summary,
        )

        baseline_score = 1.0
        candidates = []

        # Simulate 5 iterations
        test_data = [
            (0.8, 0.9, 1),  # fitness=1.7, kept
            (0.3, 0.4, 2),  # fitness=0.7, discarded
            (0.6, 0.6, 3),  # fitness=1.2, kept
            (0.9, 0.95, 4), # fitness=1.85, kept
            (0.2, 0.3, 5),  # fitness=0.5, discarded
        ]

        for p, r, i in test_data:
            scoring = {
                "aggregate": {"precision": p, "recall": r, "f1": None, "total_labels": 10}
            }
            result = evaluate_candidate(scoring, baseline_score)
            result["iteration"] = i
            result["config"] = {"precision_tweak": p}
            candidates.append(result)

        # Rank candidates
        ranked = rank_candidates(candidates)

        # Build provenance
        metadata = {
            "baseline_score": baseline_score,
            "iterations_requested": 5,
            "iterations_completed": 5,
        }
        provenance = build_provenance(ranked, metadata)

        # JSON output
        json_str = format_provenance_json(provenance)
        parsed = json.loads(json_str)
        assert len(parsed["iterations"]) == 5
        assert len(parsed["ranked_candidates"]) == 5

        # Summary
        summary = format_summary(provenance)
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_all_discarded_candidates(self):
        """All candidates below baseline — all discarded."""
        from ra.evaluation.fitness import build_provenance, format_summary

        candidates = [
            {"iteration": 1, "config": {}, "score": 0.5,
             "delta_from_baseline": -0.5, "kept": False, "rank": 1},
            {"iteration": 2, "config": {}, "score": 0.3,
             "delta_from_baseline": -0.7, "kept": False, "rank": 2},
        ]
        metadata = {"baseline_score": 1.0, "iterations_requested": 2,
                     "iterations_completed": 2}
        provenance = build_provenance(candidates, metadata)
        summary = format_summary(provenance)
        assert isinstance(summary, str)

    def test_walk_forward_with_demotion_in_json(self):
        """Walk-forward stability info appears in JSON output."""
        from ra.evaluation.fitness import (
            walk_forward_stability_check,
            build_provenance,
            format_provenance_json,
        )

        candidates = [
            {"score": 1.8, "iteration": 1, "rank": 1, "config": {"p": 1},
             "delta_from_baseline": 0.8, "kept": True},
            {"score": 1.5, "iteration": 2, "rank": 2, "config": {"p": 2},
             "delta_from_baseline": 0.5, "kept": True},
        ]

        def mock_wf_runner(candidate_config):
            if candidate_config == {"p": 1}:
                return {"summary": {"verdict": "UNSTABLE"}}
            return {"summary": {"verdict": "STABLE"}}

        checked = walk_forward_stability_check(
            candidates, wf_runner_fn=mock_wf_runner, top_n=2,
        )

        metadata = {"baseline_score": 1.0, "iterations_requested": 2,
                     "iterations_completed": 2}
        provenance = build_provenance(checked, metadata)
        json_str = format_provenance_json(provenance)
        parsed = json.loads(json_str)

        # Find the demoted candidate in ranked_candidates
        ranked = parsed["ranked_candidates"]
        unstable_entry = [c for c in ranked if c.get("walk_forward_verdict") == "UNSTABLE"]
        assert len(unstable_entry) == 1
        assert unstable_entry[0]["walk_forward_demoted"] is True
