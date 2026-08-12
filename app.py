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

apply_global_style()


def overview_page() -> None:
    st.title("Trust-Bandits Explorer")
    st.caption(
        "Explore the simulation data behind *Why Even Accurate Experts Lose "
        "Trust* and run single live simulations with your own parameter "
        "combinations."
    )

    st.markdown(
        "The models are designed to exhibit five trust dynamics:\n\n"
        "- **D1 — Expert trust fragility**: Even when the Expert is more "
        "accurate (positive accuracy gap), asymmetric penalties "
        "($c_{\\mathrm{pen}}$) can drive $p(\\mathrm{Expert})$ below 0.5.\n"
        "- **D2 — Difficulty-dependent erosion**: Trust in the Expert erodes "
        "as evidence ambiguity ($\\mu_E$) increases.\n"
        "- **D3 — Cognitive-cost-sustained reliance**: $p(\\mathrm{Expert})$ stays "
        "high when gathering peer information is costly (**peer cost "
        "weights**).\n"
        "- **D4 — Trust hysteresis**: Under cyclic regime shifts, trust "
        "depends on history (**hysteresis**), not just current parameters.\n"
        "- **D5 — Polarization**: Landscape clustering "
        "($\\rho_{\\mathrm{clust}}$) plus correlated peer exposure "
        "($\\rho_{\\mathrm{peer}}$) splits otherwise identical communities (agents) into "
        "expert-trust and peer-trust modes (**bifurcation**)."
    )

    meta = loaders.get_meta()
    if not meta.empty:
        ts = meta.iloc[0]["ingest_timestamp"]
        codes = [c.strip() for c in str(meta.iloc[0]["studies"]).split(",")]
        names = [loaders.study_label(c) for c in codes]
        st.info(f"Data as of **{ts}** · models: {', '.join(names)}")
    else:
        st.warning("Database is empty. Run `python scripts/ingest.py` to populate it.")

    st.markdown(
        "Each model page includes its own description. A parameter and metric "
        "glossary is available below. Use the sidebar to explore the base, "
        "memory, graded-evaluation, polarization, and live-simulator pages."
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
