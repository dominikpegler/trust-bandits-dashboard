import streamlit as st

from dashboard import loaders, plotting
from dashboard.loaders import fixed_parameters_html
from dashboard.ui import help_text, metadata_sidebar, model_description

REP_MU = 0.65
REP_CPEN = 6.0

st.title("Base Model")
st.markdown(model_description("1"))

if "1" not in loaders.available_studies():
    st.warning(
        "No base-model data in the database. Run `python scripts/ingest.py --studies 1`."
    )
    st.stop()

with st.sidebar:
    st.header("Controls")
    feedback = st.selectbox(
        "Feedback mode", ["full", "partial"], help=help_text("feedback")
    )
    steady = st.checkbox(
        "Aggregate metric means over steady state (second half of trials)",
        value=True,
        help=help_text("aggregate_steady"),
    )

heat = loaders.base_heatmap_cells(feedback, steady=steady)
if heat.empty:
    st.warning("No base-model heatmap data for this selection.")
    st.stop()

mu_levels = sorted(heat["mu_e"].unique())
pen_levels = sorted(heat["c_pen"].unique())
with st.sidebar:
    st.header("Selected condition")
    selected_mu = float(
        st.selectbox(
            r"Evidence strength ($\mu_E$)",
            mu_levels,
            index=mu_levels.index(REP_MU) if REP_MU in mu_levels else 0,
            help=help_text("mu_e"),
        )
    )
    selected_c_pen = float(
        st.selectbox(
            r"Penalty ($c_{\mathrm{pen}}$)",
            pen_levels,
            index=pen_levels.index(REP_CPEN) if REP_CPEN in pen_levels else 0,
            help=help_text("c_pen"),
        )
    )

n_runs = loaders.condition_n_runs(
    "1", feedback, "binary", "stationary", selected_mu, selected_c_pen
)
cid = loaders.condition_id(
    "1", feedback, "binary", "stationary", selected_mu, selected_c_pen
)
_traj = loaders.trajectory_data(cid, steady=False) if cid is not None else None
n_trials = int(_traj["trial"].max()) if _traj is not None and not _traj.empty else None

with st.sidebar:
    metadata_sidebar(
        "Condition metadata",
        [
            ("N", f"{n_runs} runs per cell" if n_runs else "n/a"),
            ("T", f"{n_trials} trials" if n_trials else "n/a"),
            ("Swept", "μ<sub>E</sub> × c<sub>pen</sub>"),
            (
                "Fixed",
                fixed_parameters_html("1"),
            ),
        ],
    )

st.subheader("Parameter landscape heatmaps")
st.markdown(
    "Color = mean $p(\\mathrm{Expert})$; white numbers = accuracy gap (Expert − Peers); "
    "elevated areas = fragility regions (Expert more accurate yet $p(\\mathrm{Expert}) < 0.5$); "
    "dark outline = the selected condition below."
)
st.plotly_chart(
    plotting.base_paradox_heatmap_figure(heat, feedback, selected_mu, selected_c_pen),
    use_container_width=True,
)


with st.expander("Explore other metrics"):
    metric = st.selectbox(
        "Metric",
        ["acc_expert", "acc_peers", "trust_expert", "trust_peers"],
        format_func=lambda m: plotting.METRIC_LABELS.get(m, m),
    )
    heat = loaders.base_metric_heatmap_cells(
        study="1",
        feedback_mode=feedback,
        regime="stationary",
        x_var="mu_e",
        y_var="c_pen",
        fixed={},
        steady=steady,
        metric=metric,
    )
    if heat.empty:
        st.warning("No data for this selection.")
    else:
        st.plotly_chart(
            plotting.parameter_metric_heatmap_figure(
                heat,
                x_label="μ<sub>E</sub>",
                y_label="c<sub>pen</sub>",
                metric=metric,
                title="",
                selected_x=selected_mu,
                selected_y=selected_c_pen,
            ),
            use_container_width=True,
        )


st.subheader("Selected condition dynamics")
cid = loaders.condition_id(
    "1", feedback, "binary", "stationary", selected_mu, selected_c_pen
)
if cid is None:
    st.warning("No trial data for the selected condition.")
else:
    err = loaders.base_condition_error_trace_data(cid)
    if not err.empty:
        st.plotly_chart(
            plotting.error_locked_trust_figure(err), use_container_width=True
        )
    traj = loaders.trajectory_data(cid, steady=False)
    if not traj.empty:
        cutoff = int(traj["trial"].max()) // 2
        ss = traj[traj["trial"] > cutoff]
        stats = {
            "trust": {
                "steady": (
                    ss["mean_trust_expert"].mean(),
                    ss["mean_trust_peers"].mean(),
                ),
                "full": (
                    traj["mean_trust_expert"].mean(),
                    traj["mean_trust_peers"].mean(),
                ),
            },
            "accuracy": {
                "steady": (ss["mean_acc_expert"].mean(), ss["mean_acc_peers"].mean()),
                "full": (traj["mean_acc_expert"].mean(), traj["mean_acc_peers"].mean()),
            },
            "p_expert": {
                "steady": ss["mean_p_expert"].mean(),
                "full": traj["mean_p_expert"].mean(),
            },
        }
        st.plotly_chart(
            plotting.trajectory_figure(
                traj,
                "trust",
                title="Trust",
                stats=stats["trust"],
            ),
            use_container_width=True,
        )
        st.plotly_chart(
            plotting.trajectory_figure(
                traj,
                "accuracy",
                title="Rolling accuracy",
                stats=stats["accuracy"],
            ),
            use_container_width=True,
        )
        st.plotly_chart(
            plotting.trajectory_figure(
                traj,
                "p_expert",
                title="p(Expert)",
                stats=stats["p_expert"],
            ),
            use_container_width=True,
        )
        with st.expander("Selected-condition trajectory data"):
            st.dataframe(traj, use_container_width=True)

st.subheader("D2/D3: Difficulty and cognitive-cost effects")
d2 = loaders.base_difficulty_data(feedback)
d3 = loaders.base_cost_data(feedback)
if d2.empty or d3.empty:
    st.warning(
        "D2/D3 data are missing. Run a full ingest to load base-model support tables."
    )
else:
    st.plotly_chart(plotting.source_accuracy_by_mu_figure(d2), use_container_width=True)
    st.plotly_chart(
        plotting.choice_area_ci_figure(
            d2,
            "mu_e",
            title="p(Expert) by evidence strength",
            x_label="Evidence strength (μ<sub>E</sub>)",
        ),
        use_container_width=True,
    )
    st.plotly_chart(
        plotting.choice_area_ci_figure(
            d3,
            "cost_sum",
            title="p(Expert) by cognitive cost",
            x_label="Cognitive cost weight (w<sub>N</sub> + w<sub>var</sub>)",
        ),
        use_container_width=True,
    )
