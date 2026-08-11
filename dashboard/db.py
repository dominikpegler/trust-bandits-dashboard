import atexit
import contextlib
from typing import Iterator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .backends import get_backend, reset_backend
from .config import database_url
from .schema import SCHEMA

_engine: Optional[Engine] = None


def get_engine() -> Engine:
    """Return the active backend's engine/connection.

    Under the Postgres backend this is the SQLAlchemy engine (used by the
    ingest script and tests). Under the DuckDB backend it is the DuckDB
    connection object.
    """
    import os

    if os.getenv("DATA_BACKEND", "postgres").lower() == "duckdb":
        return get_backend().engine()
    global _engine
    if _engine is None:
        _engine = create_engine(
            database_url(),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        atexit.register(_engine.dispose)
    return _engine


def dispose() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None
    reset_backend()


@contextlib.contextmanager
def connect() -> Iterator:
    """Yield a raw psycopg connection. Best for bulk COPY-style loads."""
    engine = get_engine()
    conn = engine.raw_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Create tables/partitions if they do not yet exist. Idempotent.

    Under the DuckDB backend this is a no-op: the schema is baked into the
    ``.duckdb`` file at export time, so there is nothing to create.
    """
    import os

    if os.getenv("DATA_BACKEND", "postgres").lower() == "duckdb":
        return
    engine = get_engine()
    with engine.begin() as c:
        legacy_d5_table = "b" + "5_runs"
        legacy_d5_index = "b" + "5_runs_grid_idx"
        legacy_d5_study = "b" + "5-"
        c.execute(text(f"""
            DO $$
            BEGIN
                IF to_regclass('public.{legacy_d5_table}') IS NOT NULL
                   AND to_regclass('public.d5_runs') IS NULL THEN
                    ALTER TABLE {legacy_d5_table} RENAME TO d5_runs;
                END IF;
                IF to_regclass('public.{legacy_d5_index}') IS NOT NULL
                   AND to_regclass('public.d5_runs_grid_idx') IS NULL THEN
                    ALTER INDEX {legacy_d5_index} RENAME TO d5_runs_grid_idx;
                END IF;
            END $$;
        """))
        c.execute(text(SCHEMA))
        c.execute(
            text("UPDATE conditions SET study = replace(study, :legacy, 'd5-') WHERE study LIKE :pattern"),
            {"legacy": legacy_d5_study, "pattern": f"{legacy_d5_study}%"},
        )
        c.execute(
            text("UPDATE d5_runs SET study = replace(study, :legacy, 'd5-') WHERE study LIKE :pattern"),
            {"legacy": legacy_d5_study, "pattern": f"{legacy_d5_study}%"},
        )
        for mode in ("binary", "continuous"):
            c.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS trials_{mode} PARTITION OF trials "
                    "FOR VALUES IN (:mode)"
                ),
                {"mode": mode},
            )


def exec_ddl(sql: str) -> None:
    engine = get_engine()
    with engine.begin() as c:
        c.execute(text(sql))


def fetch_df(query: str, params: Optional[dict] = None) -> "pd.DataFrame":
    """Run a read query against the configured backend.

    The backend is selected by ``DATA_BACKEND`` (``postgres`` | ``duckdb``).
    Queries use Postgres ``:name`` bind style; the DuckDB backend translates
    them automatically.
    """
    return get_backend().fetch_df(query, params)
