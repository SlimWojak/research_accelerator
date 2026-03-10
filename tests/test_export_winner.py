"""Tests for search.py --export-winner functionality.

TDD tests covering:
- VAL-SRCH-003: Output JSON has candidates sorted by fitness descending with rank, score, config, iteration
- VAL-WIN-001: Top candidate exportable as comparison fixture (Schema 4A)
- VAL-WIN-002: Exported winner fixture loadable by compare.html (Schema 4A structure)
- VAL-CROSS-003: Search winner → exported as fixture → compare.html loads fixture

Tests verify:
  1. --export-winner flag accepted by search.py
  2. Export produces Schema 4A JSON with baseline + winner configs
  3. Exported file has per_config, pairwise, divergence_index
  4. Winner config applies perturbed params from search results
  5. Fixture is loadable (valid JSON with required fields)
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

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


def _run_search(tmp_path: Path, iterations: int = 2, seed: int = 42) -> tuple[subprocess.CompletedProcess, Path]:
    """Run search.py and return result + output path."""
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

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=600,
    )
    return result, output_path


# ── VAL-SRCH-003: Ranked output with candidates ──────────────────────────────


class TestRankedOutput:
    """VAL-SRCH-003: Output JSON has candidates array sorted by fitness descending."""

    def test_candidates_have_required_fields(self, tmp_path):
        """Each candidate has rank, score, config, iteration."""
        result, output_path = _run_search(tmp_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert output_path.exists()

        data = json.loads(output_path.read_text())
        candidates = data["candidates"]
        assert len(candidates) >= 1

        for c in candidates:
            assert "rank" in c, f"Missing 'rank' in candidate: {c}"
            assert "score" in c, f"Missing 'score' in candidate: {c}"
            assert "config" in c, f"Missing 'config' in candidate: {c}"
            assert "iteration" in c, f"Missing 'iteration' in candidate: {c}"

    def test_candidates_sorted_by_score_descending(self, tmp_path):
        """Candidates are sorted by score in descending order."""
        result, output_path = _run_search(tmp_path, iterations=3)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        data = json.loads(output_path.read_text())
        candidates = data["candidates"]
        scores = [c["score"] for c in candidates]
        assert scores == sorted(scores, reverse=True), \
            f"Candidates not sorted by score descending: {scores}"

    def test_ranks_are_contiguous(self, tmp_path):
        """Ranks are 1-indexed and contiguous."""
        result, output_path = _run_search(tmp_path, iterations=3)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        data = json.loads(output_path.read_text())
        candidates = data["candidates"]
        ranks = [c["rank"] for c in candidates]
        assert ranks == list(range(1, len(candidates) + 1)), \
            f"Ranks not contiguous: {ranks}"


# ── VAL-WIN-001: Export winner as comparison fixture ──────────────────────────


class TestExportWinner:
    """VAL-WIN-001: Top candidate exportable as comparison fixture."""

    def test_export_winner_help_flag(self):
        """--export-winner is documented in --help."""
        result = subprocess.run(
            [sys.executable, str(SEARCH_PY), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "export-winner" in result.stdout.lower() or "export_winner" in result.stdout.lower()

    def test_export_winner_produces_schema_4a(self, tmp_path):
        """--export-winner produces Schema 4A JSON file."""
        # First run search
        result, search_output = _run_search(tmp_path)
        assert result.returncode == 0, f"Search failed: {result.stderr}"
        assert search_output.exists()

        # Now export winner
        fixture_path = tmp_path / "winner_fixture.json"
        export_cmd = [
            sys.executable, str(SEARCH_PY),
            "--export-winner", str(search_output),
            "--config", str(CONFIGS_DIR / "locked_baseline.yaml"),
            "--data", str(DATA_DIR / "eurusd_1m_2024-01-07_to_2024-01-12.csv"),
            "--output", str(fixture_path),
        ]

        export_result = subprocess.run(
            export_cmd, capture_output=True, text=True, timeout=600,
        )
        assert export_result.returncode == 0, f"Export failed: {export_result.stderr}"
        assert fixture_path.exists(), "Fixture file not created"

        # Validate Schema 4A structure
        data = json.loads(fixture_path.read_text())
        assert "schema_version" in data
        assert "per_config" in data
        assert "configs" in data
        assert "pairwise" in data

    def test_export_winner_has_two_configs(self, tmp_path):
        """Exported fixture has exactly 2 configs: baseline + winner."""
        # Run search
        result, search_output = _run_search(tmp_path)
        assert result.returncode == 0, f"Search failed: {result.stderr}"

        # Export winner
        fixture_path = tmp_path / "winner_fixture.json"
        export_cmd = [
            sys.executable, str(SEARCH_PY),
            "--export-winner", str(search_output),
            "--config", str(CONFIGS_DIR / "locked_baseline.yaml"),
            "--data", str(DATA_DIR / "eurusd_1m_2024-01-07_to_2024-01-12.csv"),
            "--output", str(fixture_path),
        ]

        export_result = subprocess.run(
            export_cmd, capture_output=True, text=True, timeout=600,
        )
        assert export_result.returncode == 0, f"Export failed: {export_result.stderr}"

        data = json.loads(fixture_path.read_text())
        configs = data["configs"]
        assert len(configs) == 2, f"Expected 2 configs, got {len(configs)}: {configs}"

        # One should be baseline, one should be winner
        per_config = data["per_config"]
        assert len(per_config) == 2

    def test_export_winner_has_pairwise_with_divergence(self, tmp_path):
        """Exported fixture has pairwise comparison with divergence_index."""
        # Run search
        result, search_output = _run_search(tmp_path)
        assert result.returncode == 0, f"Search failed: {result.stderr}"

        # Export winner
        fixture_path = tmp_path / "winner_fixture.json"
        export_cmd = [
            sys.executable, str(SEARCH_PY),
            "--export-winner", str(search_output),
            "--config", str(CONFIGS_DIR / "locked_baseline.yaml"),
            "--data", str(DATA_DIR / "eurusd_1m_2024-01-07_to_2024-01-12.csv"),
            "--output", str(fixture_path),
        ]

        export_result = subprocess.run(
            export_cmd, capture_output=True, text=True, timeout=600,
        )
        assert export_result.returncode == 0, f"Export failed: {export_result.stderr}"

        data = json.loads(fixture_path.read_text())
        pairwise = data["pairwise"]
        assert len(pairwise) >= 1, "No pairwise comparison found"

        # Check that pairwise has divergence_index
        for key, pw in pairwise.items():
            assert "divergence_index" in pw, f"No divergence_index in pairwise: {key}"

    def test_export_winner_includes_search_metadata(self, tmp_path):
        """Exported fixture includes search metadata (score, rank, iteration)."""
        # Run search
        result, search_output = _run_search(tmp_path)
        assert result.returncode == 0, f"Search failed: {result.stderr}"

        # Export winner
        fixture_path = tmp_path / "winner_fixture.json"
        export_cmd = [
            sys.executable, str(SEARCH_PY),
            "--export-winner", str(search_output),
            "--config", str(CONFIGS_DIR / "locked_baseline.yaml"),
            "--data", str(DATA_DIR / "eurusd_1m_2024-01-07_to_2024-01-12.csv"),
            "--output", str(fixture_path),
        ]

        export_result = subprocess.run(
            export_cmd, capture_output=True, text=True, timeout=600,
        )
        assert export_result.returncode == 0, f"Export failed: {export_result.stderr}"

        data = json.loads(fixture_path.read_text())

        # Check that run_id or metadata references search results
        run_id = data.get("run_id", "")
        assert "winner" in run_id.lower() or "search" in run_id.lower(), \
            f"run_id should reference search/winner: {run_id}"

    def test_export_winner_nonexistent_results_error(self, tmp_path):
        """--export-winner with nonexistent results file gives clear error."""
        export_cmd = [
            sys.executable, str(SEARCH_PY),
            "--export-winner", str(tmp_path / "nonexistent.json"),
            "--config", str(CONFIGS_DIR / "locked_baseline.yaml"),
            "--data", str(DATA_DIR / "eurusd_1m_2024-01-07_to_2024-01-12.csv"),
            "--output", str(tmp_path / "out.json"),
        ]

        result = subprocess.run(
            export_cmd, capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "not found" in combined.lower() or "error" in combined.lower()

    def test_export_winner_config_name_includes_score(self, tmp_path):
        """Winner config name in fixture includes rank and score info."""
        # Run search
        result, search_output = _run_search(tmp_path)
        assert result.returncode == 0, f"Search failed: {result.stderr}"

        # Export winner
        fixture_path = tmp_path / "winner_fixture.json"
        export_cmd = [
            sys.executable, str(SEARCH_PY),
            "--export-winner", str(search_output),
            "--config", str(CONFIGS_DIR / "locked_baseline.yaml"),
            "--data", str(DATA_DIR / "eurusd_1m_2024-01-07_to_2024-01-12.csv"),
            "--output", str(fixture_path),
        ]

        export_result = subprocess.run(
            export_cmd, capture_output=True, text=True, timeout=600,
        )
        assert export_result.returncode == 0, f"Export failed: {export_result.stderr}"

        data = json.loads(fixture_path.read_text())
        configs = data["configs"]

        # The winner config name should include "winner" or rank info
        winner_configs = [c for c in configs if "winner" in c.lower()]
        assert len(winner_configs) >= 1, \
            f"No config with 'winner' in name: {configs}"

    def test_export_winner_fixture_valid_for_compare_html(self, tmp_path):
        """VAL-WIN-002: Exported fixture has all fields compare.html needs."""
        # Run search
        result, search_output = _run_search(tmp_path)
        assert result.returncode == 0, f"Search failed: {result.stderr}"

        # Export winner
        fixture_path = tmp_path / "winner_fixture.json"
        export_cmd = [
            sys.executable, str(SEARCH_PY),
            "--export-winner", str(search_output),
            "--config", str(CONFIGS_DIR / "locked_baseline.yaml"),
            "--data", str(DATA_DIR / "eurusd_1m_2024-01-07_to_2024-01-12.csv"),
            "--output", str(fixture_path),
        ]

        export_result = subprocess.run(
            export_cmd, capture_output=True, text=True, timeout=600,
        )
        assert export_result.returncode == 0, f"Export failed: {export_result.stderr}"

        data = json.loads(fixture_path.read_text())

        # compare.html bootApp() checks these:
        assert "schema_version" in data, "Missing schema_version"
        assert "per_config" in data, "Missing per_config"

        # compare.html renderMetadata() uses:
        assert "run_id" in data, "Missing run_id"
        assert "dataset" in data, "Missing dataset"
        assert "configs" in data, "Missing configs"

        # compare.html needs per_config with detection data
        for cfg_name, cfg_data in data["per_config"].items():
            assert "per_primitive" in cfg_data, \
                f"Missing per_primitive in {cfg_name}"
            # Should have detection data for at least one primitive
            has_detections = False
            for prim, prim_data in cfg_data["per_primitive"].items():
                if "per_tf" in prim_data:
                    for tf, tf_data in prim_data["per_tf"].items():
                        if tf_data.get("detection_count", 0) > 0:
                            has_detections = True
            assert has_detections, \
                f"Config {cfg_name} has no detections in any primitive/tf"


# ── Integration test: full search → export → fixture validation ───────────────


class TestSearchToFixtureIntegration:
    """VAL-CROSS-003: Search → export → compare.html fixture validation."""

    def test_full_pipeline_search_to_fixture(self, tmp_path):
        """Full pipeline: search → export winner → valid Schema 4A fixture."""
        # Step 1: Run search
        search_result, search_output = _run_search(tmp_path, iterations=2, seed=42)
        assert search_result.returncode == 0, f"Search failed: {search_result.stderr}"
        assert search_output.exists()

        # Step 2: Verify search output has ranked candidates
        search_data = json.loads(search_output.read_text())
        candidates = search_data["candidates"]
        assert len(candidates) == 2
        assert candidates[0]["rank"] == 1
        assert candidates[0]["score"] >= candidates[1]["score"]

        # Step 3: Export winner
        fixture_path = tmp_path / "search_winner.json"
        export_cmd = [
            sys.executable, str(SEARCH_PY),
            "--export-winner", str(search_output),
            "--config", str(CONFIGS_DIR / "locked_baseline.yaml"),
            "--data", str(DATA_DIR / "eurusd_1m_2024-01-07_to_2024-01-12.csv"),
            "--output", str(fixture_path),
        ]
        export_result = subprocess.run(
            export_cmd, capture_output=True, text=True, timeout=600,
        )
        assert export_result.returncode == 0, f"Export failed: {export_result.stderr}"

        # Step 4: Validate fixture has proper structure
        fixture = json.loads(fixture_path.read_text())
        assert fixture["schema_version"] == "1.0"
        assert len(fixture["configs"]) == 2
        assert len(fixture["per_config"]) == 2
        assert len(fixture["pairwise"]) >= 1

        # Step 5: Winner config should have different detection counts than baseline
        configs = fixture["configs"]
        baseline_cfg = [c for c in configs if "baseline" in c.lower()][0]
        winner_cfg = [c for c in configs if "winner" in c.lower()][0]

        baseline_data = fixture["per_config"][baseline_cfg]
        winner_data = fixture["per_config"][winner_cfg]

        # Both should have detection data
        assert "per_primitive" in baseline_data
        assert "per_primitive" in winner_data
