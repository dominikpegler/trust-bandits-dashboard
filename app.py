import streamlit as st

st.set_page_config(
    page_title="Trust-Bandits Explorer",
    page_icon="📊",
    layout="wide",
)

st.title("Trust-Bandits Explorer")
st.caption(
    "Interactive companion to *Why Even Accurate Experts Lose Trust: "
    "A Multi-Agent Reinforcement Learning Model*."
)

from dashboard import db, loaders  # noqa: E402

try:
    db.init_db()
    meta = loaders.get_meta()
    if not meta.empty:
        ts = meta.iloc[0]["ingest_timestamp"]
        studies = meta.iloc[0]["studies"]
        st.info(f"Data as of **{ts}** · studies: {studies}")
    else:
        st.warning("Database is empty. Run `python scripts/ingest.py` to populate it.")
except Exception as e:  # pragma: no cover
    st.error(f"Could not connect to the database: {e}")
    st.stop()

st.markdown(
    """
Use the sidebar pages to explore the simulation results:

- **Heatmap (B1–B3)** — the central paradox: P(Expert) over evidence strength
  (mu_E) and asymmetric penalty (c_pen), plus marginal curves.
- **Trajectory Explorer** — trial-by-trial trust, accuracy, and choice
  probability for a selected condition.
- **Live Simulator** — run a single simulation with new parameters on the fly.
"""
)
