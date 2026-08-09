"""One-shot loader: reset-and-refill the dashboard database from raw data.

Usage
-----
    python scripts/ingest.py [--reset] [--studies 1 2 3 b5] [--dry-run]
                             [--skip-trials] [--conn-url URL]

Behaviour
---------
* Reads sources from the analysis repo's data directory (DATA_DIR env or
  --data-dir). By default only the pre-aggregated JSON files and small summary
  CSVs are read for the `conditions` and `runs` tables; trial-level data is
  loaded for `trials` from the Study 1 multi-condition CSVs (use --skip-trials
  to leave `trials` empty, which is fine for the heatmap pages).
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

import pandas as pd

# Allow running as a plain script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard import db  # noqa: E402
from dashboard.config import data_dir  # noqa: E402

STUDY1 = ["1"]
STUDIES_23 = ["2", "3"]
B5 = ["b5"]
ALL_STUDIES = STUDY1 + STUDIES_23 + B5

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


# --------------------------------------------------------------------------
# conditions (aggregates)
# --------------------------------------------------------------------------
def _build_study1_conditions(d: dict) -> pd.DataFrame:
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
    # B5 sub-block (echo-chamber), distinct study key so it does not collide
    # with the base (mu_E=0.65, c_pen=6.0, clustering=0, rho=0) condition.
    for key, v in d.get("b5", {}).items():
        if not isinstance(v, dict):
            continue
        rows.append(
            {
                "study": "b5-1",
                "evaluation_mode": "binary",
                "regime": "stationary",
                "feedback_mode": v.get("feedback_mode"),
                "mu_E": 0.65,  # B5 uses the default difficulty
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


def _build_b5_conditions(b5_json: dict, study: str, mode: str) -> pd.DataFrame:
    rows = []
    for key, v in b5_json.items():
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
    if "b5" in studies:
        for s, fname, mode in (
            ("2", "study_2.json", "binary"),
            ("3", "study_3.json", "continuous"),
        ):
            d = _load_json(pub, f"extensions/{fname}")
            if d and d.get("b5_memory"):
                frames.append(_build_b5_conditions(d["b5_memory"], f"b5-{s}", mode))
            if d and d.get("b5_graded"):
                frames.append(_build_b5_conditions(d["b5_graded"], f"b5-{s}", mode))
        d1 = _load_json(pub, "basemodel/study_1.json")
        if d1 and d1.get("b5"):
            frames.append(_build_b5_conditions(d1["b5"], "b5-1", "binary"))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df.columns = [c.lower() for c in df.columns]
    if "n_runs" in df.columns:
        df["n_runs"] = pd.to_numeric(df["n_runs"], errors="coerce").astype("Int64")
    return df


# --------------------------------------------------------------------------
# runs (per-run means) for Study 1 from the multi-condition CSVs
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
        p = raw / "basemodel" / f"df_b1_b2_multi_{fb}.csv"
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
# trials (trial-level) for Study 1
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
        p = raw / "basemodel" / f"df_b1_b2_multi_{fb}.csv"
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

    conditions = _build_conditions(studies, pub)
    row_counts["conditions"] = len(conditions)
    print(f"conditions: {len(conditions)} rows")

    runs = pd.DataFrame()
    trials = pd.DataFrame()
    if "1" in studies:
        runs = _build_runs_study1(raw)
        row_counts["runs"] = len(runs)
        print(f"runs: {len(runs)} rows")
        if not args.skip_trials:
            trials = _build_trials_study1(raw)
            row_counts["trials"] = len(trials)
            print(f"trials: {len(trials)} rows")

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
            trials_s = trials_s.drop(columns=merge_keys)
            _insert_copy(conn, "_staging_trials", trials_s)

        conn.commit()

        # ---- swap in one transaction ----
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE conditions, runs, trials RESTART IDENTITY CASCADE")
            cur.execute("INSERT INTO conditions SELECT * FROM _staging_conditions")
            cur.execute("INSERT INTO runs SELECT * FROM _staging_runs")
            cur.execute("INSERT INTO trials SELECT * FROM _staging_trials")
            cur.execute("DROP TABLE IF EXISTS _staging_conditions")
            cur.execute("DROP TABLE IF EXISTS _staging_runs")
            cur.execute("DROP TABLE IF EXISTS _staging_trials")
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
