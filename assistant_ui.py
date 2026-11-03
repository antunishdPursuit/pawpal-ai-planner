"""Persistent site-wide assistant component and event bridge."""
from pathlib import Path
from time import time
import sqlite3
import streamlit as st
from gemini_planner import is_configured, PlannerError
from planner_storage import PlannerStore
from assistant_actions import AssistantActions
from assistant_model import respond
from assistant_live import prepare_live


@st.cache_resource
def assistant_component():
    root = Path(__file__).parent / "assets"
    return st.components.v2.component(
        "pawpal_assistant", html='<div class="paw-assistant-root"></div>',
        css=(root / "assistant.css").read_text(encoding="utf-8"),
        js=(root / "assistant_audio.js").read_text(encoding="utf-8") + "\n" +
           (root / "assistant.js").read_text(encoding="utf-8"), isolate_styles=False,
    )


def render_assistant():
    state = st.session_state.setdefault("assistant_state", {"history": [], "turn": 0})
    if not state.get("route"):
        owner_id = st.session_state.get("active_owner_id")
        page = st.session_state.get("page", "Home")
        focus = state.setdefault("context", {})
        if owner_id != focus.get("owner_id"):
            focus.clear()
        focus.update(owner_id=owner_id, page=page)
        if page == "Calendar":
            focus["pet_id"] = st.session_state.get("calendar_pet")
            day = st.session_state.get("calendar_date")
            focus["day"] = day.isoformat() if day else None
    receipts = st.session_state.setdefault("assistant_receipts", [])
    pending = state.get("proposal")
    result = assistant_component()(key="site_assistant", data={
        "configured": is_configured(), "receipts": receipts,
        "page": st.session_state.get("page", "Home"),
        "credential": st.session_state.get("assistant_credential"),
        "proposal": ({"summary": pending["summary"], "conflicts": pending["conflicts"]} if pending else None),
    }, default={"outbox": []}, on_outbox_change=lambda: None, height=0)
    handled = {r["id"] for r in receipts}
    events = (result.outbox or [])[:32]
    cancelled = state.setdefault("cancelled_calls", set())
    terminated = state.setdefault("terminated_sessions", set())
    for item in events:
        if isinstance(item, dict) and item.get("kind") == "voice_end" and item.get("session_id"):
            terminated.add(item["session_id"])
        if isinstance(item, dict) and item.get("kind") == "cancel_tools":
            if item.get("session_id") == state.get("live_session", {}).get("id"):
                cancelled.update(str(i) for i in item.get("call_ids", [])[:32])
    for event in events:
        if not isinstance(event, dict) or event.get("id") in handled:
            continue
        try:
            actions = AssistantActions(PlannerStore().path, state)
        except (OSError, sqlite3.Error):
            receipts.append({"id": event["id"], "message": "Local storage is unavailable. Your chat is retained; try again."})
            st.rerun()
        receipt = {"id": event["id"]}
        kind = event.get("kind")
        if kind == "chat":
            if state.get("live_session", {}).get("active"):
                receipt["message"] = "Stop voice before sending a typed message."
            else:
                st.session_state.pop("assistant_credential", None)
                state.pop("live_session", None)
                text = str(event.get("text", ""))[:2000]
                state["turn"] += 1
                try:
                    answer = respond(text, actions, state["history"], state["turn"])
                except PlannerError as error:
                    answer = str(error)
                state["history"] = (state["history"] + [{"role": "user", "text": text},
                                     {"role": "assistant", "text": answer}])[-20:]
                receipt["message"] = answer
        elif kind == "prepare_voice":
            try:
                credential = prepare_live(actions.context(), state["history"])
                st.session_state.assistant_credential = credential
                state["live_session"] = {"id": credential["session_id"], "base_turn": state["turn"]}
                state["live_calls"] = {}
                state["cancelled_calls"] = set()
                receipt["prepared"] = True
            except PlannerError as error:
                receipt.update(message=str(error), failed=True)
        elif kind == "voice_start":
            session = state.get("live_session", {})
            if event.get("session_id") == session.get("id"):
                session.update(active=True, base_turn=state["turn"])
        elif kind == "cancel_tools":
            calls = state.get("live_calls", {})
            completed = [calls[i] for i in event.get("call_ids", []) if i in calls and calls[i].get("saved")]
            if completed:
                receipt["message"] = "The confirmed task was saved before cancellation reached the app. Check its calendar."
        elif kind == "live_tool":
            session = state.get("live_session", {})
            credential = st.session_state.get("assistant_credential", {})
            call = event.get("call", {})
            calls = state.setdefault("live_calls", {})
            valid = (event.get("session_id") == session.get("id") and credential
                     and time() - credential["issued_at"] < 900)
            if event.get("session_id") in terminated:
                response = {"ok": False, "cancelled": True, "error": "Voice stopped before this action executed."}
            elif not valid or not isinstance(call.get("id"), str):
                response = {"ok": False, "error": "Start a new voice session."}
            elif call["id"] in cancelled:
                response = {"ok": False, "cancelled": True, "error": "Action cancelled before execution."}
            elif call["id"] in calls:
                response = calls[call["id"]]
            else:
                raw_turn = event.get("turn", 0)
                turn = session["base_turn"] + (max(0, raw_turn) if type(raw_turn) is int else 0)
                state["turn"] = max(state["turn"], turn)
                response = actions.execute(call.get("name"), call.get("args", {}),
                                           str(event.get("utterance", ""))[:2000], turn)
                calls[call["id"]] = response
            receipt.update(call={"id":call.get("id"), "name":call.get("name")},
                           result=response, session_id=event.get("session_id"))
        elif kind == "voice_end":
            session = state.get("live_session", {})
            if event.get("session_id") == session.get("id") and type(event.get("turn")) is int:
                state["turn"] = max(state["turn"], session.get("base_turn", 0) + event["turn"])
            history = event.get("history", [])
            history = history if isinstance(history, list) else []
            safe = [{"role":i["role"],"text":i["text"][:2000]} for i in history[-12:]
                    if isinstance(i,dict) and i.get("role") in ("user","assistant") and isinstance(i.get("text"),str)]
            state["history"] = (state["history"] + safe)[-20:]
            st.session_state.pop("assistant_credential", None)
            state.pop("live_session", None)
        else:
            receipt["message"] = "That action is unavailable."
        receipts.append(receipt)
        del receipts[:-100]
        st.rerun()
    return state.pop("route", None)
