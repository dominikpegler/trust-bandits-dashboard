import streamlit as st

from dashboard import loaders, plotting

st.set_page_config(page_title="Trajectory Explorer", layout="wide")
st.title("Trajectory Explorer")

studies = loaders.available_studies()
if not studies:
    st.warning("No data in the database. Run `python scripts/ingest.py`.")
    st.stop()

with st.sidebar:
    st.header("Condition")
    study = st.selectbox("Study", studies)
    params = loaders.condition_params(study)
    if not params or not params.get("mu_e"):
        st.warning("No conditions for this study.")
        st.stop()
    feedback = st.selectbox("Feedback mode", params["feedback_mode"])
    mu_e = st.selectbox("Evidence strength (mu_E)", params["mu_e"])
    c_pen = st.selectbox("Asymmetric penalty (c_pen)", params["c_pen"])
    metric = st.selectbox(
        "Metric",
        ["p_expert", "trust", "accuracy"],
        format_func=lambda m: {
            "p_expert": "P(Expert)",
            "trust": "Trust (Expert vs Peers)",
            "accuracy": "Accuracy (Expert vs Peers)",
        }[m],
    )
    steady = st.checkbox("Steady-state (second half of trials)", value=False)

cid = loaders.condition_id(
    study, feedback, "binary", "stationary", float(mu_e), float(c_pen)
)
if cid is None:
    st.warning("No trial data for this condition (trials may not be loaded).")
    st.stop()

df = loaders.trajectory_data(cid, steady=steady)
if df.empty:
    st.warning("No trial data for this condition.")
    st.stop()

fig = plotting.trajectory_figure(
    df,
    metric,
    title=f"{study} · feedback={feedback} · mu_E={mu_e} · c_pen={c_pen}",
)
st.plotly_chart(fig, use_container_width=True)

with st.expander("Show data table"):
    st.dataframe(df)
