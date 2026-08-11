import html

import streamlit as st


PARAMETER_HELP = {
    "p_expert": "Probability that the simulated agent chooses the Expert rather than Peers on a trial.",
    "p_peers": "Probability that the simulated agent chooses Peers; this is 1 - p(Expert).",
    "trust": "Learned source weight used when deciding whether to rely on the Expert or Peers.",
    "accuracy": "Fraction of trials on which a source gives the correct answer.",
    "accuracy_gap": "Expert accuracy minus Peers accuracy; positive values mean the Expert is more accurate.",
    "steady_state": "Mean over the second half of trials, used as the primary summary once behavior has settled.",
    "full_range": "Mean over all trials, useful for seeing the effect of early transient behavior.",
    "ci": "95% confidence interval across simulation runs or replications.",
    "feedback": "Full feedback reveals outcomes for both sources; partial feedback reveals only the chosen source.",
    "mu_e": "Evidence strength for the task; larger values make the Expert's signal more informative.",
    "c_pen": "Asymmetric penalty for high-confidence errors; larger values make mistakes more costly.",
    "sigma_e": "Noise in the task evidence available to the model.",
    "sigma_expert": "Noise in the Expert's advice in a live simulation.",
    "sigma_peers_multiplier": "Multiplier applied to Expert noise to set Peers noise in a live simulation.",
    "m_peers": "Number of peer advisers sampled by the model.",
    "f_peers": "Fraction of available peer information sampled on each trial.",
    "lr_base": "Learning rate for trust updates; larger values adapt faster to recent outcomes.",
    "landscape_size": "Number of landscape/task items in the simulated environment.",
    "peer_cost_weights": "Cognitive-cost terms attached to peer information use.",
    "tau": "Decision temperature; lower values make choices more deterministic from current trust.",
    "w_init_expert": "Initial trust assigned to the Expert before learning from outcomes.",
    "w_init_peers": "Initial trust assigned to Peers before learning from outcomes.",
    "trials": "Number of sequential decisions in each simulation run.",
    "replications": "Number of independent simulation runs averaged together.",
    "d_t": "Expert inertia or memory-timescale parameter; larger values make source-memory effects persist longer.",
    "cyclic_regime": "Environment alternates between evidence-strength values over repeated cycles.",
    "stationary_regime": "Environment keeps the same evidence-strength setting over time.",
    "hysteresis": "Dependence of later trust on earlier trust history, even under the same current parameters.",
    "baseline_init": "Hysteresis trajectory initialized with balanced Expert and Peers trust.",
    "post_collapse_init": "Hysteresis trajectory initialized after an Expert-trust collapse.",
    "rho_clust": "Landscape-clustering parameter controlling how similar nearby agents' environments are.",
    "rho_peer": "Peer-correlation parameter controlling how correlated peer signals are.",
    "bifurcation": "Split of runs into low-Expert-trust and high-Expert-trust modes under the same parameters.",
    "sd_runs": "Standard deviation across runs; high values indicate stronger run-to-run divergence.",
    "aggregate_steady": "When enabled, condition-level heatmaps use only the second half of trials; trajectory panels still show all trials.",
}


def help_text(key: str) -> str:
    return PARAMETER_HELP[key]


MODEL_DESCRIPTIONS = {
    "1": (
        r"Establishes the core mechanisms — asymmetric error penalties, "
        r"evidence ambiguity, and peer-aggregation costs — that produce expert "
        r"trust fragility (D1), difficulty-dependent erosion (D2), and "
        r"cognitive-cost-sustained expert reliance (D3) in a stationary world "
        r"with independent trials and binary recommendations."
    ),
    "2": (
        r"Extends the base model by giving sources persistent internal "
        r"estimates that update across trials and by introducing cyclic "
        r"evidence regime shifts, testing whether institutional inertia "
        r"combined with environmental change produces trust hysteresis (D4) "
        r"and whether D1 persists when trials represent an evolving situation "
        r"rather than independent questions."
    ),
    "3": (
        r"Builds on the memory extension by replacing binary recommendations "
        r"and all-or-nothing correctness scoring with continuous "
        r"recommendations and partial-credit correctness, isolating evaluation "
        r"granularity as the key boundary condition that buffers the "
        r"asymmetric-penalty mechanisms underlying D1 and D4."
    ),
    "d5-1": (
        r"Applied across all three model variants, this manipulation "
        r"introduces landscape clustering ($\rho_{\mathrm{clust}}$) and "
        r"correlated peer exposure ($\rho_{\mathrm{peer}}$) to test whether "
        r"their joint presence — but neither alone — produces a bimodal trust "
        r"distribution across otherwise identical societies, and whether "
        r"graded evaluation buffers this bifurcation just as it buffers D1."
    ),
}


def model_description(study: str) -> str:
    """Return the 1-2 sentence model description for a study code."""
    return MODEL_DESCRIPTIONS.get(study, "")


def apply_global_style() -> None:
    """Inject app-wide CSS.

    Widens the main content column so side-by-side heatmaps (e.g. the three
    paper-style extension slices) are not compressed into the default narrow
    block.
    """
    st.html(
        """
<style>
[data-testid="stMainBlockContainer"] {
    max-width: 1000px !important;
}
</style>
"""
    )


# Glossary display names for keys in PARAMETER_HELP, grouped by section.
# The definition text is reused from PARAMETER_HELP so there is a single source
# of truth per term.
GLOSSARY_LABELS = {
    "p_expert": "p(Expert)",
    "p_peers": "p(Peers)",
    "trust": "Trust",
    "accuracy": "Accuracy",
    "accuracy_gap": "Accuracy gap",
    "steady_state": "Steady-state mean",
    "full_range": "Full-range mean",
    "ci": "95% CI",
    "feedback": "Feedback mode",
    "mu_e": "$\\mu_E$ / evidence strength",
    "c_pen": "$c_{\\mathrm{pen}}$ / asymmetric penalty",
    "sigma_e": "$\\sigma_E$ / evidence noise",
    "sigma_expert": "$\\sigma_{\\mathrm{expert}}$ / Expert noise",
    "sigma_peers_multiplier": "Peers noise multiplier",
    "m_peers": "$m_{\\mathrm{peers}}$ / number of peers",
    "f_peers": "$f_{\\mathrm{peers}}$ / peers sampling fraction",
    "lr_base": "$\\alpha_{\\mathrm{base}}$ / learning rate",
    "landscape_size": "$L$ / landscape size",
    "peer_cost_weights": "Peer cost weights",
    "tau": "$\\tau$ / decision temperature",
    "w_init_expert": "Initial trust in Expert",
    "w_init_peers": "Initial trust in Peers",
    "trials": "Trials",
    "replications": "Replications",
    "d_t": "$d_T$ / Expert inertia",
    "cyclic_regime": "Cyclic regime",
    "stationary_regime": "Stationary regime",
    "hysteresis": "Hysteresis",
    "baseline_init": "Baseline initialization",
    "post_collapse_init": "Post-collapse initialization",
    "rho_clust": "$\\rho_{\\mathrm{clust}}$ / landscape clustering",
    "rho_peer": "$\\rho_{\\mathrm{peer}}$ / peer correlation",
    "bifurcation": "Bifurcation",
    "sd_runs": "SD across runs",
    "aggregate_steady": "Steady-state aggregation",
}

GLOSSARY_GROUPS = [
    (
        "Common outputs",
        [
            "p_expert",
            "p_peers",
            "trust",
            "accuracy",
            "accuracy_gap",
            "steady_state",
            "full_range",
            "ci",
        ],
    ),
    (
        "Base Model parameters",
        [
            "mu_e",
            "c_pen",
            "sigma_e",
            "tau",
            "lr_base",
            "landscape_size",
            "peer_cost_weights",
        ],
    ),
    (
        "Memory and Graded-Evaluation parameters",
        [
            "d_t",
            "cyclic_regime",
            "stationary_regime",
            "hysteresis",
            "baseline_init",
            "post_collapse_init",
        ],
    ),
    (
        "Polarization Extension parameters",
        ["rho_clust", "rho_peer", "bifurcation", "sd_runs"],
    ),
    (
        "Live Simulator-only parameters",
        [
            "sigma_expert",
            "sigma_peers_multiplier",
            "m_peers",
            "f_peers",
            "w_init_expert",
            "w_init_peers",
            "trials",
            "replications",
        ],
    ),
]


def render_glossary() -> None:
    """Render a compact glossary for public-facing orientation."""
    with st.expander("Parameter and metric glossary"):
        lines = []
        for section, keys in GLOSSARY_GROUPS:
            lines.append(f"**{section}**")
            lines.append("")
            for key in keys:
                label = GLOSSARY_LABELS.get(key, key)
                lines.append(f"- **{label}**: {PARAMETER_HELP[key]}")
            lines.append("")
        st.markdown("\n".join(lines))


def metadata_sidebar(title: str, items: list[tuple[str, str]]) -> None:
    """Render compact condition metadata as stacked lines for the sidebar.

    Keeps all condition and simulation parameters in the sidebar alongside the
    controls. Values may include trusted HTML snippets such as <sub>...</sub>;
    labels are escaped, values are not.
    """
    lines = []
    for label, value in items:
        lines.append(
            f"<div style='margin:0.15rem 0;'><strong>{html.escape(label)}:</strong> {value}</div>"
        )
    st.markdown(
        f"<div style='font-size:0.82rem; color:rgba(49,51,63,0.7); margin-top:0.6rem;'>{title}</div>"
        + "".join(lines),
        unsafe_allow_html=True,
    )
