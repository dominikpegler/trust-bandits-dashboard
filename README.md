# Trust-Bandits Explorer

Interactive companion dashboard for *Why Even Accurate Experts Lose Trust:
A Multi-Agent Reinforcement Learning Model*.

A Streamlit app that lets you explore the simulation data (paper-aligned
heatmaps, exploratory metric views, marginal curves, trial trajectories) and run
single simulations live. The app reads from a data backend; the data is
populated by a one-shot export script.

## Architecture

```
app.py                      Streamlit entrypoint
pages/                      Streamlit multipage views
dashboard/                  helper package (backends, db, loaders, plotting, live_sim)
scripts/ingest.py           one-shot: reset-and-refill a PostgreSQL database
scripts/export_duckdb.py    one-shot: build a compact .duckdb file and upload to Blob
```

- **App**: Streamlit, deployed as a Hugging Face Space (private during dev) or
  on Azure.
- **Data backend**: pluggable. Local development and tests use PostgreSQL; the
  deployed app uses a compact DuckDB file (see `dashboard/backends.py`).
- **Data**: the app only *reads*. The raw simulation data lives on the author's
  machine (Dropbox); `ingest.py` pushes it to Postgres (dev) and
  `export_duckdb.py` builds the DuckDB artifact for deployment.

## Data backend

The backend is selected by the `DATA_BACKEND` environment variable:

- `postgres` (default) — the original SQLAlchemy/psycopg2 path, used for local
  development and tests.
- `duckdb` — reads a local `.duckdb` file (the compact artifact produced by
  `scripts/export_duckdb.py`), used in deployed environments. Set `DUCKDB_PATH`
  to the file location (the path baked into the image on Azure). If the file is
  absent, the app downloads it from Azure Blob Storage into the writable
  Streamlit cache dir on first use (see `dashboard/blobstore.py`), so the app
  runs on hosts with an ephemeral or read-only filesystem (Streamlit Community
  Cloud) as well as on hosts with the file baked into the image (Azure).

The DuckDB file is a single self-contained database (36 MB) holding all
dashboard tables. The base-model trial-level data is pre-aggregated into
`base_trajectories` and `base_error_traces_agg` at export time, so the deployed
app never touches the raw 6.4M-row `trials` table. See
`docs/db-migration-memo.md` for the rationale and benchmark.

## Setup (local development)

```bash
conda activate tower
pip install -r requirements.txt
pip install -e ../trust-bandits-analysis   # for the live simulator
```

### Start a local Postgres (optional, recommended for development)

The simplest way to get a database for development is a throwaway Docker
container:

```bash
docker run -d --name tb-pg-dev -e POSTGRES_PASSWORD=testpass \
  -e POSTGRES_DB=trustbandits -p 5433:5432 postgres:16-alpine
```

`dashboard/config.py` already defaults to
`localhost:5433 / trustbandits / postgres / testpass`, so with that container
**no `.env` file is required**.

### Pointing at another database (Azure)

Only if you want to use a different database (e.g. Azure), create a `.env`
(git-ignored) with the connection:

```
DATABASE_URL=postgresql://user:pass@host:5432/dbname?sslmode=require
```

Or, equivalently, the individual `AZURE_PG_*` variables (see
`dashboard/config.py`).

### Using the DuckDB backend locally

Build the DuckDB file (see below), then run the app with:

```bash
export DATA_BACKEND=duckdb
export DUCKDB_PATH=data/trust_bandits.duckdb
streamlit run app.py
```

If `DUCKDB_PATH` does not exist locally, the app fetches it from Azure Blob
Storage into the writable Streamlit cache dir (set the `AZURE_BLOB_*`
variables). This is how the deployed app self-provisions on a cold start.

## Populate the database

### Postgres (development)

```bash
export DATABASE_URL='postgresql://USER:PASSWORD@SERVER.postgres.database.azure.com:5432/DBNAME?sslmode=require'
export DATA_DIR="PATH/TO//trust-bandits-analysis"
```

```bash
python scripts/ingest.py --studies 1 2 3 d5   # reset-and-refill, all studies
python scripts/ingest.py --studies 1 --skip-trials   # faster, no trial-level
python scripts/ingest.py --dry-run            # show what would be ingested
```

The ingest is **atomic**: data is loaded into staging tables, then the live
tables are truncated and repopulated in a single transaction, so readers never
see a partial or stale database. Each run records an `ingest_meta` row
(timestamp, analysis git SHA, row counts).

### DuckDB artifact (deployment)

Build and publish the compact `.duckdb` file to Azure Blob Storage. The app
downloads this file on cold start, so run this **after** a data update and
**before** the next Community Cloud cold start.

The upload reads the `AZURE_BLOB_*` variables from the environment or `.env`.
You can supply them either inline or via a `.env` file (see `.env.example`):

```bash
# Point at your local raw data.
export DATA_DIR="/home/you/Dropbox/data_export/trust-bandits-analysis"

# --- Option 1: connection string ---
export AZURE_BLOB_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=YOURACCOUNT;AccountKey=YOURKEY;EndpointSuffix=core.windows.net"

# --- Option 2: account URL + credential (account key or SAS token) ---
export AZURE_BLOB_ACCOUNT_URL="https://YOURACCOUNT.blob.core.windows.net"
export AZURE_BLOB_CREDENTIAL="YOURKEY-OR-SAS"
# optional overrides (defaults shown):
export AZURE_BLOB_CONTAINER="trust-bandits"
export AZURE_BLOB_NAME="dashboard/trust_bandits.duckdb"

# Build the file from the raw data, then upload it to Blob.
python scripts/export_duckdb.py --out data/trust_bandits.duckdb --upload
```

- `export_duckdb.py` reads the same raw sources as `ingest.py`, pre-aggregates
  the base-model dynamics, and writes a single `.duckdb` file.
- `--upload` pushes that file to the configured Blob container/blob name
  (`AZURE_BLOB_CONTAINER` / `AZURE_BLOB_NAME`), overwriting any previous one.
  The container is created automatically if it does not already exist in the
  storage account.
- To push an **already-built** file to Blob without rebuilding (skips the slow
  aggregation), use `--upload-only`:

  ```bash
  python scripts/export_duckdb.py --upload-only --out data/trust_bandits.duckdb
  ```
- Run `--dry-run` first to preview what would be exported without writing or
  uploading anything:

  ```bash
  python scripts/export_duckdb.py --dry-run
  ```

Once the file is in Blob, deploy or restart the app (see [Deploy](#deploy)); on
cold start the app downloads it and serves queries in-process.

## Run the app

```bash
streamlit run app.py
```

Open the printed URL (default `http://localhost:8501`). Edits to files in
`pages/` and `app.py` hot-reload on save. After editing files in `dashboard/`,
restart Streamlit so Python reloads the helper package.

## Run the tests

```bash
python -m pytest tests/ -q
```

Needs the Postgres running with data ingested (the trajectory test skips if
trial-level data isn't loaded). The same suite runs against the DuckDB backend:

```bash
DATA_BACKEND=duckdb DUCKDB_PATH=data/trust_bandits.duckdb python -m pytest tests/ -q
```

## Development loop

- Edit a page in `pages/` or `app.py` → Streamlit hot-reloads → check it in the
  browser.
- Edit code in `dashboard/` → restart `streamlit run app.py` before checking the
  browser. Streamlit reruns page files, but it does not reliably reload already
  imported helper modules.
- When you change the data pipeline, edit `scripts/ingest.py` (Postgres) or
  `scripts/export_duckdb.py` (DuckDB), re-run it, and the app reflects the new
  data on the next interaction.
- Use `--skip-trials` for fast iteration (heatmap + marginal pages only); run a
  full ingest (with trial-level data) when testing folded trajectory sections on
  the Base Model, Memory Model, and Graded-Evaluation Model pages.

## Deploy

The Streamlit SDK is deprecated on Hugging Face Spaces, so the app is deployed
as a Docker container. Three hosting paths are available.

> **Note:** the `Dockerfile` installs the `trustbandits` package from the
> `dominikpegler/trust-bandits-analysis` repo as a git dependency. That repo is
> currently **private**, so the image will only build once it is made public
> (planned for paper publication) or a build token is supplied. Until then, use
> Path A (Community Cloud) or build locally.

> **Data backend on deploy:** the deployed app uses the DuckDB backend
> (`DATA_BACKEND=duckdb`). The `.duckdb` file is baked into the image (Path B/C)
> or fetched from Azure Blob Storage on cold start (Path A, which has an
> ephemeral filesystem). Build the file with `scripts/export_duckdb.py` before
> deploying.

### Path A — Streamlit Community Cloud (free, for collaborators)

No Dockerfile is needed; Community Cloud containerizes the app for you.

1. Push this repo to GitHub (public or private).
2. In [Streamlit Community Cloud](https://share.streamlit.io), click **Deploy an
   app**, select the repo, and set the entrypoint to `app.py`.
3. Set the `DATA_BACKEND=duckdb` secret and the `AZURE_BLOB_*` secrets so the app
   can fetch the `.duckdb` from Blob on cold start (Settings → Secrets).
4. Share the app URL with collaborators.

Note: free apps sleep after a period of inactivity and wake on the next visit,
re-fetching the `.duckdb` from Blob on each wake.

### Path B — Hugging Face Spaces (requires a paid subscription)

Docker Spaces require a Hugging Face **PRO** or **Team** subscription, which is
recurring (not a one-time cost).

1. Create a Space with the **Docker** SDK, connected to this GitHub repo.
2. In the Space's `README.md`, set `sdk: docker` and `app_port: 7860`.
3. Ensure `data/trust_bandits.duckdb` is present (the Dockerfile bakes it in).
4. Keep the Space **private** during development; make it public when the paper
   is submitted.

### Path C — Azure (permanent, uses an existing subscription)

Build the provided `Dockerfile` on Azure Container Apps or Azure App Service
(Linux). The `.duckdb` file is baked into the image, so there is no managed
relational database and no cold-start download.

1. Build the `.duckdb` file and push the image to Azure Container Registry.
2. Create a Container App or App Service (Linux) from that image.
3. The image already sets `DATA_BACKEND=duckdb` and `DUCKDB_PATH`; no database
   connection is needed.
4. Configure HTTPS and, if desired, restrict access while the paper is in
   review.

## Notes

- The Base Model page uses binary, stationary base-model data for the main D1
  heatmap and folds selected-condition trajectories into the same page.
- The Memory and Graded-Evaluation pages keep the main paper-style heatmaps
  fixed to `p(Expert)`; trust and accuracy heatmaps are available in exploratory
  expanders.
- Trial-level data is loaded for the base model by default; `--skip-trials`
  skips it. Extension trajectory panels use `extension_trajectories` loaded by a
  full extension ingest.
- In the DuckDB artifact, base-model trial-level data is pre-aggregated into
  `base_trajectories` and `base_error_traces_agg`; the raw `trials` and
  `base_error_traces` tables are not exported.
