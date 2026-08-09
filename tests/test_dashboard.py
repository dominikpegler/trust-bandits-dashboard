"""Tests for the dashboard data layer.

These require a running PostgreSQL (default: localhost:5433, db trustbandits,
user postgres, password testpass — see dashboard/config.py). Set DATABASE_URL
to point elsewhere if needed.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard import db, loaders  # noqa: E402


@pytest.fixture(scope="module")
def engine():
    db.init_db()
    yield db.get_engine()
    db.dispose()


def test_schema_tables_exist(engine):
    with engine.connect() as c:
        for t in ("conditions", "runs", "trials", "ingest_meta"):
            row = c.exec_driver_sql(
                "SELECT to_regclass('public." + t + "')"
            ).fetchone()
            assert row[0] is not None, f"table {t} missing"


def test_conditions_populated(engine):
    df = loaders.available_studies()
    assert "1" in df


def test_heatmap_shape(engine):
    df = loaders.heatmap_data("1", "full", "binary", "stationary")
    assert df.shape == (8, 8)


def test_marginal(engine):
    m = loaders.marginal_data("1", "full", "binary", "stationary", fixed={"mu_e": 0.65})
    assert len(m) == 8


def test_condition_id_and_trajectory(engine):
    cid = loaders.condition_id("1", "full", "binary", "stationary", 0.65, 6.0)
    assert cid is not None
    t = loaders.trajectory_data(cid)
    if t.empty:
        pytest.skip("trial-level data not loaded (run ingest without --skip-trials)")
    assert "mean_p_expert" in t.columns
