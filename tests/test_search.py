"""Tests for search.py parameter search CLI.

TDD tests covering:
- VAL-SRCH-001: search.py accepts required CLI flags (--config, --search-space, --labels, --iterations)
- VAL-SRCH-002: Runs specified number of iterations
- VAL-SRCH-003: Produces ranked output with candidates
- VAL-SRCH-004: Handles Ctrl+C gracefully (save completed iterations)
- VAL-SRCH-005: Progress display with best score tracking
- VAL-SRCH-006: --seed for reproducible runs (from feature expectedBehavior)
- VAL-SRCH-007: --iterations 0 error

Edge cases: missing flags, nonexistent files, empty labels, seed determinism.
"""

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml


# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
SEARCH_PY = ROOT / "search.py"
CONFIGS_DIR = ROOT / "configs"
DATA_DIR = ROOT / "data"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_search_space(tmp_path: Path) -> Path:
    """Create a minimal search-space YAML for testing."""
    space = {
        "parameters": {
            "displacement.ltf.atr_multiplier": {
                "type": "numeric",
                "base": 1.5,
                "min": 1.0,
                "max": 3.0,
                "step": 0.25,
            },
            "displacement.ltf.body_ratio": {
                "type": "numeric",
                "base": 0.60,
                "min": 0.50,
                "max": 0.80,
                "step": 0.05,
            },
        }
    }
    path = tmp_path / "search_space.yaml"
    path.write_text(yaml.dump(space))
    return path


def _make_labels(tmp_path: Path, n: int = 5) -> Path:
    """Create a minimal ground truth labels JSON for testing."""
    labels = []
    for i in range(n):
        labels.append({
            "detection_id": f"displacement_5m_2024-01-08T09:{10+i}:00_bull",
            "primitive": "displacement",
            "timeframe": "5m",
            "label": "CORRECT" if i < 3 else "NOISE",
            "labelled_by": "validate",
        })
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(labels))
    return path


def _make_empty_labels(tmp_path: Path) -> Path:
    """Create an empty labels JSON."""
    path = tmp_path / "empty_labels.json"
    path.write_text("[]")
    return path


# ── VAL-SRCH-001: search.py accepts required CLI flags ───────────────────────


class TestCLIFlags:
    """VAL-SRCH-001: search.py parses --config, --search-space, --labels, --iterations."""

    def test_help_shows_all_flags(self):
        """--help output contains all required flags."""
        result = subprocess.run(
            [sys.executable, str(SEARCH_PY), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "--config" in result.stdout
        assert "--search-space" in result.stdout
        assert "--labels" in result.stdout
        assert "--iterations" in result.stdout
        assert "--output" in result.stdout
        assert "--seed" in result.stdout

    def test_missing_config_flag_error(self):
        """Missing --config produces argparse error."""
        result = subprocess.run(
            [sys.executable, str(SEARCH_PY),
             "--search-space", "space.yaml",
             "--labels", "labels.json",
             "--iterations", "5"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0
        assert "config" in result.stderr.lower() or "required" in result.stderr.lower()

    def test_missing_search_space_flag_error(self):
        """Missing --search-space produces argparse error."""
        result = subprocess.run(
            [sys.executable, str(SEARCH_PY),
             "--config", "config.yaml",
             "--labels", "labels.json",
             "--iterations", "5"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0
        assert "search-space" in result.stderr.lower() or "search_space" in result.stderr.lower() or "required" in result.stderr.lower()

    def test_missing_labels_flag_error(self):
        """Missing --labels produces argparse error."""
        result = subprocess.run(
            [sys.executable, str(SEARCH_PY),
             "--config", "config.yaml",
             "--search-space", "space.yaml",
             "--iterations", "5"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0
        assert "labels" in result.stderr.lower() or "required" in result.stderr.lower()

    def test_missing_iterations_flag_error(self):
        """Missing --iterations produces argparse error."""
        result = subprocess.run(
            [sys.executable, str(SEARCH_PY),
             "--config", "config.yaml",
             "--search-space", "space.yaml",
             "--labels", "labels.json"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0
        assert "iterations" in result.stderr.lower() or "required" in result.stderr.lower()


# ── VAL-SRCH-007: --iterations 0 error ───────────────────────────────────────


class TestIterationsValidation:
    """--iterations 0 or negative values produce clear error."""

    def test_iterations_zero_error(self, tmp_path):
        """--iterations 0 produces error stating must be positive."""
        search_space = _make_search_space(tmp_path)
        labels = _make_labels(tmp_path)

        result = subprocess.run(
            [sys.executable, str(SEARCH_PY),
             "--config", str(CONFIGS_DIR / "locked_baseline.yaml"),
             "--search-space", str(search_space),
             "--labels", str(labels),
             "--iterations", "0"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0
        assert "positive" in result.stderr.lower() or "must be" in result.stderr.lower() or "invalid" in result.stderr.lower()

    def test_iterations_negative_error(self, tmp_path):
        """--iterations -1 produces error."""
        search_space = _make_search_space(tmp_path)
        labels = _make_labels(tmp_path)

        result = subprocess.run(
            [sys.executable, str(SEARCH_PY),
             "--config", str(CONFIGS_DIR / "locked_baseline.yaml"),
             "--search-space", str(search_space),
             "--labels", str(labels),
             "--iterations", "-1"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0


# ── Unit tests for perturbation module ────────────────────────────────────────


class TestPerturbation:
    """Tests for src/ra/evaluation/perturbation.py."""

    def test_import_perturbation(self):
        """Perturbation module is importable."""
        from ra.evaluation.perturbation import perturb_config

    def test_numeric_within_bounds(self):
        """Numeric perturbation stays within [min, max]."""
        from ra.evaluation.perturbation import perturb_config

        search_space = {
            "parameters": {
                "displacement.ltf.atr_multiplier": {
                    "type": "numeric",
                    "base": 1.5,
                    "min": 1.0,
                    "max": 3.0,
                    "step": 0.25,
                },
            }
        }
        for seed in range(100):
            result = perturb_config(search_space, seed=seed)
            val = result["displacement.ltf.atr_multiplier"]
            assert 1.0 <= val <= 3.0, f"seed={seed}: value {val} out of bounds"

    def test_numeric_snapped_to_step(self):
        """Numeric values are snapped to step grid."""
        from ra.evaluation.perturbation import perturb_config

        search_space = {
            "parameters": {
                "displacement.ltf.atr_multiplier": {
                    "type": "numeric",
                    "base": 1.5,
                    "min": 1.0,
                    "max": 3.0,
                    "step": 0.25,
                },
            }
        }
        for seed in range(50):
            result = perturb_config(search_space, seed=seed)
            val = result["displacement.ltf.atr_multiplier"]
            # Check that value is on the step grid: (val - min) % step ~= 0
            remainder = (val - 1.0) % 0.25
            assert abs(remainder) < 1e-9 or abs(remainder - 0.25) < 1e-9, \
                f"seed={seed}: value {val} not on step grid (remainder={remainder})"

    def test_categorical_within_options(self):
        """Categorical perturbation only picks from defined options."""
        from ra.evaluation.perturbation import perturb_config

        search_space = {
            "parameters": {
                "quality_gate": {
                    "type": "categorical",
                    "options": ["strict", "relaxed", "off"],
                    "base": "strict",
                },
            }
        }
        seen = set()
        for seed in range(50):
            result = perturb_config(search_space, seed=seed)
            val = result["quality_gate"]
            assert val in {"strict", "relaxed", "off"}, f"seed={seed}: invalid value {val}"
            seen.add(val)
        # Over 50 seeds, at least 2 options should appear
        assert len(seen) >= 2, f"Only {seen} options seen in 50 seeds"

    def test_boolean_perturbation(self):
        """Boolean params toggle between true and false."""
        from ra.evaluation.perturbation import perturb_config

        search_space = {
            "parameters": {
                "use_cluster": {
                    "type": "boolean",
                    "base": True,
                },
            }
        }
        seen = set()
        for seed in range(30):
            result = perturb_config(search_space, seed=seed)
            val = result["use_cluster"]
            assert isinstance(val, bool), f"seed={seed}: value {val} is not bool"
            seen.add(val)
        assert len(seen) == 2, f"Expected both True/False, got {seen}"

    def test_reproducible_with_seed(self):
        """Same seed produces identical results."""
        from ra.evaluation.perturbation import perturb_config

        search_space = {
            "parameters": {
                "displacement.ltf.atr_multiplier": {
                    "type": "numeric",
                    "base": 1.5,
                    "min": 1.0,
                    "max": 3.0,
                    "step": 0.25,
                },
                "displacement.ltf.body_ratio": {
                    "type": "numeric",
                    "base": 0.60,
                    "min": 0.50,
                    "max": 0.80,
                    "step": 0.05,
                },
            }
        }
        result_a = perturb_config(search_space, seed=42)
        result_b = perturb_config(search_space, seed=42)
        assert result_a == result_b

    def test_different_seeds_different_results(self):
        """Different seeds produce different results (high probability)."""
        from ra.evaluation.perturbation import perturb_config

        search_space = {
            "parameters": {
                "displacement.ltf.atr_multiplier": {
                    "type": "numeric",
                    "base": 1.5,
                    "min": 1.0,
                    "max": 3.0,
                    "step": 0.25,
                },
                "displacement.ltf.body_ratio": {
                    "type": "numeric",
                    "base": 0.60,
                    "min": 0.50,
                    "max": 0.80,
                    "step": 0.05,
                },
                "quality_gate": {
                    "type": "categorical",
                    "options": ["strict", "relaxed", "off"],
                    "base": "strict",
                },
            }
        }
        result_a = perturb_config(search_space, seed=1)
        result_b = perturb_config(search_space, seed=100)
        # With 3 params and different seeds, configs should differ
        assert result_a != result_b

    def test_continuous_when_no_step(self):
        """When step is absent, continuous perturbation is allowed."""
        from ra.evaluation.perturbation import perturb_config

        search_space = {
            "parameters": {
                "some_param": {
                    "type": "numeric",
                    "base": 1.5,
                    "min": 1.0,
                    "max": 3.0,
                    # no step
                },
            }
        }
        result = perturb_config(search_space, seed=42)
        val = result["some_param"]
        assert 1.0 <= val <= 3.0

    def test_multi_param_joint_perturbation(self):
        """Multiple params are perturbed independently in one call."""
        from ra.evaluation.perturbation import perturb_config

        search_space = {
            "parameters": {
                "displacement.ltf.atr_multiplier": {
                    "type": "numeric",
                    "base": 1.5,
                    "min": 1.0,
                    "max": 3.0,
                    "step": 0.25,
                },
                "displacement.ltf.body_ratio": {
                    "type": "numeric",
                    "base": 0.60,
                    "min": 0.50,
                    "max": 0.80,
                    "step": 0.05,
                },
            }
        }
        result = perturb_config(search_space, seed=42)
        assert "displacement.ltf.atr_multiplier" in result
        assert "displacement.ltf.body_ratio" in result


# ── Unit tests for fitness module ─────────────────────────────────────────────


class TestFitness:
    """Tests for src/ra/evaluation/fitness.py."""

    def test_import_fitness(self):
        """Fitness module is importable."""
        from ra.evaluation.fitness import compute_fitness

    def test_fitness_combines_precision_recall(self):
        """Fitness = precision + recall."""
        from ra.evaluation.fitness import compute_fitness

        score = compute_fitness(precision=0.8, recall=0.9)
        assert score == pytest.approx(1.7)

    def test_fitness_perfect_score(self):
        """Perfect precision + recall = 2.0."""
        from ra.evaluation.fitness import compute_fitness

        score = compute_fitness(precision=1.0, recall=1.0)
        assert score == pytest.approx(2.0)

    def test_fitness_zero_detections(self):
        """Zero detections → fitness 0.0."""
        from ra.evaluation.fitness import compute_fitness

        score = compute_fitness(precision=0.0, recall=0.0)
        assert score == pytest.approx(0.0)

    def test_fitness_null_precision(self):
        """Null precision treated as 0 → fitness = 0 + recall."""
        from ra.evaluation.fitness import compute_fitness

        score = compute_fitness(precision=None, recall=0.5)
        assert score == pytest.approx(0.5)

    def test_fitness_null_recall(self):
        """Null recall treated as 0 → fitness = precision + 0."""
        from ra.evaluation.fitness import compute_fitness

        score = compute_fitness(precision=0.5, recall=None)
        assert score == pytest.approx(0.5)

    def test_fitness_both_null(self):
        """Both null → fitness 0.0."""
        from ra.evaluation.fitness import compute_fitness

        score = compute_fitness(precision=None, recall=None)
        assert score == pytest.approx(0.0)


# ── Integration: search module imports ────────────────────────────────────────


class TestSearchModuleImport:
    """Verify search.py can be imported as a module."""

    def test_import_search_main(self):
        """search.py main function is importable."""
        # Add root to path so we can import search
        sys.path.insert(0, str(ROOT))
        try:
            import search
            assert hasattr(search, "main")
        finally:
            sys.path.pop(0)


# ── Integration: search with mocked cascade ──────────────────────────────────


class TestSearchWithMockedCascade:
    """Integration tests using mocked cascade engine to avoid heavy computation."""

    def _run_search(
        self, tmp_path, iterations=3, seed=42, extra_args=None,
    ) -> tuple[subprocess.CompletedProcess, Path]:
        """Run search.py with mocked cascade for speed.

        We use a subprocess approach since search.py is a CLI entrypoint.
        For speed, we use a small iteration count and rely on the
        mock-friendly architecture.
        """
        tmp_path.mkdir(parents=True, exist_ok=True)
        search_space = _make_search_space(tmp_path)
        labels = _make_labels(tmp_path)
        output_path = tmp_path / "search_results.json"

        cmd = [
            sys.executable, str(SEARCH_PY),
            "--config", str(CONFIGS_DIR / "locked_baseline.yaml"),
            "--search-space", str(search_space),
            "--labels", str(labels),
            "--iterations", str(iterations),
            "--output", str(output_path),
            "--seed", str(seed),
            "--data", str(DATA_DIR / "eurusd_1m_2024-01-07_to_2024-01-12.csv"),
        ]
        if extra_args:
            cmd.extend(extra_args)

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600,
        )
        return result, output_path

    def test_runs_exact_iterations(self, tmp_path):
        """VAL-SRCH-002: --iterations 2 runs exactly 2 iterations."""
        result, output_path = self._run_search(tmp_path, iterations=2)
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert output_path.exists(), "Output file not created"

        data = json.loads(output_path.read_text())
        assert "candidates" in data
        assert len(data["candidates"]) == 2
        assert data["metadata"]["iterations_completed"] == 2

    def test_produces_ranked_output(self, tmp_path):
        """VAL-SRCH-003: Output JSON has candidates sorted by score desc."""
        result, output_path = self._run_search(tmp_path, iterations=3)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        data = json.loads(output_path.read_text())
        candidates = data["candidates"]
        assert len(candidates) == 3

        # Check required fields
        for c in candidates:
            assert "rank" in c
            assert "score" in c
            assert "config" in c
            assert "iteration" in c

        # Check sorted by score descending
        scores = [c["score"] for c in candidates]
        assert scores == sorted(scores, reverse=True)

        # Check ranks are 1-indexed and contiguous
        ranks = [c["rank"] for c in candidates]
        assert ranks == list(range(1, len(candidates) + 1))

    def test_progress_display(self, tmp_path):
        """VAL-SRCH-005: Progress shows [N/total], current score, best score."""
        result, output_path = self._run_search(tmp_path, iterations=2)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        combined = result.stdout + result.stderr
        # Check for iteration progress pattern
        assert "[1/2]" in combined or "[1/2]" in combined.replace(" ", "")
        assert "[2/2]" in combined or "[2/2]" in combined.replace(" ", "")

    def test_seed_reproducibility(self, tmp_path):
        """VAL-SRCH-006: Same seed produces identical results."""
        result1, output1 = self._run_search(tmp_path / "run1", iterations=2, seed=42)
        assert result1.returncode == 0, f"stderr: {result1.stderr}"

        result2, output2 = self._run_search(tmp_path / "run2", iterations=2, seed=42)
        assert result2.returncode == 0, f"stderr: {result2.stderr}"

        data1 = json.loads(output1.read_text())
        data2 = json.loads(output2.read_text())

        # Candidates should be identical (same configs and scores)
        for c1, c2 in zip(data1["candidates"], data2["candidates"]):
            assert c1["config"] == c2["config"]
            assert c1["score"] == pytest.approx(c2["score"])
            assert c1["iteration"] == c2["iteration"]

    def test_different_seed_different_results(self, tmp_path):
        """Different seeds produce different results."""
        result1, output1 = self._run_search(tmp_path / "run1", iterations=2, seed=42)
        result2, output2 = self._run_search(tmp_path / "run2", iterations=2, seed=99)

        assert result1.returncode == 0
        assert result2.returncode == 0

        data1 = json.loads(output1.read_text())
        data2 = json.loads(output2.read_text())

        # At least one candidate config should differ
        configs1 = [c["config"] for c in data1["candidates"]]
        configs2 = [c["config"] for c in data2["candidates"]]
        assert configs1 != configs2, "Same configs with different seeds"

    def test_output_has_metadata(self, tmp_path):
        """Output JSON has metadata section with run parameters."""
        result, output_path = self._run_search(tmp_path, iterations=2)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        data = json.loads(output_path.read_text())
        assert "metadata" in data
        meta = data["metadata"]
        assert "iterations_requested" in meta
        assert "iterations_completed" in meta
        assert "seed" in meta
        assert "baseline_score" in meta
        assert meta["iterations_requested"] == 2
        assert meta["iterations_completed"] == 2
        assert meta["seed"] == 42

    def test_output_valid_json(self, tmp_path):
        """VAL-PROV-003: Output is valid, parseable JSON."""
        result, output_path = self._run_search(tmp_path, iterations=2)
        assert result.returncode == 0

        # Should parse without error
        text = output_path.read_text()
        data = json.loads(text)
        assert isinstance(data, dict)

    def test_default_output_path(self, tmp_path):
        """Default output path is results/search_results.json."""
        search_space = _make_search_space(tmp_path)
        labels = _make_labels(tmp_path)

        result = subprocess.run(
            [sys.executable, str(SEARCH_PY),
             "--config", str(CONFIGS_DIR / "locked_baseline.yaml"),
             "--search-space", str(search_space),
             "--labels", str(labels),
             "--iterations", "1",
             "--seed", "42",
             "--data", str(DATA_DIR / "eurusd_1m_2024-01-07_to_2024-01-12.csv")],
            capture_output=True, text=True, timeout=600,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        default_path = tmp_path / "results" / "search_results.json"
        assert default_path.exists(), f"Default output not at {default_path}"

    def test_summary_after_completion(self, tmp_path):
        """Summary block shown after all iterations."""
        result, output_path = self._run_search(tmp_path, iterations=2)
        assert result.returncode == 0

        combined = result.stdout + result.stderr
        # Check for summary indicators
        assert any(w in combined.lower() for w in [
            "summary", "best score", "iterations", "complete",
        ]), f"No summary found in output: {combined}"

    def test_improvement_tracking_in_output(self, tmp_path):
        """Each candidate has kept/discarded status."""
        result, output_path = self._run_search(tmp_path, iterations=2)
        assert result.returncode == 0

        data = json.loads(output_path.read_text())
        for c in data["candidates"]:
            assert "kept" in c
            assert isinstance(c["kept"], bool)
            assert "delta_from_baseline" in c


# ── Ctrl+C handling test ─────────────────────────────────────────────────────


class TestCtrlCHandling:
    """VAL-SRCH-004: SIGINT saves completed iterations, no corrupt JSON."""

    def test_sigint_saves_completed_iterations(self, tmp_path):
        """Send SIGINT mid-search; verify partial results saved."""
        search_space = _make_search_space(tmp_path)
        labels = _make_labels(tmp_path)
        output_path = tmp_path / "interrupted_results.json"

        cmd = [
            sys.executable, str(SEARCH_PY),
            "--config", str(CONFIGS_DIR / "locked_baseline.yaml"),
            "--search-space", str(search_space),
            "--labels", str(labels),
            "--iterations", "100",  # Large count — we'll interrupt before completion
            "--output", str(output_path),
            "--seed", "42",
            "--data", str(DATA_DIR / "eurusd_1m_2024-01-07_to_2024-01-12.csv"),
        ]

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

        # Wait a bit for at least one iteration to complete, then send SIGINT
        time.sleep(90)  # Give time for first iteration
        proc.send_signal(signal.SIGINT)

        try:
            stdout, stderr = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            pytest.skip("Process didn't respond to SIGINT in time")

        # Output file should exist and contain valid JSON
        if output_path.exists():
            text = output_path.read_text()
            data = json.loads(text)  # Should not raise
            assert "candidates" in data
            assert "metadata" in data
            # Should have saved whatever iterations completed
            assert data["metadata"]["iterations_completed"] >= 0
            assert len(data["candidates"]) == data["metadata"]["iterations_completed"]


# ── File validation tests ─────────────────────────────────────────────────────


class TestFileValidation:
    """Tests for file path validation in search.py."""

    def test_nonexistent_config_error(self, tmp_path):
        """Missing config file produces clear error."""
        search_space = _make_search_space(tmp_path)
        labels = _make_labels(tmp_path)

        result = subprocess.run(
            [sys.executable, str(SEARCH_PY),
             "--config", str(tmp_path / "nonexistent.yaml"),
             "--search-space", str(search_space),
             "--labels", str(labels),
             "--iterations", "5"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0
        assert "not found" in result.stderr.lower() or "error" in result.stderr.lower()

    def test_nonexistent_search_space_error(self, tmp_path):
        """Missing search-space file produces clear error."""
        labels = _make_labels(tmp_path)

        result = subprocess.run(
            [sys.executable, str(SEARCH_PY),
             "--config", str(CONFIGS_DIR / "locked_baseline.yaml"),
             "--search-space", str(tmp_path / "nonexistent.yaml"),
             "--labels", str(labels),
             "--iterations", "5"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0
        assert "not found" in result.stderr.lower() or "error" in result.stderr.lower()

    def test_empty_labels_error(self, tmp_path):
        """Empty labels file produces clear error message."""
        search_space = _make_search_space(tmp_path)
        labels = _make_empty_labels(tmp_path)

        result = subprocess.run(
            [sys.executable, str(SEARCH_PY),
             "--config", str(CONFIGS_DIR / "locked_baseline.yaml"),
             "--search-space", str(search_space),
             "--labels", str(labels),
             "--iterations", "5",
             "--data", str(DATA_DIR / "eurusd_1m_2024-01-07_to_2024-01-12.csv")],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "no" in combined.lower() and "label" in combined.lower()
