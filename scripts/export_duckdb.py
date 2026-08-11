"""One-shot exporter: build a compact DuckDB file from the raw simulation data.

This is the DuckDB/Parquet replacement for the managed PostgreSQL database
(Option 1 of the DB-migration memo). It reads the same raw sources as
``scripts/ingest.py`` and writes a single ``.duckdb`` file containing every
dashboard table, then optionally uploads it to Azure Blob Storage.

Unlike the Postgres ingest, the base-model trial-level data (the 6.4M-row
``trials`` table) is **pre-aggregated** into per-trial mean/SD trajectories and
per-offset error-locked traces, mirroring what ``ingest.py`` already does for
the extension models. The raw ``trials`` and the dead ``base_error_traces``
tables are not exported.

Usage
-----
    python scripts/export_duckdb.py [--studies 1 2 3 d5] [--out PATH]
                                    [--upload] [--dry-run]

The raw data is reached via DATA_DIR (or --data-dir). Upload requires
AZURE_BLOB_CONNECTION_STRING (or AZURE_BLOB_ACCOUNT_URL + AZURE_BLOB_CREDENTIAL)
and AZURE_BLOB_CONTAINER (default ``trust-bandits``).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# Allow running as a plain script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard.config import data_dir  # noqa: E402
from scripts.ingest import (  # noqa: E402
    _build_base_cost_runs,
    _build_conditions,
    _build_d5_runs,
    _build_extension_condition_aggregates,
    _build_extension_trajectories,
    _build_hysteresis,
    _build_hysteresis_trajectories,
    _build_runs_study1,
    _collect_model_meta,
)

STEADY_STATE_DIVISOR = 2

# Base-model per-trial metrics (source column -> output column).
_TRAJ_METRICS = {
    "p_expert": "p_expert",
    "trust_expert": "trust_expert",
    "trust_peers": "trust_peers",
    "correct_expert": "acc_expert",
    "correct_peers": "acc_peers",
}

# Error-locked trace window and per-source event cap (matches the current
# dashboard defaults in dashboard/loaders.py).
ERROR_WINDOW = 10
MAX_EVENTS_PER_SOURCE = 1000


def _build_base_trajectories(raw: Path) -> pd.DataFrame:
    """Per-trial mean/SD trajectories for the base model.

    Mirrors ``_build_extension_trajectories`` but for the base-model multi
    condition CSVs. Returns one row per (condition_key, trial) with per-trial
    means/SDs and an ``n_runs`` count.
    """
    frames = []
    for fb in ("full", "partial"):
        p = raw / "basemodel" / f"df_b1_b2_multi_{fb}.csv"
        if not p.exists():
            print(f"  [skip] {p} not found")
            continue
        print(f"  reading {p} (base trajectories)...")
        usecols = ["mu_E", "c_pen", "run_id", "trial"] + list(_TRAJ_METRICS.keys())
        df = pd.read_csv(p, usecols=usecols)
        keys = ["mu_E", "c_pen", "trial"]
        for src, out in _TRAJ_METRICS.items():
            df[f"sum_{out}"] = df[src]
            df[f"sumsq_{out}"] = df[src] ** 2
        agg_dict = {"run_id": "count"}
        for out in _TRAJ_METRICS.values():
            agg_dict[f"sum_{out}"] = "sum"
            agg_dict[f"sumsq_{out}"] = "sum"
        part = df.groupby(keys).agg(agg_dict).reset_index()
        part["feedback_mode"] = fb
        frames.append(part)
        del df, part
    if not frames:
        return pd.DataFrame()
    total = pd.concat(frames, ignore_index=True).groupby(
        ["mu_E", "c_pen", "feedback_mode", "trial"]
    ).sum(numeric_only=True).reset_index()
    total = total.rename(columns={"run_id": "n_runs"})
    for out in sorted(set(_TRAJ_METRICS.values())):
        n = total["n_runs"].clip(lower=1)
        total[f"mean_{out}"] = total[f"sum_{out}"] / n
        variance = (total[f"sumsq_{out}"] - (total[f"sum_{out}"] ** 2) / n) / (n - 1).replace(0, np.nan)
        total[f"sd_{out}"] = np.sqrt(variance.clip(lower=0)).fillna(0.0)
    keep = [
        "mu_E", "c_pen", "feedback_mode", "trial", "n_runs",
        "mean_p_expert", "sd_p_expert", "mean_trust_expert", "sd_trust_expert",
        "mean_trust_peers", "sd_trust_peers", "mean_acc_expert", "sd_acc_expert",
        "mean_acc_peers", "sd_acc_peers",
    ]
    total = total[keep]
    total.columns = [c.lower() for c in total.columns]
    return total


def _build_base_error_traces_agg(raw: Path) -> pd.DataFrame:
    """Pre-aggregated error-locked trust traces for the base model.

    For each condition and source, trust is baseline-normalized relative to the
    trust value at each error event and tracked over +/- ``ERROR_WINDOW``
    trials. Events are capped per source. Returns one row per
    (condition_key, source, offset) with the mean/SD/count of normalized trust,
    which is exactly what the dashboard's error-locked figure needs.
    """
    frames = []
    for fb in ("full", "partial"):
        p = raw / "basemodel" / f"df_b1_b2_multi_{fb}.csv"
        if not p.exists():
            print(f"  [skip] {p} not found")
            continue
        print(f"  reading {p} (base error-locked traces)...")
        usecols = ["mu_E", "c_pen", "run_id", "trial",
                   "trust_expert", "trust_peers", "correct_expert", "correct_peers"]
        df = pd.read_csv(p, usecols=usecols)
        for src, err_col, trust_col in (
            ("Expert", "correct_expert", "trust_expert"),
            ("Peers", "correct_peers", "trust_peers"),
        ):
            events = df[df[err_col] == 0][["mu_E", "c_pen", "run_id", "trial", trust_col]]
            events = events.groupby(["mu_E", "c_pen", "run_id"]).head(MAX_EVENTS_PER_SOURCE)
            if events.empty:
                continue
            ev = events.rename(columns={"trial": "ev_trial", trust_col: "baseline"})
            merged = df.merge(
                ev[["mu_E", "c_pen", "run_id", "ev_trial", "baseline"]],
                on=["mu_E", "c_pen", "run_id"],
                how="inner",
            )
            merged = merged[
                (merged["trial"] >= merged["ev_trial"] - ERROR_WINDOW)
                & (merged["trial"] <= merged["ev_trial"] + ERROR_WINDOW)
            ]
            merged["trial_offset"] = merged["trial"] - merged["ev_trial"]
            merged["trust_norm"] = merged[trust_col] - merged["baseline"]
            merged["source"] = src
            agg = (
                merged.groupby(["mu_E", "c_pen", "source", "trial_offset"])["trust_norm"]
                .agg(mean_trust_norm="mean", sd_trust_norm="std", n_events="count")
                .reset_index()
            )
            agg["feedback_mode"] = fb
            frames.append(agg)
            del events, ev, merged, agg
    if not frames:
        return pd.DataFrame()
    total = pd.concat(frames, ignore_index=True)
    total.columns = [c.lower() for c in total.columns]
    return total


def _expand_studies(studies: list[str]) -> list[str]:
    """Expand the ``d5`` shorthand into the per-model d5 study keys."""
    out = []
    for s in studies:
        if s == "d5":
            out.extend(["d5-1", "d5-2", "d5-3"])
        else:
            out.append(s)
    return out


def _assign_condition_ids(conditions: pd.DataFrame) -> pd.DataFrame:
    """Add a stable ``id`` column keyed on the schema's unique key.

    Named ``id`` to match the Postgres ``conditions`` schema, since loaders
    join ``conditions.id = runs.condition_id``.
    """
    key = ["study", "evaluation_mode", "regime", "feedback_mode", "mu_e", "c_pen",
           "expert_inertia_divisor", "clustering", "rho_peers"]
    cond = conditions.copy()
    cond["id"] = np.arange(1, len(cond) + 1)
    return cond


def _resolve_condition_ids(df: pd.DataFrame, conditions: pd.DataFrame) -> pd.DataFrame:
    """Map a per-run frame to ``condition_id`` via the conditions unique key."""
    key = ["study", "evaluation_mode", "regime", "feedback_mode", "mu_e", "c_pen",
           "expert_inertia_divisor", "clustering", "rho_peers"]
    cond_key = conditions[["id"] + key]
    for k in key:
        if k in df.columns and df[k].dtype == object:
            df[k] = pd.to_numeric(df[k], errors="coerce")
        if k in cond_key.columns and cond_key[k].dtype == object:
            cond_key[k] = pd.to_numeric(cond_key[k], errors="coerce")
    merged = df.merge(cond_key, on=key, how="left")
    merged = merged.rename(columns={"id": "condition_id"})
    merged["condition_id"] = merged["condition_id"].astype(int)
    return merged.drop(columns=key)


def _write_duckdb(out: Path, tables: dict[str, pd.DataFrame]) -> None:
    import duckdb

    if out.exists():
        out.unlink()
    con = duckdb.connect(str(out))
    try:
        for name, df in tables.items():
            if df is None or df.empty:
                print(f"  [skip] {name}: empty")
                continue
            con.register(f"df_{name}", df)
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM df_{name}")
            print(f"  wrote {name}: {len(df)} rows")
    finally:
        con.close()


def _upload_blob(out: Path) -> None:
    from dashboard.blobstore import BLOB_NAME, CONTAINER, get_container_client

    blob = get_container_client().get_blob_client(BLOB_NAME)
    with open(out, "rb") as f:
        blob.upload_blob(f, overwrite=True)
    print(f"  uploaded {out.name} -> {CONTAINER}/{BLOB_NAME}")


def run(args) -> None:
    out = Path(args.out).expanduser()

    # Skip the (slow) rebuild when the file already exists and the operator only
    # wants to push the current artifact to Blob.
    if args.upload_only:
        if not out.exists():
            raise SystemExit(
                f"--upload-only but no file at {out}; run without --upload-only to build it"
            )
        print(f"uploading existing file -> {out}")
        _upload_blob(out)
        return

    ddir = data_dir()
    pub = ddir / "pub"
    raw = ddir / "data"
    studies = [s for s in args.studies]

    t0 = time.perf_counter()
    print("building conditions...")
    conditions = _build_conditions(studies, pub)
    conditions = _assign_condition_ids(conditions)
    print(f"  conditions: {len(conditions)} rows")

    tables: dict[str, pd.DataFrame] = {"conditions": conditions}

    if "1" in studies:
        print("building runs...")
        runs = _build_runs_study1(raw)
        runs = _resolve_condition_ids(runs, conditions)
        tables["runs"] = runs
        print(f"  runs: {len(tables['runs'])} rows")
        print("building base_cost_runs...")
        tables["base_cost_runs"] = _build_base_cost_runs(raw)
        print(f"  base_cost_runs: {len(tables['base_cost_runs'])} rows")
        print("building base_trajectories...")
        tables["base_trajectories"] = _build_base_trajectories(raw)
        print(f"  base_trajectories: {len(tables['base_trajectories'])} rows")
        print("building base_error_traces_agg...")
        tables["base_error_traces_agg"] = _build_base_error_traces_agg(raw)
        print(f"  base_error_traces_agg: {len(tables['base_error_traces_agg'])} rows")

    if "d5" in studies or "1" in studies:
        print("building d5_runs...")
        tables["d5_runs"] = _build_d5_runs(raw, pub)
        print(f"  d5_runs: {len(tables['d5_runs'])} rows")

    if "2" in studies or "3" in studies:
        print("building extension_condition_aggregates...")
        tables["extension_condition_aggregates"] = _build_extension_condition_aggregates(raw)
        print(f"  extension_condition_aggregates: {len(tables['extension_condition_aggregates'])} rows")
        print("building extension_trajectories...")
        tables["extension_trajectories"] = _build_extension_trajectories(raw)
        print(f"  extension_trajectories: {len(tables['extension_trajectories'])} rows")
        print("building hysteresis...")
        tables["hysteresis"] = _build_hysteresis(pub)
        print(f"  hysteresis: {len(tables['hysteresis'])} rows")
        print("building hysteresis_trajectories...")
        tables["hysteresis_trajectories"] = _build_hysteresis_trajectories(raw)
        print(f"  hysteresis_trajectories: {len(tables['hysteresis_trajectories'])} rows")

    model_meta_rows = _collect_model_meta(_expand_studies(studies), pub)
    if model_meta_rows:
        model_meta_df = pd.DataFrame(model_meta_rows)
        model_meta_df["design"] = model_meta_df["design"].apply(json.dumps)
        tables["model_meta"] = model_meta_df
        print(f"  model_meta: {len(model_meta_df)} rows")

    ingest_meta = pd.DataFrame([{
        "ingest_timestamp": pd.Timestamp.utcnow(),
        "source_git_sha": "duckdb-export",
        "studies": ",".join(studies),
        "row_counts": json.dumps({k: len(v) for k, v in tables.items()}),
        "source_checksums": None,
    }])
    tables["ingest_meta"] = ingest_meta

    if args.dry_run:
        print("\n[DRY RUN] no file written.")
        for k, v in tables.items():
            print(f"  {k}: {len(v)} rows")
        return

    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"\nwriting DuckDB file -> {out}")
    _write_duckdb(out, tables)
    size_mb = out.stat().st_size / 1e6
    print(f"  file size: {size_mb:.1f} MB")
    print(f"  build time: {time.perf_counter() - t0:.1f}s")

    if args.upload:
        print("uploading to Azure Blob...")
        _upload_blob(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--studies",
        nargs="*",
        default=["1", "2", "3", "d5"],
        help="Studies to export. Default: all.",
    )
    parser.add_argument(
        "--out",
        default="data/trust_bandits.duckdb",
        help="Output .duckdb path (default: data/trust_bandits.duckdb).",
    )
    parser.add_argument("--upload", action="store_true", help="Upload to Azure Blob after writing.")
    parser.add_argument(
        "--upload-only",
        action="store_true",
        help="Skip the rebuild and just upload the existing --out file to Azure Blob.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be exported, do not write.")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
