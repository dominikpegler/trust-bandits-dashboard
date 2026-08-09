"""Read-only query layer over the dashboard database."""
from __future__ import annotations

import pandas as pd

from . import db

METRIC_COLUMNS = {
    "p_expert": ("mean_p_expert", "mean_p_expert_ss", "sd_p_expert", "sd_p_expert_ss"),
    "acc_expert": ("mean_acc_expert", "mean_acc_expert_ss", "sd_acc_expert", "sd_acc_expert_ss"),
    "acc_peers": ("mean_acc_peers", "mean_acc_peers_ss", "sd_acc_peers", "sd_acc_peers_ss"),
    "trust_expert": ("mean_trust_expert", "mean_trust_expert_ss", "sd_trust_expert", "sd_trust_expert_ss"),
    "trust_peers": ("mean_trust_peers", "mean_trust_peers_ss", "sd_trust_peers", "sd_trust_peers_ss"),
}

STUDIES = ("1", "2", "3", "d5-1", "d5-2", "d5-3")

# Friendly model names for display (the codes stay as internal query keys).
STUDY_LABELS = {
    "1": "Base model",
    "2": "Memory model",
    "3": "Graded-evaluation model",
    "d5-1": "Polarization extension (base model)",
    "d5-2": "Polarization extension (memory model)",
    "d5-3": "Polarization extension (graded-evaluation model)",
}


def study_label(code: str) -> str:
    return STUDY_LABELS.get(code, code)


def available_studies() -> list[str]:
    df = db.fetch_df("SELECT DISTINCT study FROM conditions ORDER BY study")
    return df["study"].tolist()


def get_meta() -> pd.DataFrame:
    return db.fetch_df(
        "SELECT * FROM ingest_meta ORDER BY ingest_timestamp DESC LIMIT 1"
    )


def condition_params(
    study: str,
    evaluation_mode: str | None = None,
    regime: str | None = None,
) -> dict:
    """Distinct parameter levels available for the given study (for dropdowns)."""
    where = ["study = :study"]
    params: dict = {"study": study}
    if evaluation_mode:
        where.append("evaluation_mode = :evaluation_mode")
        params["evaluation_mode"] = evaluation_mode
    if regime:
        where.append("regime = :regime")
        params["regime"] = regime
    q = (
        f"SELECT DISTINCT evaluation_mode, regime, feedback_mode, mu_e, c_pen, "
        f"expert_inertia_divisor, clustering, rho_peers FROM conditions "
        f"WHERE {' AND '.join(where)} ORDER BY mu_e, c_pen"
    )
    return db.fetch_df(q, params).to_dict("list")


def heatmap_data(
    study: str,
    feedback_mode: str,
    evaluation_mode: str,
    regime: str,
    steady: bool = False,
    metric: str = "p_expert",
) -> pd.DataFrame:
    """Pivot (mu_e x c_pen) for a heatmap over the base-model grid.

    For studies that collapse over mu_e (2/3), mu_e is constant so the pivot
    degenerates to a 1-row grid; callers should use marginal curves instead.
    """
    mean_col = METRIC_COLUMNS[metric][1 if steady else 0]
    sd_col = METRIC_COLUMNS[metric][3 if steady else 2]
    q = f"""
        SELECT mu_e, c_pen, feedback_mode, {mean_col} AS value, {sd_col} AS sd
        FROM conditions
        WHERE study = :study AND feedback_mode = :feedback_mode
          AND evaluation_mode = :evaluation_mode AND regime = :regime
          AND {mean_col} IS NOT NULL
        ORDER BY mu_e, c_pen
    """
    df = db.fetch_df(
        q,
        {
            "study": study,
            "feedback_mode": feedback_mode,
            "evaluation_mode": evaluation_mode,
            "regime": regime,
        },
    )
    if df.empty:
        return df
    return df.pivot(index="c_pen", columns="mu_e", values="value").sort_index(ascending=False)


def marginal_data(
    study: str,
    feedback_mode: str,
    evaluation_mode: str,
    regime: str,
    steady: bool = False,
    metric: str = "p_expert",
    fixed: dict | None = None,
) -> pd.DataFrame:
    """Marginal curves: metric vs c_pen and vs mu_e with means.

    `fixed` allows pinning mu_e (for the vs-c_pen curve) or c_pen (for the
    vs-mu_e curve).
    """
    mean_col = METRIC_COLUMNS[metric][1 if steady else 0]
    sd_col = METRIC_COLUMNS[metric][3 if steady else 2]
    fixed = fixed or {}
    conds = ["study = :study", "feedback_mode = :feedback_mode",
             "evaluation_mode = :evaluation_mode", "regime = :regime",
             f"{mean_col} IS NOT NULL"]
    params = {"study": study, "feedback_mode": feedback_mode,
              "evaluation_mode": evaluation_mode, "regime": regime}
    for k, v in fixed.items():
        conds.append(f"{k} = :{k}")
        params[k] = v
    q = (
        f"SELECT mu_e, c_pen, {mean_col} AS value, {sd_col} AS sd FROM conditions "
        f"WHERE {' AND '.join(conds)} ORDER BY c_pen, mu_e"
    )
    return db.fetch_df(q, params)


# --------------------------------------------------------------------------
# Base-model paper panels (D1-D3)
# --------------------------------------------------------------------------
def base_heatmap_cells(feedback_mode: str = "full", steady: bool = True) -> pd.DataFrame:
    """Cell-level base-model D1 data for the paper-style heatmap."""
    suffix = "_ss" if steady else ""
    q = f"""
        SELECT mu_e, c_pen, feedback_mode, n_runs,
               mean_p_expert{suffix} AS mean_p_expert,
               mean_acc_expert{suffix} AS mean_acc_expert,
               mean_acc_peers{suffix} AS mean_acc_peers,
               mean_trust_expert{suffix} AS mean_trust_expert,
               mean_trust_peers{suffix} AS mean_trust_peers
        FROM conditions
        WHERE study = '1' AND feedback_mode = :feedback_mode
          AND evaluation_mode = 'binary' AND regime = 'stationary'
        ORDER BY c_pen, mu_e
    """
    df = db.fetch_df(q, {"feedback_mode": feedback_mode})
    if df.empty:
        return df
    df["delta_acc"] = df["mean_acc_expert"] - df["mean_acc_peers"]
    df["is_paradox"] = (df["delta_acc"] > 0) & (df["mean_p_expert"] < 0.5)
    return df


def base_difficulty_data(feedback_mode: str = "full") -> pd.DataFrame:
    """D2: source accuracy and p(Expert) by mu_E at c_pen=6."""
    q = """
        SELECT c.mu_e, c.c_pen, c.feedback_mode, r.run_id,
               r.mean_p_expert AS p_expert,
               r.mean_acc_expert AS acc_expert,
               r.mean_acc_peers AS acc_peers
        FROM runs r
        JOIN conditions c ON c.id = r.condition_id
        WHERE c.study = '1' AND c.feedback_mode = :feedback_mode
          AND c.evaluation_mode = 'binary' AND c.regime = 'stationary'
          AND c.c_pen = 6.0
        ORDER BY c.mu_e, r.run_id
    """
    return db.fetch_df(q, {"feedback_mode": feedback_mode})


def base_cost_data(feedback_mode: str = "full") -> pd.DataFrame:
    """D3: p(Expert) by cognitive cost weight."""
    q = """
        SELECT feedback_mode, run_id, cost_w_n, cost_w_var, cost_sum,
               mean_p_expert AS p_expert,
               mean_acc_expert AS acc_expert,
               mean_acc_peers AS acc_peers
        FROM base_cost_runs
        WHERE feedback_mode = :feedback_mode
        ORDER BY cost_sum, run_id
    """
    return db.fetch_df(q, {"feedback_mode": feedback_mode})


def base_error_trace_data(feedback_mode: str = "full") -> pd.DataFrame:
    """D1 error-locked trust changes around source errors."""
    q = """
        SELECT feedback_mode, run_id, trial_offset AS offset, source, trust_norm
        FROM base_error_traces
        WHERE feedback_mode = :feedback_mode
        ORDER BY source, trial_offset, run_id
    """
    return db.fetch_df(q, {"feedback_mode": feedback_mode})


def base_condition_error_trace_data(
    condition_id: int,
    window: int = 10,
    max_events_per_source: int = 1000,
) -> pd.DataFrame:
    """Compute error-locked trust traces dynamically for one base-model condition.

    For each Expert/Peers error event, trust is baseline-normalized relative to
    the trust value at the error trial and tracked over +/- `window` trials.
    Events are capped per source to keep the dashboard responsive.
    """
    raw = db.fetch_df(
        """SELECT run_id, trial, trust_expert, trust_peers, acc_expert, acc_peers
           FROM trials
           WHERE condition_id = :cid
           ORDER BY run_id, trial""",
        {"cid": condition_id},
    )
    if raw.empty:
        return raw
    frames = []
    for source, err_col, trust_col in (
        ("Expert", "acc_expert", "trust_expert"),
        ("Peers", "acc_peers", "trust_peers"),
    ):
        events = raw[raw[err_col] == 0][["run_id", "trial", trust_col]].head(max_events_per_source)
        rows = []
        for _, ev in events.iterrows():
            sub = raw[(raw["run_id"] == ev["run_id"]) &
                      (raw["trial"].between(ev["trial"] - window, ev["trial"] + window))]
            if sub.empty:
                continue
            baseline = float(ev[trust_col])
            tmp = pd.DataFrame({
                "offset": sub["trial"].to_numpy() - int(ev["trial"]),
                "trust_norm": sub[trust_col].to_numpy() - baseline,
                "source": source,
                "run_id": int(ev["run_id"]),
                "event_iter": int(ev["trial"]),
            })
            rows.append(tmp)
        if rows:
            frames.append(pd.concat(rows, ignore_index=True))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def per_run_ci(
    study: str,
    feedback_mode: str,
    evaluation_mode: str,
    regime: str,
    mu_e: float | None = None,
    c_pen: float | None = None,
    steady: bool = False,
    metric: str = "p_expert",
) -> pd.DataFrame:
    """Per-run means for one (or several) conditions, for bootstrap CI ribbons.

    Returns rows of (mu_e, c_pen, value).
    """
    col = f"mean_{metric}_ss" if steady else f"mean_{metric}"
    if metric not in ("p_expert", "acc_expert", "acc_peers", "trust_expert", "trust_peers"):
        return pd.DataFrame()
    conds = ["c.study = :study", "c.feedback_mode = :feedback_mode",
             "c.evaluation_mode = :evaluation_mode", "c.regime = :regime",
             f"r.{col} IS NOT NULL"]
    params = {"study": study, "feedback_mode": feedback_mode,
              "evaluation_mode": evaluation_mode, "regime": regime}
    if mu_e is not None:
        conds.append("c.mu_e = :mu_e")
        params["mu_e"] = mu_e
    if c_pen is not None:
        conds.append("c.c_pen = :c_pen")
        params["c_pen"] = c_pen
    # use the runs table
    q = f"""
        SELECT c.mu_e, c.c_pen, r.{col} AS value
        FROM runs r
        JOIN conditions c ON c.id = r.condition_id
        WHERE {' AND '.join(conds)}
    """
    return db.fetch_df(q, params)


def condition_id(
    study: str,
    feedback_mode: str,
    evaluation_mode: str,
    regime: str,
    mu_e: float,
    c_pen: float,
    expert_inertia_divisor: float | None = None,
    clustering: float = 0.0,
    rho_peers: float = 0.0,
) -> int | None:
    # Streamlit selectboxes backed by pandas/numpy values can produce np.float64
    # scalars. psycopg2 may render those incorrectly unless converted to native
    # Python floats first.
    mu_e = float(mu_e)
    c_pen = float(c_pen)
    clustering = float(clustering)
    rho_peers = float(rho_peers)
    divisor = None if expert_inertia_divisor is None else float(expert_inertia_divisor)
    row = db.fetch_df(
        """SELECT id FROM conditions
           WHERE study = :study AND feedback_mode = :feedback_mode
             AND evaluation_mode = :evaluation_mode AND regime = :regime
             AND mu_e = :mu_e AND c_pen = :c_pen
             AND expert_inertia_divisor IS NOT DISTINCT FROM :expert_inertia_divisor
             AND clustering = :clustering AND rho_peers = :rho_peers""",
        {
            "study": study, "feedback_mode": feedback_mode,
            "evaluation_mode": evaluation_mode, "regime": regime,
            "mu_e": mu_e, "c_pen": c_pen,
            "expert_inertia_divisor": divisor,
            "clustering": clustering, "rho_peers": rho_peers,
        },
    )
    return int(row.iloc[0]["id"]) if not row.empty else None


def trajectory_data(
    cid: int,
    steady: bool = False,
) -> pd.DataFrame:
    """Per-run per-trial data for one condition. Aggregates to trial means + CI.

    If `steady` is True, only second-half trials are returned (steady state).
    Returns a DataFrame with per-trial means/SDs plus an `n_runs` column.
    """
    if steady:
        q = """
            SELECT run_id, trial, p_expert, trust_expert, trust_peers,
                   acc_expert, acc_peers
            FROM trials
            WHERE condition_id = :cid
              AND trial > (SELECT max(trial)/2 FROM trials WHERE condition_id = :cid)
        """
    else:
        q = """
            SELECT run_id, trial, p_expert, trust_expert, trust_peers,
                   acc_expert, acc_peers
            FROM trials WHERE condition_id = :cid
        """
    df = db.fetch_df(q, {"cid": cid})
    if df.empty:
        return df
    n_runs = df["run_id"].nunique()
    grouped = (
        df.groupby("trial")
        .agg(
            mean_p_expert=("p_expert", "mean"),
            sd_p_expert=("p_expert", "std"),
            mean_trust_expert=("trust_expert", "mean"),
            sd_trust_expert=("trust_expert", "std"),
            mean_trust_peers=("trust_peers", "mean"),
            sd_trust_peers=("trust_peers", "std"),
            mean_acc_expert=("acc_expert", "mean"),
            sd_acc_expert=("acc_expert", "std"),
            mean_acc_peers=("acc_peers", "mean"),
            sd_acc_peers=("acc_peers", "std"),
        )
        .reset_index()
    )
    grouped["n_runs"] = n_runs
    return grouped


def condition_n_runs(
    study: str,
    feedback_mode: str,
    evaluation_mode: str,
    regime: str,
    mu_e: float,
    c_pen: float,
    expert_inertia_divisor: float | None = None,
) -> int | None:
    mu_e = float(mu_e)
    c_pen = float(c_pen)
    divisor = None if expert_inertia_divisor is None else float(expert_inertia_divisor)
    row = db.fetch_df(
        """SELECT n_runs FROM conditions
           WHERE study = :study AND feedback_mode = :feedback_mode
             AND evaluation_mode = :evaluation_mode AND regime = :regime
             AND mu_e = :mu_e AND c_pen = :c_pen
             AND expert_inertia_divisor IS NOT DISTINCT FROM :divisor""",
        {
            "study": study, "feedback_mode": feedback_mode,
            "evaluation_mode": evaluation_mode, "regime": regime,
            "mu_e": mu_e, "c_pen": c_pen, "divisor": divisor,
        },
    )
    return int(row.iloc[0]["n_runs"]) if not row.empty and row.iloc[0]["n_runs"] is not None else None


# --------------------------------------------------------------------------
# Memory/graded-evaluation heatmaps (d_T x c_pen)
# --------------------------------------------------------------------------
def study23_heatmap_data(
    study: str,
    feedback_mode: str,
    evaluation_mode: str,
    regime: str,
    steady: bool = False,
    metric: str = "p_expert",
) -> pd.DataFrame:
    """Pivot (expert_inertia_divisor x c_pen) for Studies 2/3."""
    mean_col = METRIC_COLUMNS[metric][1 if steady else 0]
    q = f"""
        SELECT expert_inertia_divisor, c_pen, {mean_col} AS value
        FROM conditions
        WHERE study = :study AND feedback_mode = :feedback_mode
          AND evaluation_mode = :evaluation_mode AND regime = :regime
          AND {mean_col} IS NOT NULL
        ORDER BY expert_inertia_divisor, c_pen
    """
    df = db.fetch_df(
        q,
        {
            "study": study, "feedback_mode": feedback_mode,
            "evaluation_mode": evaluation_mode, "regime": regime,
        },
    )
    if df.empty:
        return df
    return df.pivot(index="c_pen", columns="expert_inertia_divisor", values="value").sort_index(ascending=False)


def extension_heatmap_cells(
    study: str,
    feedback_mode: str,
    regime: str,
    x_var: str,
    y_var: str,
    fixed: dict,
    steady: bool = True,
    metric: str = "p_expert",
) -> pd.DataFrame:
    """Cell-level memory/graded heatmap data from full extension aggregates."""
    evaluation_mode = "binary" if study == "2" else "continuous"
    metric_map = {
        "p_expert": ("mean_p_expert", "mean_p_expert_ss"),
        "acc_expert": ("mean_acc_expert", "mean_acc_expert_ss"),
        "acc_peers": ("mean_acc_peers", "mean_acc_peers_ss"),
        "trust_expert": ("mean_trust_expert", "mean_trust_expert_ss"),
        "trust_peers": ("mean_trust_peers", "mean_trust_peers_ss"),
    }
    value_col = metric_map[metric][1 if steady else 0]
    delta_col = "delta_acc_ss" if steady else "delta_acc"
    paradox_col = "is_paradox_ss" if steady else "is_paradox"
    conds = [
        "study = :study",
        "evaluation_mode = :evaluation_mode",
        "regime = :regime",
        "feedback_mode = :feedback_mode",
        f"{value_col} IS NOT NULL",
    ]
    params = {
        "study": study,
        "evaluation_mode": evaluation_mode,
        "regime": regime,
        "feedback_mode": feedback_mode,
    }
    for k, v in fixed.items():
        conds.append(f"{k} = :{k}")
        params[k] = float(v)
    q = f"""
        SELECT {x_var} AS x, {y_var} AS y, mu_e, expert_inertia_divisor, c_pen,
               n_runs, {value_col} AS value, {delta_col} AS delta_acc,
               {paradox_col} AS is_paradox, mean_acc_expert_ss, mean_acc_peers_ss
        FROM extension_condition_aggregates
        WHERE {' AND '.join(conds)}
        ORDER BY {y_var}, {x_var}
    """
    return db.fetch_df(q, params)


def extension_levels(study: str, regime: str = "cyclic", feedback_mode: str = "full") -> dict:
    evaluation_mode = "binary" if study == "2" else "continuous"
    df = db.fetch_df(
        """SELECT DISTINCT mu_e, expert_inertia_divisor, c_pen
           FROM extension_condition_aggregates
           WHERE study = :study AND evaluation_mode = :evaluation_mode
             AND regime = :regime AND feedback_mode = :feedback_mode""",
        {"study": study, "evaluation_mode": evaluation_mode, "regime": regime, "feedback_mode": feedback_mode},
    )
    if df.empty:
        return {"mu_e": [], "expert_inertia_divisor": [], "c_pen": []}
    return {
        "mu_e": sorted(df["mu_e"].unique()),
        "expert_inertia_divisor": sorted(df["expert_inertia_divisor"].unique()),
        "c_pen": sorted(df["c_pen"].unique()),
    }


def extension_trajectory_data(
    study: str,
    feedback_mode: str,
    regime: str,
    mu_e: float,
    expert_inertia_divisor: float,
    c_pen: float,
) -> pd.DataFrame:
    evaluation_mode = "binary" if study == "2" else "continuous"
    return db.fetch_df(
        """SELECT trial, n_runs, mean_p_expert, sd_p_expert,
                  mean_trust_expert, sd_trust_expert, mean_trust_peers,
                  sd_trust_peers, mean_acc_expert, sd_acc_expert,
                  mean_acc_peers, sd_acc_peers
           FROM extension_trajectories
           WHERE study = :study AND evaluation_mode = :evaluation_mode
             AND feedback_mode = :feedback_mode AND regime = :regime
             AND mu_e = :mu_e AND expert_inertia_divisor = :d_t AND c_pen = :c_pen
           ORDER BY trial""",
        {
            "study": study,
            "evaluation_mode": evaluation_mode,
            "feedback_mode": feedback_mode,
            "regime": regime,
            "mu_e": float(mu_e),
            "d_t": float(expert_inertia_divisor),
            "c_pen": float(c_pen),
        },
    )


# --------------------------------------------------------------------------
# D5 bifurcation (per-run distributions)
# --------------------------------------------------------------------------
def d5_runs_data(
    study: str = "d5-1",
    feedback_mode: str = "partial",
    metric: str = "p_expert",
) -> pd.DataFrame:
    """Per-run values over the clustering x rho grid for one feedback mode."""
    col = {"p_expert": "p_expert", "trust_expert": "trust_expert",
           "trust_peers": "trust_peers"}.get(metric, "p_expert")
    return db.fetch_df(
        f"""SELECT clustering, rho_peers, run_id, {col} AS value
            FROM d5_runs
            WHERE study = :study AND feedback_mode = :feedback_mode
            ORDER BY clustering, rho_peers, run_id""",
        {"study": study, "feedback_mode": feedback_mode},
    )


def d5_grid_levels(study: str = "d5-1") -> tuple:
    df = db.fetch_df(
        """SELECT DISTINCT clustering, rho_peers FROM d5_runs
           WHERE study = :study ORDER BY clustering, rho_peers""",
        {"study": study},
    )
    return sorted(df["clustering"].unique()), sorted(df["rho_peers"].unique())


# --------------------------------------------------------------------------
# Hysteresis
# --------------------------------------------------------------------------
def hysteresis_data(study: str = "2", feedback_mode: str = "full") -> pd.DataFrame:
    return db.fetch_df(
        """SELECT init_condition, mean_p_expert_ss, mean_trust_expert_ss,
                  mean_trust_peers_ss, p_expert_gap_ss, trust_expert_gap_ss
           FROM hysteresis
           WHERE study = :study AND feedback_mode = :feedback_mode
           ORDER BY init_condition""",
        {"study": study, "feedback_mode": feedback_mode},
    )


def hysteresis_trajectory_data(
    study: str = "2",
    feedback_mode: str = "full",
    regime: str = "cyclic",
) -> pd.DataFrame:
    """Per-trial aggregate hysteresis trajectories for a model/feedback/regime."""
    evaluation_mode = "binary" if study == "2" else "continuous"
    return db.fetch_df(
        """SELECT init_condition, trial, n_runs, c_pen, expert_inertia_divisor,
                  mu_e, mean_p_expert, sd_p_expert, mean_trust_expert,
                  sd_trust_expert, mean_trust_peers, sd_trust_peers
           FROM hysteresis_trajectories
           WHERE study = :study AND evaluation_mode = :evaluation_mode
             AND feedback_mode = :feedback_mode AND regime = :regime
           ORDER BY init_condition, trial""",
        {
            "study": study,
            "evaluation_mode": evaluation_mode,
            "feedback_mode": feedback_mode,
            "regime": regime,
        },
    )


def hysteresis_condition_meta(
    study: str = "2",
    feedback_mode: str = "full",
    regime: str = "cyclic",
) -> dict:
    """Fixed condition parameters for the hysteresis panel."""
    df = hysteresis_trajectory_data(study, feedback_mode, regime)
    if df.empty:
        return {}
    return {
        "n_runs": int(df["n_runs"].dropna().iloc[0]),
        "n_trials": int(df["trial"].max()),
        "c_pen": float(df["c_pen"].dropna().iloc[0]),
        "expert_inertia_divisor": float(df["expert_inertia_divisor"].dropna().iloc[0]),
        "mu_e_values": sorted(float(x) for x in df["mu_e"].dropna().unique()),
        "cycle_length": 20,
        "baseline_init": (0.5, 0.5),
        "post_collapse_init": (0.1, 0.9),
    }
