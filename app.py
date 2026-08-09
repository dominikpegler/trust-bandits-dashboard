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
        codes = [c.strip() for c in str(meta.iloc[0]["studies"]).split(",")]
        names = [loaders.study_label(c) for c in codes]
        st.info(f"Data as of **{ts}** · models: {', '.join(names)}")
    else:
        st.warning("Database is empty. Run `python scripts/ingest.py` to populate it.")
except Exception as e:  # pragma: no cover
    st.error(f"Could not connect to the database: {e}")
    st.stop()

st.markdown(
    r"""
Use the sidebar pages to explore the simulation results:

- **Base Model** — expert fragility, difficulty effects, and cognitive-cost
  effects.
- **Memory Model** — source-memory parameter landscape and hysteresis.
- **Graded-Evaluation Model** — continuous-evaluation parameter landscape and
  hysteresis.
- **Polarization Extension** — echo-chamber bifurcation over the
  landscape-clustering × peer-correlation grid (base model).
- **Live Simulator** — run a single simulation with new parameters on the fly.
"""
)
