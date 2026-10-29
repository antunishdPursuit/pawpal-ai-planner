"""Homepage composition; styling and scrolling have separate owners."""
import base64
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).parent / "assets"


@st.cache_data
def _hero_image():
    return base64.b64encode((ASSETS / "home-pets.webp").read_bytes()).decode("ascii")


def _homepage_html(image):
    """Only trusted project assets enter this HTML; no planner data is rendered."""
    css = (ASSETS / "homepage.css").read_text(encoding="utf8").rstrip("\n") + "\n    "
    markup = (ASSETS / "homepage.html").read_text(encoding="utf8").rstrip("\n") + "\n    "
    script = (ASSETS / "homepage.js").read_text(encoding="utf8").rstrip("\n") + "\n    "
    return "<style>" + css + "</style>" + markup.replace("__HERO_IMAGE__", image) + "<script>" + script + "</script>"


def show_home(open_planner):
    with st.container(key="homepage_navigation", horizontal=True, vertical_alignment="center"):
        st.button("PawPal AI Planner", key="home_brand")
        st.button("Open planner", type="primary", on_click=open_planner, key="home_open_planner")
    st.html(_homepage_html(_hero_image()), unsafe_allow_javascript=True)
