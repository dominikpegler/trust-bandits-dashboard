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
        r"and whether B1 persists when trials represent an evolving situation "
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
        r"graded evaluation buffers this bifurcation just as it buffers B1."
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
    st.markdown(
        """
<style>
[data-testid="stMainBlockContainer"] .block-container {
    max-width: 1400px !important;
}
</style>
""",
        unsafe_allow_html=True,
    )


def render_glossary() -> None:
    """Render a compact glossary for public-facing orientation."""
    with st.expander("Parameter and metric glossary"):
        st.markdown(
            r"""
**Common outputs**

- **p(Expert)**: Probability that the simulated agent chooses the Expert rather than Peers on a trial.
- **p(Peers)**: Probability that the simulated agent chooses Peers; this is 1 - p(Expert).
- **Trust**: Learned source weight used when deciding whether to rely on the Expert or Peers.
- **Accuracy**: Fraction of trials on which a source gives the correct answer.
- **Accuracy gap**: Expert accuracy minus Peers accuracy; positive values mean the Expert is more accurate.
- **Steady-state mean**: Mean over the second half of trials, used as the primary summary once behavior has settled.
- **Full-range mean**: Mean over all trials, useful for seeing the effect of early transient behavior.
- **95% CI**: Confidence interval across simulation runs or replications.

**Base Model parameters**

- **$\mu_E$ / evidence strength**: Task evidence strength; larger values make the Expert's signal more informative.
- **$c_{\mathrm{pen}}$ / asymmetric penalty**: Penalty for high-confidence errors; larger values make mistakes more costly.
- **$\sigma_E$ / evidence noise**: Noise in the task evidence available to the model.
- **$\tau$ / decision temperature**: Lower values make choices more deterministic from current trust.
- **$\alpha_{\mathrm{base}}$ / learning rate**: Trust-update rate; larger values adapt faster to recent outcomes.
- **$L$**: Number of landscape/task items in the simulated environment.
- **Peer cost weights**: Cognitive-cost terms attached to peer information use.

**Memory and Graded-Evaluation parameters**

- **$d_T$ / Expert inertia**: Memory-timescale parameter; larger values make source-memory effects persist longer.
- **Cyclic regime**: Environment alternates between evidence-strength values over repeated cycles.
- **Stationary regime**: Environment keeps the same evidence-strength setting over time.
- **Hysteresis**: Later trust can depend on earlier trust history, even under the same current parameters.
- **Baseline initialization**: Hysteresis trajectory initialized with balanced Expert and Peers trust.
- **Post-collapse initialization**: Hysteresis trajectory initialized after an Expert-trust collapse.

**Polarization Extension parameters**

- **$\rho_{\mathrm{clust}}$ / landscape clustering**: Controls how similar nearby agents' environments are.
- **$\rho_{\mathrm{peer}}$ / peer correlation**: Controls how correlated peer signals are.
- **Bifurcation**: Split of runs into low-Expert-trust and high-Expert-trust modes under the same parameters.
- **SD across runs**: Standard deviation across runs; high values indicate stronger run-to-run divergence.

**Live Simulator-only parameters**

- **$\sigma_{\mathrm{expert}}$ / Expert noise**: Noise in the Expert's advice.
- **Peers noise multiplier**: Multiplier applied to Expert noise to set Peers noise.
- **$m_{\mathrm{peers}}$ / number of peers**: Number of peer advisers sampled by the model.
- **$f_{\mathrm{peers}}$ / peers sampling fraction**: Fraction of available peer information sampled on each trial.
- **Initial trust**: Starting trust assigned to each source before learning from outcomes.
- **Trials**: Number of sequential decisions in each simulation run.
- **Replications**: Number of independent simulation runs averaged together.
"""
        )


def metadata_box(items: list[tuple[str, str]]) -> None:
    """Render compact, consistent condition metadata.

    Values may include trusted HTML snippets such as <sub>...</sub>. Labels are
    escaped; values are not escaped so math-like HTML can render consistently.
    """
    chips = []
    for label, value in items:
        chips.append(
            f"<span class='metadata-chip'><strong>{html.escape(label)}:</strong> {value}</span>"
        )
    st.markdown(
        """
<style>
.metadata-box {
  border: 1px solid rgba(49, 51, 63, 0.18);
  background: rgba(250, 250, 252, 0.9);
  border-radius: 0.5rem;
  padding: 0.55rem 0.65rem;
  margin: 0.4rem 0 1rem 0;
  line-height: 1.65;
  font-size: 0.94rem;
}
.metadata-chip {
  display: inline-block;
  margin-right: 1.1rem;
}
</style>
"""
        + "<div class='metadata-box'>"
        + "".join(chips)
        + "</div>",
        unsafe_allow_html=True,
    )
