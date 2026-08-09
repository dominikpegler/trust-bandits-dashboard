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

STUDIES = ("1", "2", "3", "b5-1", "b5-2", "b5-3")


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
    """Pivot (mu_e x c_pen) for a heatmap over the Study 1 grid.

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
    row = db.fetch_df(
        """SELECT id FROM conditions
           WHERE study = :study AND feedback_mode = :feedback_mode
             AND evaluation_mode = :evaluation_mode AND regime = :regime
             AND mu_e = :mu_e AND c_pen = :c_pen
             AND clustering = :clustering AND rho_peers = :rho_peers""",
        {
            "study": study, "feedback_mode": feedback_mode,
            "evaluation_mode": evaluation_mode, "regime": regime,
            "mu_e": mu_e, "c_pen": c_pen,
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
    return grouped
