"""Load the current stylesheet on every app run."""
from pathlib import Path
import streamlit as st


def apply_theme():
    assets = Path(__file__).parent / "assets"
    css = "\n".join((assets / name).read_text(encoding="utf8") for name in ("app.css", "calendar.css"))
    st.html("<style>" + css + "</style>")


def favicon():
    return str(Path(__file__).parent / "assets" / "favicon.png")
