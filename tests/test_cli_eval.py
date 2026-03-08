"""Tests for eval.py CLI integration (Phase 2).

Validates:
- VAL-CLI-001: eval.py sweep produces valid output
- VAL-CLI-005: --help for all subcommands
- VAL-CLI-006: Missing args produce clear errors
- VAL-CLI-007: Phase 1 run.py backward compatibility
- VAL-CLI-008: Progress output for long sweeps
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "configs" / "locked_baseline.yaml"
DATA_PATH = PROJECT_ROOT / "data" / "eurusd_1m_2024-01-07_to_2024-01-12.csv"
EVAL_PY = PROJECT_ROOT / "eval.py"
RUN_PY = PROJECT_ROOT / "run.py"


# ─── VAL-CLI-005: --help for all subcommands ─────────────────────────────


class TestHelpMessages:
    """Test that --help works for all subcommands."""

    def test_eval_help(self):
        """eval.py --help lists subcommands and exits 0."""
        result = subprocess.run(
            [sys.executable, str(EVAL_PY), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "sweep" in result.stdout
        assert "compare" in result.stdout
        assert "walk-forward" in result.stdout

    def test_sweep_help(self):
        """eval.py sweep --help shows usage."""
        result = subprocess.run(
            [sys.executable, str(EVAL_PY), "sweep", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "--config" in result.stdout

    def test_compare_help(self):
        """eval.py compare --help shows usage."""
        result = subprocess.run(
            [sys.executable, str(EVAL_PY), "compare", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "--config" in result.stdout

    def test_walk_forward_help(self):
        """eval.py walk-forward --help shows usage."""
        result = subprocess.run(
            [sys.executable, str(EVAL_PY), "walk-forward", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "--config" in result.stdout or "--river" in result.stdout


# ─── VAL-CLI-006: Missing args produce clear errors ──────────────────────


class TestMissingArgs:
    """Test that missing required args produce clear error messages."""

    def test_sweep_missing_config(self):
        """sweep without --config exits non-zero with error."""
        result = subprocess.run(
            [sys.executable, str(EVAL_PY), "sweep"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0
        assert "config" in result.stderr.lower() or "required" in result.stderr.lower()

    def test_compare_missing_config(self):
        """compare without --config exits non-zero with error."""
        result = subprocess.run(
            [sys.executable, str(EVAL_PY), "compare"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0

    def test_walk_forward_missing_args(self):
        """walk-forward without required args exits non-zero."""
        result = subprocess.run(
            [sys.executable, str(EVAL_PY), "walk-forward"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0

    def test_no_subcommand(self):
        """eval.py with no subcommand exits non-zero or shows help."""
        result = subprocess.run(
            [sys.executable, str(EVAL_PY)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Should either show help or exit with error
        assert result.returncode != 0 or "usage" in result.stdout.lower()


# ─── VAL-CLI-007: Phase 1 run.py backward compatibility ──────────────────


class TestRunPyBackwardCompat:
    """Test that Phase 1 run.py still works unchanged."""

    def test_run_py_produces_output(self):
        """run.py --config --data --output still works and produces cascade_summary.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    sys.executable, str(RUN_PY),
                    "--config", str(CONFIG_PATH),
                    "--data", str(DATA_PATH),
                    "--output", tmpdir,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            assert result.returncode == 0, f"run.py failed: {result.stderr}"

            # Verify output structure
            output_dir = Path(tmpdir)
            summary_path = output_dir / "cascade_summary.json"
            assert summary_path.exists(), "cascade_summary.json not produced"

            with open(summary_path) as f:
                summary = json.load(f)
            assert "detection_counts" in summary
            assert "total_detections" in summary
            assert summary["total_detections"] > 0


# ─── VAL-CLI-001: eval.py sweep produces valid output ────────────────────


class TestSweepSubcommand:
    """Test eval.py sweep subcommand produces valid output."""

    def test_sweep_produces_json(self):
        """eval.py sweep exits 0 and produces valid JSON output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    sys.executable, str(EVAL_PY),
                    "sweep",
                    "--config", str(CONFIG_PATH),
                    "--data", str(DATA_PATH),
                    "--primitive", "displacement",
                    "--x-param", "ltf.close_gate",
                    "--metric", "detection_count",
                    "--output", tmpdir,
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            assert result.returncode == 0, f"sweep failed: {result.stderr}"

            # Check output file exists and is valid JSON
            output_dir = Path(tmpdir)
            json_files = list(output_dir.glob("*.json"))
            assert len(json_files) > 0, "No JSON output files produced"

            # Validate the sweep output structure (Schema 4D)
            for jf in json_files:
                with open(jf) as f:
                    data = json.load(f)
                assert "schema_version" in data
