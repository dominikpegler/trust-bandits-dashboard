# DB Migration Memo: DuckDB + Azure Blob for the Trust-Bandits Dashboard

Date: 2026-08-11
Status: Recommendation (Option 1)

## Summary

The dashboard's managed PostgreSQL (Azure B1ms, ~EUR 15/mo) is a read-only
serving layer for static simulation aggregates. It is over-provisioned for the
workload: read-heavy, sporadic traffic, long idle periods, and it suffers CPU
credit throttling and IOPS limits on the burstable tier. This memo evaluates
four alternatives and recommends replacing Postgres with a compact DuckDB file
stored in Azure Blob Storage.

## Recommendation

**Option 1 (DuckDB + Azure Blob) is the best fit.** It offers the lowest
latency, near-zero cost, and the least maintenance for a static, read-only
research dataset. The dashboard's data is already Parquet at the source, so no
conversion is needed for most tables; the base-model trial-level data is
pre-aggregated at export time.

**Option 4 (Neon/Supabase) is the fallback** if the team rejects the refactor:
it keeps Postgres and needs almost no SQL change, at EUR 0-5/mo, but keeps
network latency and adds cross-cloud latency with the Streamlit host.

Options 2 and 3 are rejected: both force a full T-SQL dialect rewrite (high
effort) with worse latency than DuckDB (serverless auto-pause wakes in minutes;
Basic 5 DTU has the same IOPS ceiling as today's B1ms plus a 2 GB storage cap).

## Options comparison

| Option | Effort | Est. cost/mo | Query latency | Key risk |
|---|---|---|---|---|
| 1. DuckDB + Blob | Medium | < EUR 1 | Fastest (in-memory) | Cold-start Blob download; ephemeral host FS |
| 2. Azure SQL Serverless | High (T-SQL rewrite) | EUR 2-10 | Poor on cold start (minutes) | Auto-pause wake latency |
| 3. Azure SQL Basic 5 DTU | High (T-SQL rewrite) | ~EUR 4.90 | Weak, same IOPS ceiling | 2 GB storage cap |
| 4. Neon/Supabase | Lowest (no SQL change) | EUR 0-5 | Good (network DB) | Cross-cloud latency; small free tier |

## PoC benchmark

Same queries, local Postgres (localhost:5433) vs a 36.2 MB DuckDB file, median
of 5 runs.

| Query | Postgres | DuckDB | Speedup |
|---|---|---|---|
| base_heatmap_cells | 4.1 ms | 1.8 ms | 2.3x |
| per_run_ci | 12.2 ms | 1.2 ms | 10x |
| base_difficulty_data | 29.9 ms | 3.7 ms | 8x |
| extension_heatmap_cells | 1.4 ms | 1.2 ms | 1.2x |
| trajectory_data | 282.4 ms | 3.2 ms | 88x |
| base_condition_error_trace | 2176.4 ms | 3.1 ms | 700x |

The two heaviest queries are the ones backed by the raw 6.4M-row `trials` table.
Pre-aggregating them at export time (into `base_trajectories` and
`base_error_traces_agg`) removes the per-request aggregation cost entirely.

## Cost estimate

- Azure Blob Storage: ~36 MB file, negligible (well under EUR 1/mo, effectively
  free at this scale).
- No compute, no 24/7 server, no CPU credits, no IOPS limits.
- The Azure Postgres B1ms (~EUR 15/mo) is decommissioned.

## Implementation

1. `scripts/export_duckdb.py` reads the raw sources, pre-aggregates base-model
   dynamics, writes one `trust_bandits.duckdb` file, and uploads it to Blob.
2. `dashboard/backends.py` provides a pluggable backend (`DATA_BACKEND=postgres`
   for dev/tests, `DATA_BACKEND=duckdb` for deploy). `dashboard/db.py` delegates
   `fetch_df` to the active backend.
3. `dashboard/loaders.py` reads the pre-aggregated `base_trajectories` and
   `base_error_traces_agg` tables, with a fallback to the raw `trials`
   computation for the Postgres dev database.
4. On Azure, the `.duckdb` file is baked into the container image (zero cold
   start); Blob is the canonical artifact store and the fallback for Streamlit
   Community Cloud (which has an ephemeral filesystem).

## Data footprint

The DuckDB file is 36.2 MB, far smaller than the raw ~12.6 GB of per-trial
sweep Parquet, because the dashboard-facing tables are pre-aggregated. The raw
6.4M-row `trials` table and the dead `base_error_traces` table are not
exported.

## Verification

- `pytest tests/ -q` passes against both backends (16 tests each).
- `ast.parse` smoke check passes.
- Manual Streamlit click-through on all five pages.

## Open items

- Blob container name/region and SAS token vs managed identity on Azure.
- Whether `runs` (128k rows) stays as-is (it is already run-level; kept as-is).
- Error-locked trace window is fixed at export time (default 10).
