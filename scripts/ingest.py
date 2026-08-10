"""One-shot loader: reset-and-refill the dashboard database from raw data.

Usage
-----
    python scripts/ingest.py [--reset] [--studies 1 2 3 d5] [--dry-run]
                             [--skip-trials] [--conn-url URL]

Behaviour
---------
* Reads sources from the analysis repo's data directory (DATA_DIR env or
  --data-dir). By default only the pre-aggregated JSON files and small summary
  CSVs are read for the `conditions` and `runs` tables; trial-level data is
  loaded for `trials` from the base-model multi-condition CSVs (use
  --skip-trials to leave `trials` empty, which is fine for the heatmap pages).
* Atomic reset-and-refill: everything is loaded into `_staging_*` tables,
  then in a single transaction the live tables are truncated and repopulated
  from staging, and staging is dropped. Readers never observe a partial DB.
* Writes an `ingest_meta` row (timestamp, git SHA, row counts, checksums).

The database is reached via DATABASE_URL (or the AZURE_PG_* env vars / local
defaults). Run this on a machine that has access to the raw data (e.g. your
laptop with the Dropbox folder mounted).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Allow running as a plain script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard import db  # noqa: E402
from dashboard.config import data_dir  # noqa: E402

STUDY1 = ["1"]
STUDIES_23 = ["2", "3"]
D5 = ["d5"]
ALL_STUDIES = STUDY1 + STUDIES_23 + D5

STEADY_STATE_DIVISOR = 2  # second half of trials == steady state


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(pub: Path, name: str) -> dict:
    p = pub / name
    if not p.exists():
        print(f"  [skip] {p} not found")
        return {}
    with open(p) as f:
        return json.load(f)


def _source_block(d: dict, name: str) -> dict:
    """Read a renamed D-block, falling back to legacy raw-data keys."""
    legacy = name.replace("d5", "b" + "5")
    return d.get(name) or d.get(legacy, {})

def _source_file(*candidates: Path) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _collect_model_meta(studies: list[str], pub: Path) -> list[dict]:
    """Capture the fixed `design` block for each study being ingested.

    Returns a list of {"study", "design", "source"} dicts for model_meta.
    Study 1 and d5-1 come from the base-model study JSON; studies 2/3 from the
    extension study JSONs; d5-2/d5-3 inherit the design of their base model.
    """
    rows: list[dict] = []
    base_json = pub / "basemodel" / "study_1.json"
    base_d = _load_json(pub, "basemodel/study_1.json")
    base_design = base_d.get("design", {})

    for s in studies:
        if s == "1":
            rows.append({"study": "1", "design": base_design, "source": str(base_json)})
        elif s == "d5-1":
            d5_design = dict(base_design)
            d5_design.update(_source_block(base_d, "d5"))
            rows.append({"study": "d5-1", "design": d5_design, "source": str(base_json)})
        elif s in ("2", "3"):
            p = pub / "extensions" / f"study_{s}.json"
            d = _load_json(pub, f"extensions/study_{s}.json")
            rows.append({"study": s, "design": d.get("design", {}), "source": str(p)})
        elif s in ("d5-2", "d5-3"):
            base = s.split("-")[1]
            p = pub / "extensions" / f"study_{base}.json"
            d = _load_json(pub, f"extensions/study_{base}.json")
            d5_design = dict(d.get("design", {}))
            d5_design.update(_source_block(d, f"d5_{'memory' if base == '2' else 'graded'}"))
            rows.append({"study": s, "design": d5_design, "source": str(p)})
    return rows


# --------------------------------------------------------------------------
# conditions (aggregates)
# --------------------------------------------------------------------------
def _build_study1_conditions(d: dict) -> pd.DataFrame:
    n_runs = d.get("n_repetitions")
    rows = []
    for key, v in d.get("conditions", {}).items():
        rows.append(
            {
                "study": "1",
                "evaluation_mode": "binary",
                "regime": "stationary",
                "feedback_mode": v.get("feedback_mode"),
                "mu_E": v.get("mu_E"),
                "c_pen": v.get("c_pen"),
                "expert_inertia_divisor": None,
                "clustering": 0.0,
                "rho_peers": 0.0,
                "n_runs": n_runs,
                "mean_p_expert": v.get("mean_p_expert"),
                "sd_p_expert": v.get("sd_p_expert"),
                "mean_acc_expert": v.get("mean_acc_expert"),
                "sd_acc_expert": v.get("sd_acc_expert"),
                "mean_acc_peers": v.get("mean_acc_peers"),
                "sd_acc_peers": v.get("sd_acc_peers"),
                "mean_trust_expert": v.get("mean_trust_expert"),
                "sd_trust_expert": v.get("sd_trust_expert"),
                "mean_trust_peers": v.get("mean_trust_peers"),
                "sd_trust_peers": v.get("sd_trust_peers"),
                "mean_p_expert_ss": v.get("mean_p_expert_ss"),
                "sd_p_expert_ss": v.get("sd_p_expert_ss"),
                "mean_acc_expert_ss": v.get("mean_acc_expert_ss"),
                "sd_acc_expert_ss": v.get("sd_acc_expert_ss"),
                "mean_acc_peers_ss": v.get("mean_acc_peers_ss"),
                "sd_acc_peers_ss": v.get("sd_acc_peers_ss"),
                "mean_trust_expert_ss": v.get("mean_trust_expert_ss"),
                "sd_trust_expert_ss": v.get("sd_trust_expert_ss"),
                "mean_trust_peers_ss": v.get("mean_trust_peers_ss"),
                "sd_trust_peers_ss": v.get("sd_trust_peers_ss"),
            }
        )
    # D5 sub-block (echo-chamber), distinct study key so it does not collide
    # with the base (mu_E=0.65, c_pen=6.0, clustering=0, rho=0) condition.
    for key, v in _source_block(d, "d5").items():
        if not isinstance(v, dict):
            continue
        rows.append(
            {
                "study": "d5-1",
                "evaluation_mode": "binary",
                "regime": "stationary",
                "feedback_mode": v.get("feedback_mode"),
                "mu_E": 0.65,  # D5 uses the default difficulty
                "c_pen": 6.0,
                "expert_inertia_divisor": None,
                "clustering": v.get("clustering"),
                "rho_peers": v.get("rho_peers"),
                "mean_p_expert": v.get("p_expert_mean"),
                "sd_p_expert": v.get("p_expert_sd"),
                "mean_acc_expert": v.get("acc_expert"),
                "mean_acc_peers": v.get("acc_peers"),
                "frac_low": v.get("frac_low"),
                "frac_high": v.get("frac_high"),
                "n_runs": v.get("n_runs"),
                "gap": v.get("gap"),
            }
        )
    return pd.DataFrame(rows)


def _build_study23_conditions(d: dict, study: str, mode: str) -> pd.DataFrame:
    n_runs = d.get("n_repetitions_sweep")
    rows = []
    for key, v in d.get("conditions", {}).items():
        rows.append(
            {
                "study": study,
                "evaluation_mode": mode,
                "regime": "cyclic",
                "feedback_mode": v.get("feedback_mode"),
                "mu_E": d.get("design", {}).get("mu_E_default"),
                "c_pen": v.get("c_pen"),
                "expert_inertia_divisor": v.get("expert_inertia_divisor"),
                "clustering": 0.0,
                "rho_peers": 0.0,
                "n_runs": n_runs,
                "mean_p_expert": v.get("mean_p_expert"),
                "sd_p_expert": v.get("sd_p_expert"),
                "mean_acc_expert": v.get("mean_acc_expert"),
                "mean_acc_peers": v.get("mean_acc_peers"),
                "mean_trust_expert": v.get("mean_trust_expert"),
                "mean_trust_peers": v.get("mean_trust_peers"),
                "mean_p_expert_ss": v.get("mean_p_expert_ss"),
                "sd_p_expert_ss": v.get("sd_p_expert_ss"),
                "mean_acc_expert_ss": v.get("mean_acc_expert_ss"),
                "sd_acc_expert_ss": v.get("sd_acc_expert_ss"),
                "mean_acc_peers_ss": v.get("mean_acc_peers_ss"),
                "sd_acc_peers_ss": v.get("sd_acc_peers_ss"),
                "mean_trust_expert_ss": v.get("mean_trust_expert_ss"),
                "mean_trust_peers_ss": v.get("mean_trust_peers_ss"),
                "mean_acc_expert_cont": v.get("mean_acc_expert_cont"),
                "mean_acc_peers_cont": v.get("mean_acc_peers_cont"),
                "mean_acc_expert_cont_ss": v.get("mean_acc_expert_cont_ss"),
                "mean_acc_peers_cont_ss": v.get("mean_acc_peers_cont_ss"),
            }
        )
    return pd.DataFrame(rows)


def _build_d5_conditions(d5_json: dict, study: str, mode: str) -> pd.DataFrame:
    rows = []
    for key, v in d5_json.items():
        if not isinstance(v, dict):
            continue
        rows.append(
            {
                "study": study,
                "evaluation_mode": mode,
                "regime": "stationary",
                "feedback_mode": v.get("feedback_mode"),
                "mu_E": 0.65,
                "c_pen": 6.0,
                "expert_inertia_divisor": None,
                "clustering": v.get("clustering"),
                "rho_peers": v.get("rho_peers"),
                "mean_p_expert": v.get("p_expert_mean"),
                "sd_p_expert": v.get("p_expert_sd"),
                "mean_acc_expert": v.get("acc_expert"),
                "mean_acc_peers": v.get("acc_peers"),
                "frac_low": v.get("frac_low"),
                "frac_high": v.get("frac_high"),
                "n_runs": v.get("n_runs"),
                "gap": v.get("gap"),
            }
        )
    return pd.DataFrame(rows)


def _build_conditions(studies: list[str], pub: Path) -> pd.DataFrame:
    frames = []
    if "1" in studies:
        d = _load_json(pub, "basemodel/study_1.json")
        if d:
            frames.append(_build_study1_conditions(d))
    for s, mode in (("2", "binary"), ("3", "continuous")):
        if s in studies:
            d = _load_json(pub, f"extensions/study_{s}.json")
            if d:
                frames.append(_build_study23_conditions(d, s, mode))
    if "d5" in studies:
        for s, fname, mode in (
            ("2", "study_2.json", "binary"),
            ("3", "study_3.json", "continuous"),
        ):
            d = _load_json(pub, f"extensions/{fname}")
            memory = _source_block(d, "d5_memory") if d else {}
            graded = _source_block(d, "d5_graded") if d else {}
            if memory:
                frames.append(_build_d5_conditions(memory, f"d5-{s}", mode))
            if graded:
                frames.append(_build_d5_conditions(graded, f"d5-{s}", mode))
        d1 = _load_json(pub, "basemodel/study_1.json")
        base_d5 = _source_block(d1, "d5") if d1 else {}
        if base_d5:
            frames.append(_build_d5_conditions(base_d5, "d5-1", "binary"))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df.columns = [c.lower() for c in df.columns]
    if "n_runs" in df.columns:
        df["n_runs"] = pd.to_numeric(df["n_runs"], errors="coerce").astype("Int64")
    # Deduplicate on the schema's unique key. The d5-1 rows are added both from
    # study_1.json's own D5 block and from the study-1 builder, so drop any
    # exact duplicates to keep the count consistent with the unique constraint.
    key = ["study", "evaluation_mode", "regime", "feedback_mode", "mu_e", "c_pen",
           "expert_inertia_divisor", "clustering", "rho_peers"]
    df = df.drop_duplicates(subset=key, keep="first")
    return df


# --------------------------------------------------------------------------
# runs (per-run means) for the base model from the multi-condition CSVs
# --------------------------------------------------------------------------
_PER_RUN_COLS = {
    "mean_p_expert": "p_expert",
    "mean_trust_expert": "trust_expert",
    "mean_trust_peers": "trust_peers",
    "mean_acc_expert": "correct_expert",
    "mean_acc_peers": "correct_peers",
}


def _build_runs_study1(raw: Path) -> pd.DataFrame:
    frames = []
    for fb in ("full", "partial"):
        p = _source_file(
            raw / "basemodel" / f"df_d1_d2_multi_{fb}.csv",
            raw / "basemodel" / f"df_{'b' + '1'}_{'b' + '2'}_multi_{fb}.csv",
        )
        if not p.exists():
            print(f"  [skip] {p} not found")
            continue
        print(f"  reading {p} (per-run aggregation)...")
        src_cols = ["mu_E", "c_pen", "run_id", "trial"] + list(_PER_RUN_COLS.values())
        df = pd.read_csv(p, usecols=src_cols)
        cutoff = df["trial"].max() // STEADY_STATE_DIVISOR
        half = df[df["trial"] > cutoff]
        agg_full = (
            df.groupby(["mu_E", "c_pen", "run_id"])
            .agg({v: "mean" for v in _PER_RUN_COLS.values()})
            .reset_index()
            .rename(columns={v: k for k, v in _PER_RUN_COLS.items()})
        )
        agg_half = (
            half.groupby(["mu_E", "c_pen", "run_id"])
            .agg({v: "mean" for v in _PER_RUN_COLS.values()})
            .reset_index()
            .rename(columns={v: f"{k}_ss" for k, v in _PER_RUN_COLS.items()})
        )
        m = agg_full.merge(agg_half, on=["mu_E", "c_pen", "run_id"], how="left")
        m["feedback_mode"] = fb
        m["study"] = "1"
        m["evaluation_mode"] = "binary"
        m["regime"] = "stationary"
        m["expert_inertia_divisor"] = None
        m["clustering"] = 0.0
        m["rho_peers"] = 0.0
        m.columns = [c.lower() for c in m.columns]
        frames.append(m)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# --------------------------------------------------------------------------
# trials (trial-level) for the base model
# --------------------------------------------------------------------------
_TRIAL_COLS = {
    "p_expert": "p_expert",
    "trust_expert": "trust_expert",
    "trust_peers": "trust_peers",
    "acc_expert": "correct_expert",
    "acc_peers": "correct_peers",
}


def _build_trials_study1(raw: Path) -> pd.DataFrame:
    frames = []
    for fb in ("full", "partial"):
        p = _source_file(
            raw / "basemodel" / f"df_d1_d2_multi_{fb}.csv",
            raw / "basemodel" / f"df_{'b' + '1'}_{'b' + '2'}_multi_{fb}.csv",
        )
        if not p.exists():
            continue
        print(f"  reading {p} (trial-level)...")
        df = pd.read_csv(
            p,
            usecols=["mu_E", "c_pen", "run_id", "trial", "evidence_majority",
                     "evidence_proportion", "chosen_source", "correct_expert",
                     "correct_peers", "p_expert", "trust_expert", "trust_peers"],
        )
        df = df.rename(columns={"correct_expert": "acc_expert", "correct_peers": "acc_peers"})
        df["evaluation_mode"] = "binary"
        df["regime"] = "stationary"
        df["expert_inertia_divisor"] = None
        df["clustering"] = 0.0
        df["rho_peers"] = 0.0
        df["feedback_mode"] = fb
        df["study"] = "1"
        df.columns = [c.lower() for c in df.columns]
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _build_base_cost_runs(raw: Path) -> pd.DataFrame:
    """Base-model cognitive-cost sweep (D3), one row per run x cost."""
    p = _source_file(
        raw / "basemodel" / "df_d3.csv",
        raw / "basemodel" / f"df_{'b' + '3'}.csv",
    )
    if not p.exists():
        print(f"  [skip] {p} not found")
        return pd.DataFrame()
    print(f"  reading {p} (base cost sweep)...")
    df = pd.read_csv(p)
    df.columns = [c.lower() for c in df.columns]
    return df[[
        "feedback_mode", "run_id", "cost_w_n", "cost_w_var", "cost_sum",
        "mean_p_expert", "mean_acc_expert", "mean_acc_peers",
    ]]


def _build_base_error_traces(raw: Path) -> pd.DataFrame:
    """Base-model error-locked trust traces (D1)."""
    p = _source_file(
        raw / "basemodel" / "df_d1_details.csv",
        raw / "basemodel" / f"df_{'b' + '1'}_details.csv",
    )
    if not p.exists():
        print(f"  [skip] {p} not found")
        return pd.DataFrame()
    print(f"  reading {p} (base error-locked traces)...")
    df = pd.read_csv(p)
    df.columns = [c.lower() for c in df.columns]
    df = df.rename(columns={"offset": "trial_offset"})
    return df[[
        "feedback_mode", "run_id", "event_iter", "trial_offset", "source",
        "trust", "baseline", "trust_norm",
    ]]


def _build_extension_condition_aggregates(raw: Path) -> pd.DataFrame:
    """Condition-level extension aggregates preserving mu_E x d_T x c_pen.

    Reads parquet chunks for binary/continuous and stationary/cyclic regimes,
    aggregates first to run level (full range and second half), then to condition
    level. This is the data needed for the paper's three extension heatmaps.
    """
    frames = []
    for evaluation_mode, study in (("binary", "2"), ("continuous", "3")):
        for regime in ("stationary", "cyclic"):
            chunks_dir = raw / "extensions" / f"sweep_chunks_{evaluation_mode}_{regime}"
            files = sorted(chunks_dir.glob("chunk_*.parquet"))
            if not files:
                print(f"  [skip] no chunks in {chunks_dir}")
                continue
            print(f"  reading {chunks_dir} ({len(files)} chunks; extension aggregates)...")
            run_parts = []
            base_cols = [
                "trial", "mu_E_init", "expert_inertia_divisor", "c_pen",
                "feedback_mode", "run_id", "p_expert", "trust_expert", "trust_peers",
            ]
            if evaluation_mode == "binary":
                metric_cols = ["correct_expert", "correct_peers"]
            else:
                metric_cols = [
                    "correct_expert_bin", "correct_peers_bin",
                    "correct_expert_cont", "correct_peers_cont",
                ]
            usecols = base_cols + metric_cols
            for f in files:
                chunk = pd.read_parquet(f, columns=usecols)
                cutoff = int(chunk["trial"].max()) // STEADY_STATE_DIVISOR
                keys = ["mu_E_init", "expert_inertia_divisor", "c_pen", "feedback_mode", "run_id"]
                agg_map = {
                    "p_expert": "mean",
                    "trust_expert": "mean",
                    "trust_peers": "mean",
                }
                if evaluation_mode == "binary":
                    agg_map.update({"correct_expert": "mean", "correct_peers": "mean"})
                else:
                    agg_map.update({
                        "correct_expert_bin": "mean",
                        "correct_peers_bin": "mean",
                        "correct_expert_cont": "mean",
                        "correct_peers_cont": "mean",
                    })
                full = chunk.groupby(keys).agg(agg_map).reset_index()
                full = full.rename(columns={
                    "p_expert": "mean_p_expert",
                    "trust_expert": "mean_trust_expert",
                    "trust_peers": "mean_trust_peers",
                    "correct_expert": "mean_acc_expert",
                    "correct_peers": "mean_acc_peers",
                    "correct_expert_bin": "mean_acc_expert",
                    "correct_peers_bin": "mean_acc_peers",
                    "correct_expert_cont": "mean_acc_expert_cont",
                    "correct_peers_cont": "mean_acc_peers_cont",
                })
                half_chunk = chunk[chunk["trial"] > cutoff]
                half = half_chunk.groupby(keys).agg(agg_map).reset_index()
                half = half.rename(columns={
                    "p_expert": "mean_p_expert_ss",
                    "trust_expert": "mean_trust_expert_ss",
                    "trust_peers": "mean_trust_peers_ss",
                    "correct_expert": "mean_acc_expert_ss",
                    "correct_peers": "mean_acc_peers_ss",
                    "correct_expert_bin": "mean_acc_expert_ss",
                    "correct_peers_bin": "mean_acc_peers_ss",
                    "correct_expert_cont": "mean_acc_expert_cont_ss",
                    "correct_peers_cont": "mean_acc_peers_cont_ss",
                })
                run_parts.append(full.merge(half, on=keys, how="left"))
                del chunk, half_chunk, full, half
            if not run_parts:
                continue
            runs = pd.concat(run_parts, ignore_index=True)
            cond_keys = ["mu_E_init", "expert_inertia_divisor", "c_pen", "feedback_mode"]
            agg_cols = [c for c in runs.columns if c.startswith("mean_")]
            agg_spec = {c: "mean" for c in agg_cols}
            agg_spec["run_id"] = "nunique"
            cond = runs.groupby(cond_keys).agg(agg_spec).reset_index()
            cond = cond.rename(columns={"run_id": "n_runs", "mu_E_init": "mu_e"})
            # Add SDs across run-level p(Expert) means for uncertainty/inspection.
            sd = runs.groupby(cond_keys).agg(
                sd_p_expert=("mean_p_expert", "std"),
                sd_p_expert_ss=("mean_p_expert_ss", "std"),
            ).reset_index().rename(columns={"mu_E_init": "mu_e"})
            cond = cond.merge(sd, on=["mu_e", "expert_inertia_divisor", "c_pen", "feedback_mode"], how="left")
            cond["study"] = study
            cond["evaluation_mode"] = evaluation_mode
            cond["regime"] = regime
            cond["delta_acc"] = cond["mean_acc_expert"] - cond["mean_acc_peers"]
            cond["delta_acc_ss"] = cond["mean_acc_expert_ss"] - cond["mean_acc_peers_ss"]
            cond["is_paradox"] = (cond["delta_acc"] > 0) & (cond["mean_p_expert"] < 0.5)
            cond["is_paradox_ss"] = (cond["delta_acc_ss"] > 0) & (cond["mean_p_expert_ss"] < 0.5)
            frames.append(cond)
            del runs, run_parts
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df.columns = [c.lower() for c in df.columns]
    cols = [
        "study", "evaluation_mode", "regime", "feedback_mode", "mu_e",
        "expert_inertia_divisor", "c_pen", "n_runs", "mean_p_expert", "sd_p_expert",
        "mean_p_expert_ss", "sd_p_expert_ss", "mean_acc_expert", "mean_acc_peers",
        "mean_acc_expert_ss", "mean_acc_peers_ss", "mean_acc_expert_cont",
        "mean_acc_peers_cont", "mean_acc_expert_cont_ss", "mean_acc_peers_cont_ss",
        "mean_trust_expert", "mean_trust_peers", "mean_trust_expert_ss",
        "mean_trust_peers_ss", "delta_acc", "delta_acc_ss", "is_paradox",
        "is_paradox_ss",
    ]
    for c in cols:
        if c not in df.columns:
            df[c] = None
    return df[cols]


def _build_extension_trajectories(raw: Path) -> pd.DataFrame:
    """Per-trial extension aggregates for selected-condition dynamics panels."""
    frames = []
    for evaluation_mode, study in (("binary", "2"), ("continuous", "3")):
        for regime in ("stationary", "cyclic"):
            chunks_dir = raw / "extensions" / f"sweep_chunks_{evaluation_mode}_{regime}"
            files = sorted(chunks_dir.glob("chunk_*.parquet"))
            if not files:
                print(f"  [skip] no chunks in {chunks_dir}")
                continue
            print(f"  reading {chunks_dir} ({len(files)} chunks; extension trajectories)...")
            keys = ["mu_E_init", "expert_inertia_divisor", "c_pen", "feedback_mode", "trial"]
            if evaluation_mode == "binary":
                metrics = {
                    "p_expert": "p_expert",
                    "trust_expert": "trust_expert",
                    "trust_peers": "trust_peers",
                    "correct_expert": "acc_expert",
                    "correct_peers": "acc_peers",
                }
            else:
                metrics = {
                    "p_expert": "p_expert",
                    "trust_expert": "trust_expert",
                    "trust_peers": "trust_peers",
                    "correct_expert_bin": "acc_expert",
                    "correct_peers_bin": "acc_peers",
                }
            usecols = keys + ["run_id"] + list(metrics.keys())
            parts = []
            for f in files:
                chunk = pd.read_parquet(f, columns=usecols)
                for src, out in metrics.items():
                    chunk[f"sum_{out}"] = chunk[src]
                    chunk[f"sumsq_{out}"] = chunk[src] ** 2
                agg_dict = {"run_id": "count"}
                for out in metrics.values():
                    agg_dict[f"sum_{out}"] = "sum"
                    agg_dict[f"sumsq_{out}"] = "sum"
                part = chunk.groupby(keys).agg(agg_dict).reset_index()
                parts.append(part)
                del chunk, part
            if not parts:
                continue
            total = pd.concat(parts, ignore_index=True).groupby(keys).sum(numeric_only=True).reset_index()
            total = total.rename(columns={"run_id": "n_runs", "mu_E_init": "mu_e"})
            for out in sorted(set(metrics.values())):
                n = total["n_runs"].clip(lower=1)
                total[f"mean_{out}"] = total[f"sum_{out}"] / n
                variance = (total[f"sumsq_{out}"] - (total[f"sum_{out}"] ** 2) / n) / (n - 1).replace(0, np.nan)
                total[f"sd_{out}"] = np.sqrt(variance.clip(lower=0)).fillna(0.0)
            total["study"] = study
            total["evaluation_mode"] = evaluation_mode
            total["regime"] = regime
            keep = [
                "study", "evaluation_mode", "regime", "feedback_mode", "mu_e",
                "expert_inertia_divisor", "c_pen", "trial", "n_runs",
                "mean_p_expert", "sd_p_expert", "mean_trust_expert", "sd_trust_expert",
                "mean_trust_peers", "sd_trust_peers", "mean_acc_expert", "sd_acc_expert",
                "mean_acc_peers", "sd_acc_peers",
            ]
            frames.append(total[keep])
            del total, parts
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df.columns = [c.lower() for c in df.columns]
    return df


# --------------------------------------------------------------------------
# d5_runs (per-run steady-state over clustering x rho grid)
# --------------------------------------------------------------------------
def _build_d5_runs(raw: Path, pub: Path) -> pd.DataFrame:
    """Per-run p(Expert)/trust/accuracy over the clustering x rho grid.

    Uses the D5 per-run CSV (base model) plus the D5 memory/graded summary CSVs
    for the extension variants. The perrun CSV holds one row per run; the
    summary CSVs hold per-cell aggregates, so we only load the base-model
    perrun data here (the extension variants are covered by `conditions`).
    """
    p = _source_file(
        raw / "clustering" / "d5_perrun.csv",
        raw / "clustering" / f"{'b' + '5'}_perrun.csv",
    )
    if not p.exists():
        print(f"  [skip] {p} not found")
        return pd.DataFrame()
    print(f"  reading {p} (D5 per-run)...")
    df = pd.read_csv(p)
    df["study"] = "d5-1"
    df["evaluation_mode"] = "binary"
    df.columns = [c.lower() for c in df.columns]
    return df[["study", "evaluation_mode", "feedback_mode", "clustering",
               "rho_peers", "run_id", "p_expert", "trust_expert",
               "trust_peers", "acc_expert", "acc_peers"]]


# --------------------------------------------------------------------------
# hysteresis (baseline vs post-collapse, Studies 2/3)
# --------------------------------------------------------------------------
def _build_hysteresis(pub: Path) -> pd.DataFrame:
    rows = []
    for s, fname, mode in (("2", "study_2.json", "binary"),
                           ("3", "study_3.json", "continuous")):
        d = _load_json(pub, f"extensions/{fname}")
        if not d:
            continue
        for key, v in d.get("hysteresis", {}).items():
            if not isinstance(v, dict):
                continue
            rows.append(
                {
                    "study": s,
                    "evaluation_mode": mode,
                    "regime": "cyclic",
                    "feedback_mode": v.get("feedback_mode"),
                    "init_condition": v.get("init_condition"),
                    "mean_p_expert_ss": v.get("mean_p_expert_ss"),
                    "mean_trust_expert_ss": v.get("mean_trust_expert_ss"),
                    "mean_trust_peers_ss": v.get("mean_trust_peers_ss"),
                }
            )
        for fb, v in d.get("hysteresis_gap", {}).items():
            if not isinstance(v, dict):
                continue
            rows.append(
                {
                    "study": s,
                    "evaluation_mode": mode,
                    "regime": "cyclic",
                    "feedback_mode": fb,
                    "init_condition": "gap",
                    "p_expert_gap_ss": v.get("p_expert_gap_ss"),
                    "trust_expert_gap_ss": v.get("trust_expert_gap_ss"),
                }
            )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df.columns = [c.lower() for c in df.columns]
    return df


def _build_hysteresis_trajectories(raw: Path) -> pd.DataFrame:
    """Per-trial hysteresis means/SDs from df_ext_hyst.csv.

    This mirrors the paper's hysteresis panel: baseline and post-collapse
    p(Expert) trajectories, with 95% CIs derived from SD / sqrt(n_runs).
    """
    p = raw / "extensions" / "df_ext_hyst.csv"
    if not p.exists():
        print(f"  [skip] {p} not found")
        return pd.DataFrame()
    print(f"  reading {p} (hysteresis trajectories)...")
    usecols = [
        "evaluation_mode",
        "regime",
        "feedback_mode",
        "init_condition",
        "trial",
        "run_id",
        "mu_E",
        "c_pen",
        "expert_inertia_divisor",
        "p_expert",
        "trust_expert",
        "trust_peers",
    ]
    df = pd.read_csv(p, usecols=usecols)
    df["study"] = df["evaluation_mode"].map({"binary": "2", "continuous": "3"})
    grouped = (
        df.groupby(
            ["study", "evaluation_mode", "regime", "feedback_mode", "init_condition", "trial"],
            dropna=False,
        )
        .agg(
            n_runs=("run_id", "nunique"),
            c_pen=("c_pen", "first"),
            expert_inertia_divisor=("expert_inertia_divisor", "first"),
            mu_e=("mu_E", "first"),
            mean_p_expert=("p_expert", "mean"),
            sd_p_expert=("p_expert", "std"),
            mean_trust_expert=("trust_expert", "mean"),
            sd_trust_expert=("trust_expert", "std"),
            mean_trust_peers=("trust_peers", "mean"),
            sd_trust_peers=("trust_peers", "std"),
        )
        .reset_index()
    )
    grouped.columns = [c.lower() for c in grouped.columns]
    return grouped


# --------------------------------------------------------------------------
# load + atomic swap
# --------------------------------------------------------------------------
def _insert_copy(conn, table: str, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    cols = list(df.columns)
    df = df[cols]
    with conn.cursor() as cur:
        cols_sql = ",".join(cols)
        buf = io.StringIO()
        df.to_csv(buf, index=False, header=False, na_rep="\\N")
        buf.seek(0)
        cur.copy_expert(
            f"COPY {table} ({cols_sql}) FROM STDIN WITH (FORMAT csv, NULL '\\N')",
            buf,
        )
    return len(df)


def _resolve_condition_ids(conn, staging_conditions: str) -> pd.DataFrame:
    """Map staging conditions rows to live condition IDs by unique key."""
    return pd.read_sql_query(
        "SELECT id, study, evaluation_mode, regime, feedback_mode, mu_E, c_pen, "
        "expert_inertia_divisor, clustering, rho_peers "
        f"FROM {staging_conditions}",
        conn,
    )

def run(args) -> None:
    ddir = data_dir()
    pub = ddir / "pub"
    raw = ddir / "data"
    studies = [s for s in args.studies]

    db.init_db()
    print("schema ready")

    row_counts = {}

    model_meta_rows = _collect_model_meta(studies, pub)
    row_counts["model_meta"] = len(model_meta_rows)
    if model_meta_rows:
        print(f"model_meta: {len(model_meta_rows)} rows")

    conditions = _build_conditions(studies, pub)
    row_counts["conditions"] = len(conditions)
    print(f"conditions: {len(conditions)} rows")

    runs = pd.DataFrame()
    trials = pd.DataFrame()
    base_cost_runs = pd.DataFrame()
    base_error_traces = pd.DataFrame()
    if "1" in studies:
        runs = _build_runs_study1(raw)
        row_counts["runs"] = len(runs)
        print(f"runs: {len(runs)} rows")
        base_cost_runs = _build_base_cost_runs(raw)
        row_counts["base_cost_runs"] = len(base_cost_runs)
        print(f"base_cost_runs: {len(base_cost_runs)} rows")
        base_error_traces = _build_base_error_traces(raw)
        row_counts["base_error_traces"] = len(base_error_traces)
        print(f"base_error_traces: {len(base_error_traces)} rows")
        if not args.skip_trials:
            trials = _build_trials_study1(raw)
            row_counts["trials"] = len(trials)
            print(f"trials: {len(trials)} rows")

    d5_runs = pd.DataFrame()
    if "d5" in studies or "1" in studies:
        d5_runs = _build_d5_runs(raw, pub)
        row_counts["d5_runs"] = len(d5_runs)
        print(f"d5_runs: {len(d5_runs)} rows")

    hysteresis = pd.DataFrame()
    hysteresis_trajectories = pd.DataFrame()
    extension_condition_aggregates = pd.DataFrame()
    extension_trajectories = pd.DataFrame()
    if "2" in studies or "3" in studies:
        extension_condition_aggregates = _build_extension_condition_aggregates(raw)
        row_counts["extension_condition_aggregates"] = len(extension_condition_aggregates)
        print(f"extension_condition_aggregates: {len(extension_condition_aggregates)} rows")
        extension_trajectories = _build_extension_trajectories(raw)
        row_counts["extension_trajectories"] = len(extension_trajectories)
        print(f"extension_trajectories: {len(extension_trajectories)} rows")
        hysteresis = _build_hysteresis(pub)
        row_counts["hysteresis"] = len(hysteresis)
        print(f"hysteresis: {len(hysteresis)} rows")
        hysteresis_trajectories = _build_hysteresis_trajectories(raw)
        row_counts["hysteresis_trajectories"] = len(hysteresis_trajectories)
        print(f"hysteresis_trajectories: {len(hysteresis_trajectories)} rows")

    if args.dry_run:
        print("\n[DRY RUN] no changes written.")
        for k, v in row_counts.items():
            print(f"  {k}: {v}")
        return

    # ---- atomic swap ----
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS _staging_conditions")
            cur.execute("DROP TABLE IF EXISTS _staging_runs")
            cur.execute("DROP TABLE IF EXISTS _staging_trials")
            cur.execute("DROP TABLE IF EXISTS _staging_base_cost_runs")
            cur.execute("DROP TABLE IF EXISTS _staging_base_error_traces")
            cur.execute("DROP TABLE IF EXISTS _staging_extension_condition_aggregates")
            cur.execute("DROP TABLE IF EXISTS _staging_extension_trajectories")
            cur.execute("DROP TABLE IF EXISTS _staging_d5_runs")
            cur.execute("DROP TABLE IF EXISTS _staging_hysteresis")
            cur.execute("DROP TABLE IF EXISTS _staging_hysteresis_trajectories")
            cur.execute("DROP TABLE IF EXISTS _staging_model_meta")
        conn.commit()

        # staging tables mirror live ones (no FKs between staging)
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE _staging_conditions (LIKE conditions "
                "INCLUDING DEFAULTS INCLUDING IDENTITY)"
            )
            cur.execute(
                "CREATE TABLE _staging_runs (LIKE runs "
                "INCLUDING DEFAULTS INCLUDING IDENTITY)"
            )
            cur.execute(
                "CREATE TABLE _staging_trials (LIKE trials "
                "INCLUDING DEFAULTS INCLUDING IDENTITY)"
            )
            cur.execute(
                "CREATE TABLE _staging_base_cost_runs (LIKE base_cost_runs "
                "INCLUDING DEFAULTS INCLUDING IDENTITY)"
            )
            cur.execute(
                "CREATE TABLE _staging_base_error_traces (LIKE base_error_traces "
                "INCLUDING DEFAULTS INCLUDING IDENTITY)"
            )
            cur.execute(
                "CREATE TABLE _staging_extension_condition_aggregates "
                "(LIKE extension_condition_aggregates INCLUDING DEFAULTS INCLUDING IDENTITY)"
            )
            cur.execute(
                "CREATE TABLE _staging_extension_trajectories "
                "(LIKE extension_trajectories INCLUDING DEFAULTS INCLUDING IDENTITY)"
            )
            cur.execute(
                "CREATE TABLE _staging_d5_runs (LIKE d5_runs "
                "INCLUDING DEFAULTS INCLUDING IDENTITY)"
            )
            cur.execute(
                "CREATE TABLE _staging_hysteresis_trajectories (LIKE hysteresis_trajectories "
                "INCLUDING DEFAULTS INCLUDING IDENTITY)"
            )
            cur.execute(
                "CREATE TABLE _staging_model_meta (LIKE model_meta "
                "INCLUDING DEFAULTS INCLUDING IDENTITY)"
            )
            cur.execute(
                "CREATE TABLE _staging_hysteresis_trajectories "
                "(LIKE hysteresis_trajectories INCLUDING DEFAULTS INCLUDING IDENTITY)"
            )
        conn.commit()

        _insert_copy(conn, "_staging_conditions", conditions)

        # resolve condition ids for runs/trials staging
        cond_key = _resolve_condition_ids(conn, "_staging_conditions")
        merge_keys = ["study", "evaluation_mode", "regime", "feedback_mode",
                      "mu_e", "c_pen", "expert_inertia_divisor", "clustering", "rho_peers"]
        # coerce merge-key dtypes so object/float mismatches don't break the join
        for k in merge_keys:
            if k in cond_key.columns and cond_key[k].dtype == object:
                cond_key[k] = pd.to_numeric(cond_key[k], errors="coerce")
        if not runs.empty:
            for k in merge_keys:
                if k in runs.columns and runs[k].dtype == object:
                    runs[k] = pd.to_numeric(runs[k], errors="coerce")
            runs_s = runs.merge(
                cond_key[["id"] + merge_keys],
                on=merge_keys,
                how="left",
            )
            runs_s = runs_s.rename(columns={"id": "condition_id"})
            runs_s["condition_id"] = runs_s["condition_id"].astype(int)
            runs_s = runs_s.drop(columns=merge_keys)
            _insert_copy(conn, "_staging_runs", runs_s)

        if not trials.empty:
            for k in merge_keys:
                if k in trials.columns and trials[k].dtype == object:
                    trials[k] = pd.to_numeric(trials[k], errors="coerce")
            trials_s = trials.merge(
                cond_key[["id"] + merge_keys],
                on=merge_keys,
                how="left",
            )
            trials_s = trials_s.rename(columns={"id": "condition_id"})
            trials_s = trials_s.dropna(subset=["condition_id"])
            trials_s["condition_id"] = trials_s["condition_id"].astype(int)
            # evaluation_mode is a real (NOT NULL partition-key) column of the
            # trials table and must be kept; the other merge keys are not
            # columns of trials and should be dropped.
            trials_s = trials_s.drop(
                columns=[k for k in merge_keys if k != "evaluation_mode"]
            )
            _insert_copy(conn, "_staging_trials", trials_s)

        if not base_cost_runs.empty:
            _insert_copy(conn, "_staging_base_cost_runs", base_cost_runs)
        if not base_error_traces.empty:
            _insert_copy(conn, "_staging_base_error_traces", base_error_traces)
        if not extension_condition_aggregates.empty:
            _insert_copy(conn, "_staging_extension_condition_aggregates", extension_condition_aggregates)
        if not extension_trajectories.empty:
            _insert_copy(conn, "_staging_extension_trajectories", extension_trajectories)

        if not d5_runs.empty:
            _insert_copy(conn, "_staging_d5_runs", d5_runs)
        if not hysteresis.empty:
            _insert_copy(conn, "_staging_hysteresis", hysteresis)
        if not hysteresis_trajectories.empty:
            _insert_copy(conn, "_staging_hysteresis_trajectories", hysteresis_trajectories)

        if model_meta_rows:
            model_meta_df = pd.DataFrame(model_meta_rows)
            model_meta_df["design"] = model_meta_df["design"].apply(json.dumps)
            _insert_copy(conn, "_staging_model_meta", model_meta_df)

        conn.commit()

        # ---- swap in one transaction ----
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE TABLE conditions, runs, trials, d5_runs, hysteresis, "
                "hysteresis_trajectories, base_cost_runs, base_error_traces, "
                "extension_condition_aggregates, extension_trajectories, model_meta "
                "RESTART IDENTITY CASCADE"
            )
            cur.execute("INSERT INTO conditions SELECT * FROM _staging_conditions")
            cur.execute("INSERT INTO runs SELECT * FROM _staging_runs")
            cur.execute("INSERT INTO trials SELECT * FROM _staging_trials")
            cur.execute("INSERT INTO base_cost_runs SELECT * FROM _staging_base_cost_runs")
            cur.execute("INSERT INTO base_error_traces SELECT * FROM _staging_base_error_traces")
            cur.execute("INSERT INTO extension_condition_aggregates SELECT * FROM _staging_extension_condition_aggregates")
            cur.execute("INSERT INTO extension_trajectories SELECT * FROM _staging_extension_trajectories")
            cur.execute("INSERT INTO d5_runs SELECT * FROM _staging_d5_runs")
            cur.execute("INSERT INTO hysteresis SELECT * FROM _staging_hysteresis")
            cur.execute("INSERT INTO hysteresis_trajectories SELECT * FROM _staging_hysteresis_trajectories")
            cur.execute("INSERT INTO model_meta SELECT * FROM _staging_model_meta")
            cur.execute("DROP TABLE IF EXISTS _staging_conditions")
            cur.execute("DROP TABLE IF EXISTS _staging_runs")
            cur.execute("DROP TABLE IF EXISTS _staging_trials")
            cur.execute("DROP TABLE IF EXISTS _staging_base_cost_runs")
            cur.execute("DROP TABLE IF EXISTS _staging_base_error_traces")
            cur.execute("DROP TABLE IF EXISTS _staging_extension_condition_aggregates")
            cur.execute("DROP TABLE IF EXISTS _staging_extension_trajectories")
            cur.execute("DROP TABLE IF EXISTS _staging_d5_runs")
            cur.execute("DROP TABLE IF EXISTS _staging_hysteresis")
            cur.execute("DROP TABLE IF EXISTS _staging_hysteresis_trajectories")
            cur.execute("DROP TABLE IF EXISTS _staging_model_meta")
            # metadata
            import subprocess
            sha = ""
            for cand in (ddir / ".git", Path(ddir).parent / "trust-bandits-analysis" / ".git"):
                try:
                    sha = subprocess.check_output(
                        ["git", "-C", str(cand.parent), "rev-parse", "HEAD"],
                        stderr=subprocess.DEVNULL,
                    ).decode().strip()
                    break
                except Exception:
                    continue
            if not sha:
                sha = "unknown"
            cur.execute(
                "INSERT INTO ingest_meta (source_git_sha, studies, row_counts) "
                "VALUES (%s, %s, %s::jsonb)",
                (sha, ",".join(studies), json.dumps(row_counts)),
            )
        conn.commit()

    print("\nDone. Ingested row counts:")
    for k, v in row_counts.items():
        print(f"  {k}: {v}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--studies",
        nargs="*",
        default=ALL_STUDIES,
        help=f"Studies to ingest. Choices: {ALL_STUDIES}. Default: all.",
    )
    parser.add_argument("--reset", action="store_true", default=True, help="Reset and refill (default).")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be ingested, do not write.")
    parser.add_argument("--skip-trials", action="store_true", help="Skip trial-level loading (faster).")
    args = parser.parse_args()

    allowed = set(ALL_STUDIES)
    for s in args.studies:
        if s not in allowed:
            parser.error(f"unknown study {s!r}; choices are {ALL_STUDIES}")

    run(args)


if __name__ == "__main__":
    main()
