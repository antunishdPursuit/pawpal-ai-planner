"""Load the current stylesheet on every app run."""
from pathlib import Path
import streamlit as st


def apply_theme():
    st.html(Path(__file__).parent / "assets" / "app.css")


def favicon():
    return str(Path(__file__).parent / "assets" / "favicon.png")
