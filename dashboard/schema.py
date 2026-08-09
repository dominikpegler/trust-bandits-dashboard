SCHEMA = """
-- Conditions: one row per (study, evaluation_mode, regime, feedback_mode,
-- mu_E, c_pen, expert_inertia_divisor, clustering, rho_peers).
-- Aggregated means/SDs per condition, pulled from the study_*.json files.
CREATE TABLE IF NOT EXISTS conditions (
    id                       BIGSERIAL PRIMARY KEY,
    study                    TEXT        NOT NULL,          -- 1, 2, 3, b5
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

    -- continuous-evaluation accuracy variants (Study 3)
    mean_acc_expert_cont     DOUBLE PRECISION,
    mean_acc_peers_cont      DOUBLE PRECISION,
    mean_acc_expert_cont_ss  DOUBLE PRECISION,
    mean_acc_peers_cont_ss   DOUBLE PRECISION,

    -- b5 fields
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
