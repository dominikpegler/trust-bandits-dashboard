SCHEMA = """
-- Conditions: one row per (study, evaluation_mode, regime, feedback_mode,
-- mu_E, c_pen, expert_inertia_divisor, clustering, rho_peers).
-- Aggregated means/SDs per condition, pulled from the study_*.json files.
CREATE TABLE IF NOT EXISTS conditions (
    id                       BIGSERIAL PRIMARY KEY,
    study                    TEXT        NOT NULL,          -- 1, 2, 3, d5
    evaluation_mode          TEXT        NOT NULL,          -- binary | continuous
    regime                   TEXT        NOT NULL,          -- stationary | cyclic
    feedback_mode            TEXT        NOT NULL,          -- full | partial
    mu_E                     DOUBLE PRECISION NOT NULL,
    c_pen                    DOUBLE PRECISION NOT NULL,
    expert_inertia_divisor   DOUBLE PRECISION,
    clustering               DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    rho_peers                DOUBLE PRECISION NOT NULL DEFAULT 0.0,

    mean_p_expert            DOUBLE PRECISION,
    sd_p_expert              DOUBLE PRECISION,
    mean_acc_expert          DOUBLE PRECISION,
    sd_acc_expert            DOUBLE PRECISION,
    mean_acc_peers           DOUBLE PRECISION,
    sd_acc_peers             DOUBLE PRECISION,
    mean_trust_expert        DOUBLE PRECISION,
    sd_trust_expert          DOUBLE PRECISION,
    mean_trust_peers         DOUBLE PRECISION,
    sd_trust_peers           DOUBLE PRECISION,

    -- steady-state (second-half) variants, where available
    mean_p_expert_ss         DOUBLE PRECISION,
    sd_p_expert_ss           DOUBLE PRECISION,
    mean_acc_expert_ss       DOUBLE PRECISION,
    sd_acc_expert_ss         DOUBLE PRECISION,
    mean_acc_peers_ss        DOUBLE PRECISION,
    sd_acc_peers_ss          DOUBLE PRECISION,
    mean_trust_expert_ss     DOUBLE PRECISION,
    sd_trust_expert_ss       DOUBLE PRECISION,
    mean_trust_peers_ss      DOUBLE PRECISION,
    sd_trust_peers_ss        DOUBLE PRECISION,

    -- continuous-evaluation accuracy variants (graded-evaluation model)
    mean_acc_expert_cont     DOUBLE PRECISION,
    mean_acc_peers_cont      DOUBLE PRECISION,
    mean_acc_expert_cont_ss  DOUBLE PRECISION,
    mean_acc_peers_cont_ss   DOUBLE PRECISION,

    -- D5 fields
    frac_low                 DOUBLE PRECISION,
    frac_high                DOUBLE PRECISION,
    n_runs                   INTEGER,
    gap                      DOUBLE PRECISION,

    UNIQUE (study, evaluation_mode, regime, feedback_mode,
            mu_E, c_pen, expert_inertia_divisor, clustering, rho_peers)
);

-- Per-run means: one row per (condition_id, run_id). Used for bootstrap CIs
-- and per-run distributions (bimodality).
CREATE TABLE IF NOT EXISTS runs (
    id                BIGSERIAL PRIMARY KEY,
    condition_id      BIGINT      NOT NULL REFERENCES conditions(id) ON DELETE CASCADE,
    run_id            INTEGER     NOT NULL,

    mean_p_expert     DOUBLE PRECISION,
    mean_trust_expert DOUBLE PRECISION,
    mean_trust_peers  DOUBLE PRECISION,
    mean_acc_expert   DOUBLE PRECISION,
    mean_acc_peers    DOUBLE PRECISION,

    -- steady-state (second-half) variants
    mean_p_expert_ss     DOUBLE PRECISION,
    mean_trust_expert_ss DOUBLE PRECISION,
    mean_trust_peers_ss  DOUBLE PRECISION,
    mean_acc_expert_ss   DOUBLE PRECISION,
    mean_acc_peers_ss    DOUBLE PRECISION,

    UNIQUE (condition_id, run_id)
);
CREATE INDEX IF NOT EXISTS runs_condition_idx ON runs(condition_id);

-- Trial-level data: loaded lazily for the trajectory explorer. Partitioned by
-- evaluation_mode so each partition stays a manageable size.
CREATE TABLE IF NOT EXISTS trials (
    evaluation_mode      TEXT        NOT NULL,
    condition_id         BIGINT      NOT NULL REFERENCES conditions(id) ON DELETE CASCADE,
    run_id               INTEGER     NOT NULL,
    trial                INTEGER     NOT NULL,
    p_expert             DOUBLE PRECISION,
    trust_expert         DOUBLE PRECISION,
    trust_peers          DOUBLE PRECISION,
    acc_expert           DOUBLE PRECISION,
    acc_peers            DOUBLE PRECISION,
    evidence_majority    INTEGER,
    evidence_proportion  DOUBLE PRECISION,
    chosen_source        TEXT
) PARTITION BY LIST (evaluation_mode);

CREATE INDEX IF NOT EXISTS trials_cond_run_idx
    ON trials(evaluation_mode, condition_id, run_id, trial);

-- Base-model cognitive-cost sweep (D3): one row per run x cost condition.
CREATE TABLE IF NOT EXISTS base_cost_runs (
    id                BIGSERIAL PRIMARY KEY,
    feedback_mode     TEXT        NOT NULL,
    run_id            INTEGER     NOT NULL,
    cost_w_n          DOUBLE PRECISION,
    cost_w_var        DOUBLE PRECISION,
    cost_sum          DOUBLE PRECISION,
    mean_p_expert     DOUBLE PRECISION,
    mean_acc_expert   DOUBLE PRECISION,
    mean_acc_peers    DOUBLE PRECISION,
    UNIQUE (feedback_mode, run_id, cost_w_n, cost_w_var)
);
CREATE INDEX IF NOT EXISTS base_cost_runs_idx
    ON base_cost_runs(feedback_mode, cost_sum);

-- Base-model error-locked trust traces (D1): one row per run x source x offset.
CREATE TABLE IF NOT EXISTS base_error_traces (
    id             BIGSERIAL PRIMARY KEY,
    feedback_mode  TEXT        NOT NULL,
    run_id         INTEGER     NOT NULL,
    event_iter     INTEGER,
    trial_offset   INTEGER     NOT NULL,
    source         TEXT        NOT NULL,          -- Expert | Peers
    trust          DOUBLE PRECISION,
    baseline       DOUBLE PRECISION,
    trust_norm     DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS base_error_traces_idx
    ON base_error_traces(feedback_mode, source, trial_offset);

-- Extension condition-level aggregates preserving the full parameter grid.
-- This powers the three paper-style heatmaps for memory and graded-evaluation
-- models: mu_E x c_pen, d_T x c_pen, and d_T x mu_E.
CREATE TABLE IF NOT EXISTS extension_condition_aggregates (
    id                       BIGSERIAL PRIMARY KEY,
    study                    TEXT        NOT NULL,        -- 2 | 3
    evaluation_mode          TEXT        NOT NULL,        -- binary | continuous
    regime                   TEXT        NOT NULL,        -- stationary | cyclic
    feedback_mode            TEXT        NOT NULL,
    mu_e                     DOUBLE PRECISION NOT NULL,
    expert_inertia_divisor   DOUBLE PRECISION NOT NULL,
    c_pen                    DOUBLE PRECISION NOT NULL,
    n_runs                   INTEGER,
    mean_p_expert            DOUBLE PRECISION,
    sd_p_expert              DOUBLE PRECISION,
    mean_p_expert_ss         DOUBLE PRECISION,
    sd_p_expert_ss           DOUBLE PRECISION,
    mean_acc_expert          DOUBLE PRECISION,
    mean_acc_peers           DOUBLE PRECISION,
    mean_acc_expert_ss       DOUBLE PRECISION,
    mean_acc_peers_ss        DOUBLE PRECISION,
    mean_acc_expert_cont     DOUBLE PRECISION,
    mean_acc_peers_cont      DOUBLE PRECISION,
    mean_acc_expert_cont_ss  DOUBLE PRECISION,
    mean_acc_peers_cont_ss   DOUBLE PRECISION,
    mean_trust_expert        DOUBLE PRECISION,
    mean_trust_peers         DOUBLE PRECISION,
    mean_trust_expert_ss     DOUBLE PRECISION,
    mean_trust_peers_ss      DOUBLE PRECISION,
    delta_acc                DOUBLE PRECISION,
    delta_acc_ss             DOUBLE PRECISION,
    is_paradox               BOOLEAN,
    is_paradox_ss            BOOLEAN,
    UNIQUE (study, evaluation_mode, regime, feedback_mode, mu_e, expert_inertia_divisor, c_pen)
);
CREATE INDEX IF NOT EXISTS extension_condition_aggregates_idx
    ON extension_condition_aggregates(study, evaluation_mode, regime, feedback_mode, mu_e, expert_inertia_divisor, c_pen);

-- Extension per-trial aggregates for selected-condition dynamics panels.
CREATE TABLE IF NOT EXISTS extension_trajectories (
    id                       BIGSERIAL PRIMARY KEY,
    study                    TEXT        NOT NULL,        -- 2 | 3
    evaluation_mode          TEXT        NOT NULL,        -- binary | continuous
    regime                   TEXT        NOT NULL,        -- stationary | cyclic
    feedback_mode            TEXT        NOT NULL,
    mu_e                     DOUBLE PRECISION NOT NULL,
    expert_inertia_divisor   DOUBLE PRECISION NOT NULL,
    c_pen                    DOUBLE PRECISION NOT NULL,
    trial                    INTEGER     NOT NULL,
    n_runs                   INTEGER,
    mean_p_expert            DOUBLE PRECISION,
    sd_p_expert              DOUBLE PRECISION,
    mean_trust_expert        DOUBLE PRECISION,
    sd_trust_expert          DOUBLE PRECISION,
    mean_trust_peers         DOUBLE PRECISION,
    sd_trust_peers           DOUBLE PRECISION,
    mean_acc_expert          DOUBLE PRECISION,
    sd_acc_expert            DOUBLE PRECISION,
    mean_acc_peers           DOUBLE PRECISION,
    sd_acc_peers             DOUBLE PRECISION,
    UNIQUE (study, evaluation_mode, regime, feedback_mode, mu_e, expert_inertia_divisor, c_pen, trial)
);
CREATE INDEX IF NOT EXISTS extension_trajectories_idx
    ON extension_trajectories(study, evaluation_mode, regime, feedback_mode, mu_e, expert_inertia_divisor, c_pen, trial);

-- D5 echo-chamber: per-run steady-state values over the clustering x rho grid.
CREATE TABLE IF NOT EXISTS d5_runs (
    id             BIGSERIAL PRIMARY KEY,
    study          TEXT        NOT NULL,          -- d5-1, d5-2, d5-3
    evaluation_mode TEXT       NOT NULL,          -- binary | continuous
    feedback_mode  TEXT        NOT NULL,
    clustering     DOUBLE PRECISION NOT NULL,
    rho_peers      DOUBLE PRECISION NOT NULL,
    run_id         INTEGER     NOT NULL,
    p_expert       DOUBLE PRECISION,
    trust_expert   DOUBLE PRECISION,
    trust_peers    DOUBLE PRECISION,
    acc_expert     DOUBLE PRECISION,
    acc_peers      DOUBLE PRECISION,
    UNIQUE (study, evaluation_mode, feedback_mode, clustering, rho_peers, run_id)
);
CREATE INDEX IF NOT EXISTS d5_runs_grid_idx
    ON d5_runs(study, evaluation_mode, feedback_mode, clustering, rho_peers);

-- Hysteresis: baseline vs post-collapse initial-trust comparison (Studies 2/3).
CREATE TABLE IF NOT EXISTS hysteresis (
    id               BIGSERIAL PRIMARY KEY,
    study            TEXT        NOT NULL,        -- 2 | 3
    evaluation_mode  TEXT        NOT NULL,        -- binary | continuous
    regime           TEXT        NOT NULL,        -- cyclic
    feedback_mode    TEXT        NOT NULL,
    init_condition   TEXT        NOT NULL,        -- baseline | post_collapse
    mean_p_expert_ss DOUBLE PRECISION,
    mean_trust_expert_ss DOUBLE PRECISION,
    mean_trust_peers_ss  DOUBLE PRECISION,
    p_expert_gap_ss  DOUBLE PRECISION,
    trust_expert_gap_ss DOUBLE PRECISION,
    UNIQUE (study, evaluation_mode, regime, feedback_mode, init_condition)
);

-- Hysteresis trajectories: per-trial aggregates from df_ext_hyst.csv.
-- These support the paper-style hysteresis panel (baseline stacked area plus
-- post-collapse p(Expert) line). Values are means/SDs across runs at each trial.
CREATE TABLE IF NOT EXISTS hysteresis_trajectories (
    id                 BIGSERIAL PRIMARY KEY,
    study              TEXT        NOT NULL,        -- 2 | 3
    evaluation_mode    TEXT        NOT NULL,        -- binary | continuous
    regime             TEXT        NOT NULL,        -- stationary | cyclic
    feedback_mode      TEXT        NOT NULL,
    init_condition     TEXT        NOT NULL,        -- baseline | post_collapse
    trial              INTEGER     NOT NULL,
    n_runs             INTEGER,
    c_pen              DOUBLE PRECISION,
    expert_inertia_divisor DOUBLE PRECISION,
    mu_e               DOUBLE PRECISION,
    mean_p_expert      DOUBLE PRECISION,
    sd_p_expert        DOUBLE PRECISION,
    mean_trust_expert  DOUBLE PRECISION,
    sd_trust_expert    DOUBLE PRECISION,
    mean_trust_peers   DOUBLE PRECISION,
    sd_trust_peers     DOUBLE PRECISION,
    UNIQUE (study, evaluation_mode, regime, feedback_mode, init_condition, trial)
);
CREATE INDEX IF NOT EXISTS hysteresis_traj_idx
    ON hysteresis_trajectories(study, evaluation_mode, regime, feedback_mode, init_condition, trial);

-- Ingest metadata: one row per successful ingest, so the app can show
-- "Data as of <date>" and detect stale data.
CREATE TABLE IF NOT EXISTS ingest_meta (
    id                 BIGSERIAL PRIMARY KEY,
    ingest_timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_git_sha     TEXT,
    studies            TEXT,
    row_counts         JSONB,
    source_checksums   JSONB
);
"""
