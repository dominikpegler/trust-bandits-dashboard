"""Tests for the pluggable data backends.

These run against both backends and exercise the DuckDB fetch-on-missing
behaviour without touching the network (``download_blob`` is monkeypatched).
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard import backends  # noqa: E402


def _make_duckdb(path: Path) -> Path:
    """Create a tiny valid DuckDB file with one table."""
    import duckdb

    con = duckdb.connect(str(path))
    try:
        con.execute("CREATE TABLE sample (x INTEGER)")
        con.execute("INSERT INTO sample VALUES (1), (2), (3)")
    finally:
        con.close()
    return path


def test_duckdb_fetch_on_missing(tmp_path, monkeypatch):
    """A missing DUCKDB_PATH is downloaded to the cache dir before opening."""
    dest = tmp_path / "trust_bandits.duckdb"  # DUCKDB_PATH (baked-in path, absent)
    source = _make_duckdb(tmp_path / "source.duckdb")
    cache = tmp_path / "cache"

    def fake_cache_path():
        cache.mkdir(parents=True, exist_ok=True)
        return cache

    def fake_download(target):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        return target

    monkeypatch.setattr("dashboard.blobstore.cache_path", fake_cache_path)
    monkeypatch.setattr("dashboard.blobstore.download_blob", fake_download)

    backend = backends.DuckDBBackend(path=str(dest))
    try:
        df = backend.fetch_df("SELECT x FROM sample ORDER BY x")
        assert df["x"].tolist() == [1, 2, 3]
    finally:
        backend.dispose()
    # The artifact is written into the cache dir, not DUCKDB_PATH.
    assert (cache / "trust_bandits.duckdb").exists()
    assert not dest.exists()


def test_duckdb_missing_no_blob_raises(tmp_path, monkeypatch):
    """A missing DUCKDB_PATH with no Blob credentials raises a clear error."""
    dest = tmp_path / "missing.duckdb"

    def fake_cache_path():
        return tmp_path

    def raise_no_creds(*_a, **_k):
        raise RuntimeError("not configured")

    monkeypatch.setattr("dashboard.blobstore.cache_path", fake_cache_path)
    monkeypatch.setattr("dashboard.blobstore.download_blob", raise_no_creds)

    with pytest.raises(RuntimeError, match="not found at"):
        backends.DuckDBBackend(path=str(dest))


def test_sql_bind_translation():
    """Postgres :name binds are translated to DuckDB $name."""
    sql = "SELECT * FROM t WHERE a = :a AND b = :b"
    assert backends._to_duckdb_sql(sql) == "SELECT * FROM t WHERE a = $a AND b = $b"


def test_get_container_client_creates_missing(monkeypatch):
    """A missing container is created once, then reused."""
    from azure.core.exceptions import ResourceExistsError

    from dashboard import blobstore

    created = []

    class FakeContainer:
        def __init__(self, name):
            self.name = name

        def create_container(self):
            created.append(self.name)
            raise ResourceExistsError("already exists")

        def get_blob_client(self, blob):
            return None

    class FakeService:
        def get_container_client(self, name):
            return FakeContainer(name)

    monkeypatch.setattr(blobstore, "blob_client", lambda: FakeService())

    c = blobstore.get_container_client()
    assert c.name == "trust-bandits"
    assert created == ["trust-bandits"]


def test_cache_path_is_created_and_writable():
    """cache_path() returns an existing, writable directory."""
    from dashboard import blobstore

    path = blobstore.cache_path()
    assert path.is_dir()
    probe = path / ".probe"
    probe.write_text("x")
    assert probe.exists()
    probe.unlink()
