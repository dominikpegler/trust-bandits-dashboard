import streamlit as st

st.set_page_config(
    page_title="Trust-Bandits Explorer",
    page_icon="📊",
    layout="wide",
)

from dashboard import db, loaders  # noqa: E402
from dashboard.ui import apply_global_style, render_glossary  # noqa: E402

try:
    db.init_db()
except Exception as e:  # pragma: no cover
    st.error(f"Could not connect to the database: {e}")
    st.stop()


def overview_page() -> None:
    st.title("Trust-Bandits Explorer")
    st.caption(
        "Interactive companion to *Why Even Accurate Experts Lose Trust: "
        "A Multi-Agent Reinforcement Learning Model*."
    )

    apply_global_style()

    meta = loaders.get_meta()
    if not meta.empty:
        ts = meta.iloc[0]["ingest_timestamp"]
        codes = [c.strip() for c in str(meta.iloc[0]["studies"]).split(",")]
        names = [loaders.study_label(c) for c in codes]
        st.info(f"Data as of **{ts}** · models: {', '.join(names)}")
    else:
        st.warning("Database is empty. Run `python scripts/ingest.py` to populate it.")

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
    render_glossary()


navigation = st.navigation(
    [
        st.Page(overview_page, title="Trust-Bandits Explorer", icon="📊"),
        st.Page("pages/1_Base_Model.py", title="Base Model"),
        st.Page("pages/2_Memory_Model.py", title="Memory Model"),
        st.Page("pages/3_Graded_Evaluation_Model.py", title="Graded-Evaluation Model"),
        st.Page("pages/4_Polarization_Extension.py", title="Polarization Extension"),
        st.Page("pages/6_Live_Simulator.py", title="Live Simulator"),
    ]
)
navigation.run()
