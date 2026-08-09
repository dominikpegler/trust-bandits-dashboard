import streamlit as st

from dashboard import loaders, plotting
from dashboard.ui import metadata_box

REP_MU = 0.65
REP_CPEN = 6.0

st.set_page_config(page_title="Base Model Results", layout="wide")
st.title("Base Model Results: Expert Fragility, Difficulty, and Cost")

if "1" not in loaders.available_studies():
    st.warning("No base-model data in the database. Run `python scripts/ingest.py --studies 1`.")
    st.stop()

with st.sidebar:
    st.header("Controls")
    feedback = st.selectbox("Feedback mode", ["full", "partial"])
    steady = st.checkbox("Use steady-state aggregates (second half of trials)", value=True)

heat = loaders.base_heatmap_cells(feedback, steady=steady)
if heat.empty:
    st.warning("No base-model heatmap data for this selection.")
    st.stop()

mu_levels = sorted(heat["mu_e"].unique())
pen_levels = sorted(heat["c_pen"].unique())
with st.sidebar:
    st.header("Selected condition")
    selected_mu = float(st.selectbox(
        "Evidence strength", mu_levels,
        index=mu_levels.index(REP_MU) if REP_MU in mu_levels else 0,
    ))
    st.caption(r"$\mu_E$")
    selected_c_pen = float(st.selectbox(
        "Penalty", pen_levels,
        index=pen_levels.index(REP_CPEN) if REP_CPEN in pen_levels else 0,
    ))
    st.caption(r"$c_{\mathrm{pen}}$")

metadata_box(
    [
        ("Model", "Base model"),
        ("Feedback", feedback),
        ("N", "1000 runs per cell"),
        ("T", "50 trials"),
        ("Swept", "μ<sub>E</sub> × c<sub>pen</sub>"),
        ("Selected", f"μ<sub>E</sub>={selected_mu}, c<sub>pen</sub>={selected_c_pen:g}"),
        ("Fixed", "L=32, σ<sub>E</sub>=0.1, τ=0.3, α<sub>base</sub>=0.1, peers cost=(0.5, 0.25)"),
    ]
)

st.subheader("D1: Expert fragility heatmap")
st.markdown(
    "Color encodes mean p(Expert). White numbers are the accuracy gap "
    "(Expert − Peers). White outlines mark expert-fragility cells where the "
    "Expert is more accurate but p(Expert) < 0.5. The red outline marks the "
    "currently selected condition used below."
)
st.plotly_chart(
    plotting.base_paradox_heatmap_figure(heat, feedback, selected_mu, selected_c_pen),
    use_container_width=True,
)

st.subheader("Selected condition dynamics")
cid = loaders.condition_id("1", feedback, "binary", "stationary", selected_mu, selected_c_pen)
if cid is None:
    st.warning("No trial data for the selected condition.")
else:
    err = loaders.base_condition_error_trace_data(cid)
    if not err.empty:
        st.plotly_chart(plotting.error_locked_trust_figure(err), use_container_width=True)
    traj = loaders.trajectory_data(cid, steady=False)
    if not traj.empty:
        cutoff = int(traj["trial"].max()) // 2
        ss = traj[traj["trial"] > cutoff]
        stats = {
            "trust": {
                "steady": (ss["mean_trust_expert"].mean(), ss["mean_trust_peers"].mean()),
                "full": (traj["mean_trust_expert"].mean(), traj["mean_trust_peers"].mean()),
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
                title="Selected condition: trust",
                stats=stats["trust"],
            ),
            use_container_width=True,
        )
        st.plotly_chart(
            plotting.trajectory_figure(
                traj,
                "accuracy",
                title="Selected condition: rolling accuracy",
                stats=stats["accuracy"],
            ),
            use_container_width=True,
        )
        st.plotly_chart(
            plotting.trajectory_figure(
                traj,
                "p_expert",
                title="Selected condition: p(Expert)",
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
    st.warning("D2/D3 data are missing. Run a full ingest to load base-model support tables.")
else:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.plotly_chart(plotting.source_accuracy_by_mu_figure(d2), use_container_width=True)
    with col2:
        st.plotly_chart(
            plotting.choice_area_ci_figure(
                d2,
                "mu_e",
                title="p(Expert) by evidence strength",
                x_label="Evidence strength (μ<sub>E</sub>)",
            ),
            use_container_width=True,
        )
    with col3:
        st.plotly_chart(
            plotting.choice_area_ci_figure(
                d3,
                "cost_sum",
                title="p(Expert) by cognitive cost",
                x_label="Cognitive cost weight (w<sub>N</sub> + w<sub>var</sub>)",
            ),
            use_container_width=True,
        )

with st.expander("Explore other base-model metrics"):
    metric = st.selectbox(
        "Metric",
        ["p_expert", "acc_expert", "acc_peers", "trust_expert", "trust_peers"],
        format_func=lambda m: plotting.METRIC_LABELS.get(m, m),
    )
    df = loaders.heatmap_data("1", feedback, "binary", "stationary", steady=steady, metric=metric)
    if df.empty:
        st.warning("No data for this selection.")
    else:
        n_runs = loaders.condition_n_runs("1", feedback, "binary", "stationary", REP_MU, REP_CPEN)
        n_caption = f" · N = {n_runs} simulations" if n_runs else ""
        st.plotly_chart(
            plotting.heatmap_figure(
                df,
                metric,
                title=f"{plotting.METRIC_LABELS.get(metric, metric)} · feedback={feedback}{n_caption}",
            ),
            use_container_width=True,
        )
