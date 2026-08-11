"""Azure Blob Storage access shared by the exporter and the dashboard backend.

Both the publish side (scripts/export_duckdb.py) and the read side
(dashboard/backends.py) need to reach the same private container. This module
centralizes the credential parsing and the blob defaults so the two sides
cannot drift.

Credentials support exactly one mode (mirroring the statsboteval pattern):

* ``AZURE_BLOB_CONNECTION_STRING`` — local/dev or any environment with a
  connection string.
* ``AZURE_BLOB_ACCOUNT_URL`` + ``AZURE_BLOB_CREDENTIAL`` — cloud (account URL
  plus an account key or SAS token).

If neither is set, ``blob_client()`` raises a clear error.
"""
from __future__ import annotations

import os
from pathlib import Path

CONTAINER = os.getenv("AZURE_BLOB_CONTAINER", "trust-bandits")
BLOB_NAME = os.getenv("AZURE_BLOB_NAME", "dashboard/trust_bandits.duckdb")


def blob_client():
    """Return a ``BlobServiceClient`` from the configured credential mode."""
    from azure.storage.blob import BlobServiceClient

    conn = os.getenv("AZURE_BLOB_CONNECTION_STRING")
    if conn:
        return BlobServiceClient.from_connection_string(conn)
    account_url = os.getenv("AZURE_BLOB_ACCOUNT_URL")
    credential = os.getenv("AZURE_BLOB_CREDENTIAL")
    if account_url and credential:
        return BlobServiceClient(account_url, credential=credential)
    raise RuntimeError(
        "Azure Blob Storage is not configured. Set either "
        "AZURE_BLOB_CONNECTION_STRING, or AZURE_BLOB_ACCOUNT_URL + "
        "AZURE_BLOB_CREDENTIAL."
    )


def get_container_client():
    """Return the container client, creating the container if it does not exist."""
    from azure.core.exceptions import ResourceExistsError

    container = blob_client().get_container_client(CONTAINER)
    try:
        container.create_container()
    except ResourceExistsError:
        pass
    return container


def download_blob(dest: Path) -> Path:
    """Download the dashboard blob to ``dest``, creating parent dirs."""
    blob = get_container_client().get_blob_client(BLOB_NAME)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        blob.download_blob().readinto(f)
    return dest


def cache_path() -> Path:
    """Return a writable directory for the downloaded artifact.

    Uses Streamlit's cache directory (``~/.streamlit/cache``), which is
    writable on hosts where the app directory is read-only (Streamlit
    Community Cloud). Lazy-imports Streamlit so this stays usable outside a
    running Streamlit runtime.
    """
    try:
        from streamlit.file_util import get_streamlit_file_path

        root = Path(get_streamlit_file_path("cache", "dashboard_artifacts"))
    except Exception:
        # Fall back to the platform temp dir if Streamlit is unavailable.
        import tempfile

        root = Path(tempfile.gettempdir()) / "trust_bandits_dashboard_artifacts"
    root.mkdir(parents=True, exist_ok=True)
    return root
