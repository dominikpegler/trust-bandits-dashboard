# Trust-Bandits Explorer

Interactive companion dashboard for *Why Even Accurate Experts Lose Trust:
A Multi-Agent Reinforcement Learning Model*.

A Streamlit app that lets you explore the simulation data (paper-aligned
heatmaps, exploratory metric views, marginal curves, trial trajectories) and run
single simulations live. The app reads from a PostgreSQL database; the data is
populated by a one-shot ingest script.

## Architecture

```
app.py                      Streamlit entrypoint
pages/                      Streamlit multipage views
dashboard/                  helper package (db, loaders, plotting, live_sim)
scripts/ingest.py           one-shot: reset-and-refill the database
```

- **App**: Streamlit, deployed as a Hugging Face Space (private during dev).
- **Database**: PostgreSQL (e.g. Azure Database for PostgreSQL Flexible Server).
- **Data**: the app only *reads* from Postgres. The raw simulation data lives
  on the author's machine (Dropbox); `ingest.py` pushes it to the database.

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

## Populate the database

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
trial-level data isn't loaded).

## Development loop

- Edit a page in `pages/` or `app.py` → Streamlit hot-reloads → check it in the
  browser.
- Edit code in `dashboard/` → restart `streamlit run app.py` before checking the
  browser. Streamlit reruns page files, but it does not reliably reload already
  imported helper modules.
- When you change the data pipeline, edit `scripts/ingest.py`, re-run it, and
  the app reflects the new data on the next interaction.
- Use `--skip-trials` for fast iteration (heatmap + marginal pages only); run a
  full ingest (with trial-level data) when testing folded trajectory sections on
  the Base Model, Memory Model, and Graded-Evaluation Model pages.

## Deploy

The Streamlit SDK is deprecated on Hugging Face Spaces, so the app is deployed
as a Docker container. Three hosting paths are available.

### Path A — Streamlit Community Cloud (free, for collaborators)

No Dockerfile is needed; Community Cloud containerizes the app for you.

1. Push this repo to GitHub (public or private).
2. In [Streamlit Community Cloud](https://share.streamlit.io), click **Deploy an
   app**, select the repo, and set the entrypoint to `app.py`.
3. Set the `DATABASE_URL` secret (Settings → Secrets).
4. Share the app URL with collaborators.

Note: free apps sleep after a period of inactivity and wake on the next visit.

### Path B — Hugging Face Spaces (requires a paid subscription)

Docker Spaces require a Hugging Face **PRO** or **Team** subscription, which is
recurring (not a one-time cost).

1. Create a Space with the **Docker** SDK, connected to this GitHub repo.
2. In the Space's `README.md`, set `sdk: docker` and `app_port: 7860`.
3. Set the `DATABASE_URL` secret (Settings → Variables and secrets).
4. Keep the Space **private** during development; make it public when the paper
   is submitted.

### Path C — Azure (permanent, uses an existing subscription)

Build the provided `Dockerfile` on Azure Container Apps or Azure App Service
(Linux), reusing your existing Azure Database for PostgreSQL.

1. Build and push the image to Azure Container Registry.
2. Create a Container App or App Service (Linux) from that image.
3. Set the `DATABASE_URL` environment variable to your Azure Postgres.
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
