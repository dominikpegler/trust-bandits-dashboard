"""Pluggable read backends for the dashboard.

Two implementations share a common ``fetch_df(query, params)`` interface:

* ``PostgresBackend`` — the original SQLAlchemy/psycopg2 path (used for local
  development and tests against a real PostgreSQL).
* ``DuckDBBackend`` — reads a local ``.duckdb`` file (the compact artifact
  produced by ``scripts/export_duckdb.py``). Used in deployed environments.

The backend is selected by the ``DATA_BACKEND`` environment variable
(``postgres`` | ``duckdb``), defaulting to ``postgres`` so nothing breaks for
local development.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

import pandas as pd

from .config import database_url

# Postgres ``:name`` bind style -> DuckDB ``$name``.
_BIND_RE = re.compile(r":(\w+)")


def _to_duckdb_sql(query: str) -> str:
    return _BIND_RE.sub(r"$\1", query)


class PostgresBackend:
    """Read via SQLAlchemy over psycopg2 (the original implementation)."""

    def __init__(self) -> None:
        from sqlalchemy import create_engine

        self._engine = create_engine(
            database_url(),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )

    def fetch_df(self, query: str, params: Optional[dict] = None) -> pd.DataFrame:
        from sqlalchemy import text

        with self._engine.connect() as c:
            return pd.read_sql_query(text(query), c, params=params)

    def engine(self):
        return self._engine

    def dispose(self) -> None:
        self._engine.dispose()


class DuckDBBackend:
    """Read a local DuckDB file (the compact dashboard artifact).

    If the file at ``DUCKDB_PATH`` is not present, it is downloaded from Azure
    Blob Storage into the writable Streamlit cache directory (see
    :mod:`dashboard.blobstore`). This lets the app run on hosts with an
    ephemeral or read-only filesystem (Streamlit Community Cloud) while still
    using the baked-in file on Azure.
    """

    def __init__(self, path: str | None = None) -> None:
        import duckdb

        self._path = os.getenv("DUCKDB_PATH", "data/trust_bandits.duckdb") if path is None else path
        local = Path(self._path).expanduser()
        if not local.exists():
            try:
                from .blobstore import cache_path, download_blob

                local = cache_path() / Path(self._path).name
                download_blob(local)
            except RuntimeError as exc:
                raise RuntimeError(
                    f"DuckDB file not found at {Path(self._path)} and Azure Blob "
                    f"Storage is not configured. Set DATA_BACKEND=duckdb with a local "
                    f"DUCKDB_PATH, or configure the AZURE_BLOB_* variables to download "
                    f"it. ({exc})"
                ) from exc
        self._con = duckdb.connect(str(local), read_only=True)

    def fetch_df(self, query: str, params: Optional[dict] = None) -> pd.DataFrame:
        sql = _to_duckdb_sql(query)
        if params:
            return self._con.execute(sql, params).df()
        return self._con.execute(sql).df()

    def engine(self):
        return self._con

    def dispose(self) -> None:
        self._con.close()


def get_backend():
    """Return the configured backend instance (cached per process)."""
    global _backend
    if _backend is None:
        mode = os.getenv("DATA_BACKEND", "postgres").lower()
        if mode == "duckdb":
            _backend = DuckDBBackend()
        else:
            _backend = PostgresBackend()
    return _backend


def reset_backend() -> None:
    global _backend
    if _backend is not None:
        _backend.dispose()
        _backend = None


_backend: Optional[object] = None
