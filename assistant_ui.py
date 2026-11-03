"""Persistent site-wide assistant component and event bridge."""
from pathlib import Path
import streamlit as st
from gemini_planner import is_configured


@st.cache_resource
def assistant_component():
    root = Path(__file__).parent / "assets"
    return st.components.v2.component(
        "pawpal_assistant", html='<div class="paw-assistant-root"></div>',
        css=(root / "assistant.css").read_text(encoding="utf-8"),
        js=(root / "assistant.js").read_text(encoding="utf-8"), isolate_styles=False,
    )


def render_assistant():
    receipts = st.session_state.setdefault("assistant_receipts", [])
    result = assistant_component()(key="site_assistant", data={
        "configured": is_configured(), "receipts": receipts,
        "page": st.session_state.get("page", "Home"),
    }, default={"outbox": []}, on_outbox_change=lambda: None, height=0)
    handled = {r["id"] for r in receipts}
    for event in result.outbox or []:
        if event.get("id") not in handled:
            receipts.append({"id": event["id"], "message": "The assistant connection is ready."})
            st.rerun()
