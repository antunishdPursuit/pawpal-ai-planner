"""Approved semantic tokens shared by the planner interface."""
from pathlib import Path
import streamlit as st

CSS = """
<style>
:root {
 --paw-page: #F7F8F4; --paw-surface: #FFFFFF; --paw-text: #18332B;
 --paw-primary: #245C45; --paw-border: #CBD5CB; --paw-muted: #4C6358;
 --paw-warning: #784600; --paw-warning-bg: #FFF4DC;
 --paw-error: #8C2525; --paw-error-bg: #FDECEC;
 --paw-success: #245C45; --paw-success-bg: #EAF4EC;
 --paw-space-1: 4px; --paw-space-2: 8px; --paw-space-3: 12px;
 --paw-space-4: 16px; --paw-space-6: 24px; --paw-space-8: 32px;
 --paw-radius: 12px; --paw-width: 1440px; --paw-control: 44px;
 --paw-title: 28px; --paw-heading: 20px; --paw-body: 16px; --paw-small: 14px;
}
.stApp { background: var(--paw-page); color: var(--paw-text); }
.stMainBlockContainer { max-width: var(--paw-width); padding-top: var(--paw-space-8); }
h1 { font-size: var(--paw-title) !important; line-height: var(--paw-space-8) !important; }
h2, h3 { font-size: var(--paw-heading) !important; }
button, input, [data-baseweb="select"] { min-height: var(--paw-control); }
button:focus-visible, input:focus-visible, textarea:focus-visible,
[role="tab"]:focus-visible { outline: 3px solid var(--paw-primary) !important; outline-offset: 2px; }
[data-testid="stVerticalBlockBorderWrapper"] {
 border-color: var(--paw-border); border-radius: var(--paw-radius);
}
[data-testid="stCaptionContainer"] { color: var(--paw-muted); font-size: var(--paw-small); }
[data-testid="stAlert"] { border-radius: var(--paw-radius); }
@media (max-width: 768px) {
 .st-key-week_grid { display: none; }
 .stMainBlockContainer { padding: var(--paw-space-4); }
 [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
 [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
   min-width: min(100%, 280px); flex: 1 1 100%;
 }
}
@media (prefers-reduced-motion: reduce) {
 *, *::before, *::after { animation: none !important; transition: none !important; }
}
</style>
"""


def apply_theme():
    st.markdown(CSS, unsafe_allow_html=True)


def favicon():
    return str(Path(__file__).parent / "assets" / "favicon.png")
