import plotly.graph_objects as go
import streamlit as st

from dashboard import loaders, plotting
from dashboard.loaders import fixed_parameters_html
from dashboard.ui import help_text, metadata_box, model_description

st.title("Polarization Extension")

st.markdown(model_description("d5-1"))
st.markdown(
    "Per-run steady-state p(Expert) distributions over the landscape-clustering "
    "($\\rho_{clust}$, rows) × peer-correlation ($\\rho_{peer}$, columns) grid, "
    "for the base model. The red dashed line marks p(Expert) = 0.5. Bimodality "
    "(a split into a peer-trust and an expert-trust mode) emerges at high "
    "$\\rho_{clust}$ and $\\rho_{peer}$."
)

# Only the base model has per-run polarization data so far.
d5_study = "d5-1"
d5 = [s for s in loaders.available_studies() if s == d5_study]
if not d5:
    st.warning("No polarization-extension data in the database. Run `python scripts/ingest.py --studies d5`.")
    st.stop()

with st.sidebar:
    st.header("Controls")
    st.caption("Polarization extension (base model)")
    feedback = st.selectbox("Feedback mode", ["full", "partial"], help=help_text("feedback"))

clust_levels, rho_levels = loaders.d5_grid_levels(d5_study)
df = loaders.d5_runs_data(d5_study, feedback, "p_expert")
if df.empty:
    st.warning("No data for this selection.")
    st.stop()

n_runs = df["run_id"].nunique()
metadata_box(
    [
        ("Model", "Base model"),
        ("Extension", "Polarization"),
        ("Feedback", feedback),
        ("N", f"{n_runs} runs per cell"),
        ("T", "50 trials"),
        ("Aggregation", "steady-state p(Expert)"),
        ("Grid", "ρ<sub>clust</sub> × ρ<sub>peer</sub>"),
        ("Selected", "μ<sub>E</sub>=0.65, c<sub>pen</sub>=6"),
        ("Fixed", fixed_parameters_html("d5-1")),
    ]
)
st.caption(
    f"$\\rho_{{\\mathrm{{clust}}}}$: {help_text('rho_clust')} "
    f"$\\rho_{{\\mathrm{{peer}}}}$: {help_text('rho_peer')} "
    f"Bifurcation: {help_text('bifurcation')}"
)
fig = plotting.d5_bifurcation_figure(
    df, clust_levels, rho_levels, "p_expert",
    title=f"Polarization extension (base model) · feedback={feedback} · N = {n_runs} runs per cell",
)
st.plotly_chart(fig, use_container_width=True)

with st.expander("Explore trust distributions"):
    trust_metric = st.selectbox(
        "Metric",
        ["trust_expert", "trust_peers"],
        format_func=lambda m: plotting.METRIC_LABELS.get(m, m),
    )
    trust_df = loaders.d5_runs_data(d5_study, feedback, trust_metric)
    if trust_df.empty:
        st.warning("No data for this selection.")
    else:
        st.plotly_chart(
            plotting.d5_bifurcation_figure(
                trust_df,
                clust_levels,
                rho_levels,
                trust_metric,
                title=(
                    f"Polarization trust distribution · {plotting.METRIC_LABELS.get(trust_metric, trust_metric)} "
                    f"· feedback={feedback}"
                ),
            ),
            use_container_width=True,
        )

st.subheader("Bifurcation strength (SD across runs)")
cols = st.columns(2)
for col, fb in zip(cols, ["full", "partial"]):
    with col:
        sd_df = loaders.d5_runs_data(d5_study, fb, "p_expert")
        sd_grid = (
            sd_df.groupby(["clustering", "rho_peers"])["value"]
            .std()
            .reset_index()
            .pivot(index="clustering", columns="rho_peers", values="value")
            .sort_index(ascending=False)
        )
        heat = go.Figure(
            data=go.Heatmap(
                z=sd_grid.values,
                x=[f"{x:.2g}" for x in sd_grid.columns],
                y=[f"{y:.2g}" for y in sd_grid.index],
                colorscale=[[0, "#f7f7f7"], [1, plotting._blend_white(plotting.COLOR_EXPERT)]],
                zmin=0,
                zmax=max(0.25, float(sd_grid.max().max())),
                text=[[f"{v:.2f}" for v in row] for row in sd_grid.values],
                texttemplate="%{text}",
                hovertemplate="ρ<sub>peer</sub>=%{x}<br>ρ<sub>clust</sub>=%{y}<br>SD=%{z:.3f}<extra></extra>",
                colorbar=dict(title="SD"),
            )
        )
        heat.update_layout(
            title=f"feedback={fb}",
            xaxis_title="ρ<sub>peer</sub>",
            yaxis_title="ρ<sub>clust</sub>",
            height=420,
            margin=dict(l=60, r=20, t=60, b=50),
        )
        st.plotly_chart(heat, use_container_width=True)
