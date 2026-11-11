"""PawPal's required layered-parallax homepage."""
import base64
from pathlib import Path

import streamlit as st
from pawpal.presentation.calendar_presentation import CalendarItem, render_timeline

ASSETS = Path(__file__).parent.parent.parent / "assets"


@st.cache_data
def _hero_image(name):
    return base64.b64encode((ASSETS / name).read_bytes()).decode("ascii")


def _homepage_html():
    """Compose trusted project assets without planner or model-generated data."""
    css = (ASSETS / "homepage.css").read_text(encoding="utf8")
    markup = (ASSETS / "homepage.html").read_text(encoding="utf8")
    script = (ASSETS / "homepage.js").read_text(encoding="utf8")
    for layer in ("room", "dog", "cat"):
        markup = markup.replace(f"__{layer.upper()}_IMAGE__", _hero_image(f"home-{layer}.webp"))
    markup = markup.replace("__BRAND_IMAGE__", _hero_image("favicon.png"))
    preview = render_timeline(["Tomorrow"], [[CalendarItem("Walk Luna", 540, location="The park")]], start_hour=8, end_hour=10)
    markup = markup.replace("__CALENDAR_PREVIEW__", preview)
    return "<style>" + css + "</style>" + markup + "<script>" + script + "</script>"


def show_home(open_planner):
    with st.container(key="homepage_navigation", horizontal=True, vertical_alignment="center"):
        st.button("Open planner", type="primary", on_click=open_planner, key="home_open_planner")
    st.html(_homepage_html(), unsafe_allow_javascript=True)
    with st.container(key="homepage_closing"):
        st.button("Open planner", type="primary", on_click=open_planner, key="home_closing_planner")
