import streamlit as st

from dashboard.extension_sections import render_extension_page

st.set_page_config(page_title="Memory Model", layout="wide")
st.title("Memory Model: Parameter Landscape and Hysteresis")

render_extension_page("2")
