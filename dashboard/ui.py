import html

import streamlit as st


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
