import streamlit as st
import plotly.graph_objects as go

from dashboard import loaders, plotting

st.set_page_config(page_title="Heatmap (B1–B3)", layout="wide")
st.title("Heatmap: P(Expert) over evidence strength × penalty")

studies = loaders.available_studies()
base_studies = [s for s in studies if s == "1"]
if not base_studies:
    st.warning("No Study 1 data in the database. Run `python scripts/ingest.py --studies 1`.")
    st.stop()

with st.sidebar:
    st.header("Controls")
    feedback = st.selectbox("Feedback mode", ["full", "partial"])
    metric = st.selectbox(
        "Metric",
        ["p_expert", "acc_expert", "acc_peers", "trust_expert", "trust_peers"],
        format_func=lambda m: plotting.METRIC_LABELS.get(m, m),
    )
    steady = st.checkbox("Steady-state (second half of trials)", value=False)

df = loaders.heatmap_data(
    "1", feedback, "binary", "stationary", steady=steady, metric=metric
)
if df.empty:
    st.warning("No data for this selection.")
    st.stop()

fig = plotting.heatmap_figure(df, metric, title=f"{plotting.METRIC_LABELS.get(metric, metric)} · feedback={feedback}")
st.plotly_chart(fig, use_container_width=True)

st.subheader("Marginal curves")
col1, col2 = st.columns(2)
with col1:
    mu = st.selectbox("Fix evidence strength (mu_E)", sorted(df.columns, key=float))
    m1 = loaders.marginal_data(
        "1", feedback, "binary", "stationary", steady=steady, metric=metric,
        fixed={"mu_e": float(mu)},
    )
    st.plotly_chart(
        plotting.marginal_figure(m1, "c_pen", metric, title=f"vs c_pen · mu_E={mu}"),
        use_container_width=True,
    )
with col2:
    pen = st.selectbox("Fix penalty (c_pen)", sorted(df.index, key=float))
    m2 = loaders.marginal_data(
        "1", feedback, "binary", "stationary", steady=steady, metric=metric,
        fixed={"c_pen": float(pen)},
    )
    st.plotly_chart(
        plotting.marginal_figure(m2, "mu_e", metric, title=f"vs mu_E · c_pen={pen}"),
        use_container_width=True,
    )
