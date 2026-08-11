"""Tests for the dashboard data layer.

These require a running PostgreSQL (default: localhost:5433, db trustbandits,
user postgres, password testpass — see dashboard/config.py). Set DATABASE_URL
to point elsewhere if needed.

The same suite runs against the DuckDB backend by setting DATA_BACKEND=duckdb
and DUCKDB_PATH to a built ``.duckdb`` file (see scripts/export_duckdb.py).
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


@pytest.fixture(scope="module")
def duckdb_engine():
    if os.getenv("DATA_BACKEND", "postgres").lower() != "duckdb":
        pytest.skip("DuckDB backend not selected (set DATA_BACKEND=duckdb)")
    db.init_db()
    yield db.get_engine()
    db.dispose()


@pytest.fixture(scope="module")
def tables():
    if os.getenv("DATA_BACKEND", "postgres").lower() == "duckdb":
        return (
            "conditions", "runs", "base_cost_runs", "base_trajectories",
            "base_error_traces_agg", "extension_condition_aggregates",
            "extension_trajectories", "d5_runs", "hysteresis",
            "hysteresis_trajectories", "ingest_meta", "model_meta",
        )
    return (
        "conditions", "runs", "trials", "base_cost_runs", "base_error_traces",
        "extension_condition_aggregates", "extension_trajectories", "d5_runs",
        "hysteresis", "hysteresis_trajectories", "ingest_meta", "model_meta",
    )


def test_schema_tables_exist(engine, tables):
    if os.getenv("DATA_BACKEND", "postgres").lower() == "duckdb":
        present = set(db.fetch_df("SHOW TABLES")["name"])
        for t in tables:
            assert t in present, f"table {t} missing"
        return
    with engine.connect() as c:
        for t in tables:
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


def test_base_heatmap_cells(engine):
    df = loaders.base_heatmap_cells("full")
    assert len(df) == 64
    assert {"delta_acc", "is_paradox"}.issubset(df.columns)


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
    assert "n_runs" in t.columns


def test_n_runs_populated(engine):
    n = loaders.condition_n_runs("1", "full", "binary", "stationary", 0.65, 6.0)
    assert n == 1000


def test_study23_heatmap(engine):
    df = loaders.study23_heatmap_data("2", "full", "binary", "cyclic")
    assert not df.empty
    assert df.shape[0] == 8  # 8 c_pen levels


def test_extension_heatmap_cells(engine):
    df = loaders.extension_heatmap_cells(
        "2", "full", "cyclic", x_var="mu_e", y_var="c_pen",
        fixed={"expert_inertia_divisor": 2.0}, steady=True,
    )
    assert not df.empty
    assert df["x"].nunique() == 8
    assert df["y"].nunique() == 8
    assert {"delta_acc", "is_paradox"}.issubset(df.columns)


def test_extension_trajectory_data(engine):
    df = loaders.extension_trajectory_data("2", "full", "cyclic", 0.65, 2.0, 10.0)
    assert not df.empty
    assert df["trial"].max() == 100
    assert df["n_runs"].iloc[0] == 500
    assert {"mean_p_expert", "mean_trust_expert", "mean_acc_expert"}.issubset(df.columns)


def test_d5_runs(engine):
    df = loaders.d5_runs_data("d5-1", "partial")
    assert not df.empty
    assert "value" in df.columns


def test_hysteresis(engine):
    df = loaders.hysteresis_data("2", "full")
    assert not df.empty
    assert "init_condition" in df.columns


def test_base_d2_d3_error_trace(engine):
    d2 = loaders.base_difficulty_data("full")
    d3 = loaders.base_cost_data("full")
    err = loaders.base_error_trace_data("full")
    assert d2["mu_e"].nunique() == 8
    assert d3["cost_sum"].nunique() == 6
    assert set(err["source"].unique()) == {"Expert", "Peers"}


def test_dynamic_base_condition_error_trace(engine):
    cid = loaders.condition_id("1", "full", "binary", "stationary", 0.65, 6.0)
    err = loaders.base_condition_error_trace_data(cid, window=5, max_events_per_source=10)
    assert not err.empty
    assert set(err["source"].unique()).issubset({"Expert", "Peers"})
    if os.getenv("DATA_BACKEND", "postgres").lower() == "duckdb":
        # Pre-aggregated table is fixed at export-time window (10).
        assert err["offset"].min() >= -10
        assert err["offset"].max() <= 10
    else:
        assert err["offset"].min() >= -5
        assert err["offset"].max() <= 5


def test_hysteresis_trajectory(engine):
    df = loaders.hysteresis_trajectory_data("2", "full", "cyclic")
    assert not df.empty
    assert df["init_condition"].nunique() == 2


def test_model_meta(engine):
    for study in ("1", "2", "3", "d5-1"):
        design = loaders.model_meta(study)
        assert design, f"model_meta missing design for study {study}"
        s = loaders.fixed_parameters_html(study, design)
        assert "n/a" not in s
        assert "σ<sub>E</sub>=" in s or "σ<sub>E</sub> = " in s