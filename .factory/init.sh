#!/bin/bash
set -e

cd /Users/echopeso/research_accelerator

# Install project in editable mode if pyproject.toml exists and ra is not importable
if [ -f "pyproject.toml" ]; then
    if ! python3 -c "import ra" 2>/dev/null; then
        echo "Installing project in editable mode..."
        python3 -m pip install -e ".[dev]" --quiet
    fi
fi

# Verify baseline fixtures exist
if [ ! -d "tests/fixtures/baseline_output" ]; then
    echo "ERROR: Baseline fixtures not found at tests/fixtures/baseline_output/"
    echo "Run the pipeline first: cd pipeline && python preprocess_data_v2.py"
    exit 1
fi

# Verify dataset exists
if [ ! -f "data/eurusd_1m_2024-01-07_to_2024-01-12.csv" ]; then
    echo "ERROR: Dataset not found at data/eurusd_1m_2024-01-07_to_2024-01-12.csv"
    exit 1
fi

# Count baseline fixtures
FIXTURE_COUNT=$(ls -1 tests/fixtures/baseline_output/*.json 2>/dev/null | wc -l | tr -d ' ')
echo "Environment ready. Baseline fixtures: ${FIXTURE_COUNT} JSON files."
