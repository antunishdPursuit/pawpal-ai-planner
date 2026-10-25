"""Small native-browser voice surface inside the task editor."""
import json
import sqlite3
from time import time
from pathlib import Path
import streamlit as st
from gemini_planner import decode_proposal, PlannerError, is_configured
from voice_planner import live_credential, transcribe
from voice_completion import save_voice_task


@st.cache_resource
def voice_component():
    root = Path(__file__).parent / "assets"
    return st.components.v2.component(
        "pawpal_voice", html=(root / "voice.html").read_text(encoding="utf-8"),
        css=(root / "voice.css").read_text(encoding="utf-8"),
        js=(root / "voice.js").read_text(encoding="utf-8"),
    )


def render_voice(store, owner, profiles, replace_allowed):
    if st.session_state.get("voice_error"):
        st.error(st.session_state.voice_error)
    credential = st.session_state.get("voice_credential")
    if credential and (credential.get("owner_id") != owner.owner_id or time() - credential.get("issued_at", 0) >= 360):
        st.session_state.pop("voice_credential", None)
        credential = None
    component = voice_component()
    event = component(data={"credential": credential,
                            "configured": is_configured(), "replace_allowed": replace_allowed,
                            "revision": st.session_state.get("voice_event_id")},
                      key=f"voice_{owner.owner_id}", default={"event": None}, on_event_change=lambda: None).event
    if not event or not isinstance(event, dict):
        return
    handled = st.session_state.get("voice_handled_events", [])
    if event.get("id") in handled:
        return
    st.session_state.voice_handled_events = (handled + [event.get("id")])[-20:]
    st.session_state.voice_event_id = event.get("id")
    try:
        if event.get("kind") == "connect":
            st.session_state.pop("voice_error", None)
            st.session_state.voice_credential = live_credential(owner, profiles, st.session_state.get("conversation"))
            st.rerun()
        if event.get("kind") == "dictation":
            st.session_state.pop("voice_error", None)
            with st.spinner("Transcribing..."):
                text = transcribe(event.get("audio"), [pet.name for pet in owner.pets])
            count = st.session_state.get("composer_count", 0)
            existing = st.session_state.get(f"request_{count}", st.session_state.get("pending_request", ""))
            st.session_state.pending_request = (existing.strip() + " " + text).strip()[:2000]
            st.session_state.composer_count = count + 1
            st.session_state.pop("voice_credential", None)
            st.rerun()
        if event.get("kind") == "live_complete":
            if event.get("save_requested") and not event.get("error"):
                credential = st.session_state.get("voice_credential")
                if (not replace_allowed or event.get("confirmation_after_preview") is not True
                        or not credential or credential.get("owner_id") != owner.owner_id
                        or event.get("session_id") != credential.get("session_id")):
                    raise PlannerError("Start a new voice conversation.")
                history = event.get("history", [])
                if not isinstance(history, list):
                    raise PlannerError("Voice confirmation unavailable.")
                utterances = [i["text"] for i in history[-6:] if isinstance(i, dict)
                              and i.get("role") == "user" and isinstance(i.get("text"), str)]
                saved = save_voice_task(store, owner, event.get("proposal"), utterances[-1] if utterances else "",
                                        credential["session_id"], event.get("proposal_id"))
                from task_editor import cancel_editor
                cancel_editor()
                st.session_state.pending_selected_day = saved.due_date
                st.session_state.voice_calendar_target = {"owner_id": owner.owner_id, "pet_id": saved.assigned_pet_id}
                st.session_state.page = "Calendar"
                st.session_state.notice = "Task saved."
                st.rerun()
            st.session_state.pop("voice_credential", None)
            st.session_state.pop("voice_error", None)
            history = event.get("history", [])
            if not isinstance(history, list):
                raise PlannerError("Voice response unavailable. Try again or type.")
            safe = [{"role": item["role"], "text": item["text"][:2000]} for item in history[-6:]
                    if isinstance(item, dict) and item.get("role") in ("user", "assistant") and isinstance(item.get("text"), str)]
            st.session_state.conversation = (st.session_state.get("conversation", []) + safe)[-6:]
            proposal = event.get("proposal")
            if event.get("error"):
                st.session_state.voice_error = "Voice disconnected. Try again or type."
                st.session_state.preview_blocked = True
                proposal = None
            if proposal:
                if not isinstance(proposal, dict):
                    raise PlannerError("Voice response unavailable. Try again or type.")
                if not replace_allowed:
                    raise PlannerError("Allow draft replacement first.")
                result = decode_proposal(json.dumps(proposal), owner)
                if result.draft is None:
                    raise PlannerError("Keep planning or use Manual.")
                st.session_state.task_draft = result.draft
                st.session_state.preview_blocked = False
                st.session_state.conversation_requested = False
            else:
                users = [item["text"] for item in safe if item["role"] == "user"]
                if users:
                    count = st.session_state.get("composer_count", 0)
                    existing = st.session_state.get(f"request_{count}", st.session_state.get("pending_request", ""))
                    st.session_state.pending_request = (existing.strip() + " " + users[-1]).strip()[:2000]
                    st.session_state.composer_count = count + 1
                    st.session_state.preview_blocked = True
                    st.session_state.conversation_requested = True
            st.rerun()
    except (PlannerError, ValueError, TypeError, sqlite3.Error, OSError) as error:
        st.session_state.pop("voice_credential", None)
        proposal = event.get("proposal")
        if isinstance(proposal, dict):
            try:
                candidate = decode_proposal(json.dumps(proposal), owner)
                if candidate.draft:
                    st.session_state.task_draft = candidate.draft
            except PlannerError:
                pass
        st.session_state.preview_blocked = True
        st.session_state.voice_error = str(error) if isinstance(error, PlannerError) else "Could not save this task. Review it before trying again."
        st.rerun()
