"""Shared test fixtures for the RA test suite.

Provides pre-loaded and pre-aggregated bar DataFrames for all timeframes.
"""

from pathlib import Path

import pytest

from ra.data.csv_loader import load_csv
from ra.data.tf_aggregator import aggregate

# Path to the 5-day EURUSD 1m CSV dataset
CSV_PATH = Path(__file__).parent.parent / "data" / "eurusd_1m_2024-01-07_to_2024-01-12.csv"


@pytest.fixture(scope="session")
def bars_1m():
    """Load the 5-day EURUSD 1m bars with full session tagging."""
    return load_csv(CSV_PATH)


@pytest.fixture(scope="session")
def bars_5m(bars_1m):
    """Aggregate 1m bars to 5m."""
    return aggregate(bars_1m, "5m")


@pytest.fixture(scope="session")
def bars_15m(bars_1m):
    """Aggregate 1m bars to 15m."""
    return aggregate(bars_1m, "15m")


@pytest.fixture(scope="session")
def bars_1h(bars_1m):
    """Aggregate 1m bars to 1H."""
    return aggregate(bars_1m, "1H")


@pytest.fixture(scope="session")
def bars_4h(bars_1m):
    """Aggregate 1m bars to 4H."""
    return aggregate(bars_1m, "4H")


@pytest.fixture(scope="session")
def bars_1d(bars_1m):
    """Aggregate 1m bars to 1D (forex day)."""
    return aggregate(bars_1m, "1D")
