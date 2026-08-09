import os
from pathlib import Path
from urllib.parse import quote_plus


def _build_dsn_from_env() -> str:
    host = os.getenv("AZURE_PG_HOST", "localhost")
    port = os.getenv("AZURE_PG_PORT", "5433")
    dbname = os.getenv("AZURE_PG_DBNAME", "trustbandits")
    user = os.getenv("AZURE_PG_USER", "postgres")
    password = os.getenv("AZURE_PG_PASSWORD", "testpass")
    sslmode = os.getenv("AZURE_PG_SSLMODE", "disable")
    return (
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{dbname}?sslmode={sslmode}"
    )


def database_url() -> str:
    return os.getenv("DATABASE_URL", _build_dsn_from_env())


def data_dir() -> Path:
    raw = os.getenv("DATA_DIR", "~/Dropbox/data_export/trust-bandits-analysis")
    return Path(raw).expanduser()


def pub_dir() -> Path:
    return data_dir() / "pub"


def raw_dir() -> Path:
    return data_dir() / "data"
