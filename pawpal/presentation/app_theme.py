"""Load the current stylesheet on every app run."""
from pathlib import Path
from base64 import b64encode
import streamlit as st


@st.cache_data
def _asset_data(name):
    return b64encode((Path(__file__).parent.parent.parent / "assets" / name).read_bytes()).decode("ascii")


def apply_theme():
    assets = Path(__file__).parent.parent.parent / "assets"
    css = "\n".join((assets / name).read_text(encoding="utf8") for name in ("app.css", "calendar.css"))
    workspace = (assets / "workspace.css").read_text(encoding="utf8")
    workspace = workspace.replace("__PLANNER_FONT__", "data:font/ttf;base64," + _asset_data("fonts/DMSans.ttf"))
    workspace = workspace.replace("__PLANNER_ROOM__", "data:image/webp;base64," + _asset_data("planner-room.webp"))
    st.html("<style>" + css + "\n" + workspace + "</style>")


def favicon():
    return str(Path(__file__).parent.parent.parent / "assets" / "favicon.png")
