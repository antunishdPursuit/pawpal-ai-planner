"""Persistent site-wide assistant component and event bridge."""
from pathlib import Path
import html
import json
from time import time
import sqlite3
import base64
from uuid import uuid4
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx
from gemini_planner import is_configured, PlannerError
from planner_storage import PlannerStore
from assistant_actions import AssistantActions
from assistant_model import respond
from assistant_live import prepare_live
from live_confirmation import stage_save, commit_save
from sable_assets import companion_assets


@st.cache_resource
def assistant_component():
    root = Path(__file__).parent / "assets"
    return st.components.v2.component(
        "pawpal_assistant", html='<div class="paw-assistant-root"></div>'
        '<div class="paw-sable-assets" hidden>' + html.escape(json.dumps(companion_assets())) + '</div>'
        '<div class="paw-voice-detector" hidden>' + base64.b64encode(
            (root / "vendor/silero/silero_vad_v5.onnx").read_bytes()).decode() + '</div>'
        '<div class="paw-voice-wasm" hidden>' + base64.b64encode(
            (root / "vendor/onnxruntime/ort-wasm-simd.wasm").read_bytes()).decode() + '</div>',
        css=(root / "assistant.css").read_text(encoding="utf-8"),
        js=(root / "vendor/onnxruntime/ort.wasm.min.js").read_text(encoding="utf-8") + "\n" +
           (root / "assistant_vad.js").read_text(encoding="utf-8") + "\n" +
           (root / "assistant_audio.js").read_text(encoding="utf-8") + "\n" +
           (root / "sable.js").read_text(encoding="utf-8") + "\n" +
           (root / "assistant.js").read_text(encoding="utf-8"), isolate_styles=False,
    )


def suspend_assistant():
    """Invalidate voice work when leaving the planner; keep conversation history."""
    state = st.session_state.get("assistant_state", {})
    state.pop("navigation", None)
    state.pop("arrived_route", None)
    session = state.pop("live_session", {})
    if session.get("id"):
        state.setdefault("terminated_sessions", set()).add(session["id"])
    for key in ("live_calls", "live_verifications", "confirmation_transcripts"):
        state.pop(key, None)
    st.session_state.pop("assistant_credential", None)


def rerun_assistant():
    ctx = get_script_run_ctx()
    st.rerun(scope="fragment" if ctx and ctx.fragment_ids_this_run else "app")


def render_assistant():
    state = st.session_state.setdefault("assistant_state", {"history": [], "turn": 0})
    page = st.session_state.get("page", "Home")
    navigation = state.get("navigation")
    if navigation and navigation["from_page"] != page:
        if navigation.get("arrived") and navigation["route"]["page"] == page:
            navigation["entering"] = True
        else:
            state.pop("navigation", None)
        state.pop("arrived_route", None)
    route = state.get("route")
    if route and route["page"] != page:
        state["navigation"] = {"id": str(uuid4()), "route": dict(state.pop("route")), "from_page": page}
    if not state.get("route") and not state.get("navigation") and not state.get("arrived_route"):
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
        "history": state["history"],
        "navigation": ({"id": state["navigation"]["id"], "page": state["navigation"]["route"]["page"], "arrived": state["navigation"].get("arrived", False), "entering": state["navigation"].get("entering", False)}
                       if state.get("navigation") else None),
        "credential": st.session_state.get("assistant_credential"),
        "proposal": ({"id": pending["id"], "summary": pending["summary"], "conflicts": pending["conflicts"]} if pending else None),
    }, default={"outbox": []}, on_outbox_change=lambda: None, height=0)
    handled_order = state.setdefault("handled_events", [])
    handled = set(handled_order) | {r["id"] for r in receipts}
    queued = [e for e in (result.outbox or []) if isinstance(e, dict) and e.get("id") not in handled]
    events = queued[:32]
    cancelled = state.setdefault("cancelled_calls", set())
    terminated = state.setdefault("terminated_sessions", set())
    processed = False
    for item in queued:
        if item.get("kind") == "chat" or (item.get("kind") == "voice_turn" and not item.get("closed")):
            state.pop("navigation", None)
            state.pop("arrived_route", None)
        session = state.get("live_session", {})
        if (isinstance(item, dict) and item.get("kind") == "voice_turn"
                and item.get("session_id") == session.get("id") and type(item.get("turn")) is int
                and item["turn"] >= session.get("audio_turn", 0)):
            session.update(audio_turn=item["turn"], audio_closed=item.get("closed") is True)
            state["turn"] = max(state["turn"], session.get("base_turn", 0) + item["turn"])
        if isinstance(item, dict) and item.get("kind") == "voice_end" and item.get("session_id"):
            terminated.add(item["session_id"])
        if isinstance(item, dict) and item.get("kind") == "cancel_tools":
            if item.get("session_id") == state.get("live_session", {}).get("id"):
                cancelled.update(str(i) for i in item.get("call_ids", [])[:32])
    for event in events:
        if not isinstance(event, dict) or event.get("id") in handled:
            continue
        processed = True
        receipt = {"id": event["id"]}
        kind = event.get("kind")
        if kind in ("chat", "prepare_voice", "live_tool", "live_commit"):
            try:
                actions = AssistantActions(PlannerStore().path, state)
            except (OSError, sqlite3.Error):
                message = "Local storage is unavailable. Your chat is retained; try again."
                receipt.update(message=message, failed=True)
                if kind in ("live_tool", "live_commit"):
                    receipt.update(call=event.get("call", {}), session_id=event.get("session_id"),
                                   result={"ok": False, "error": message})
                receipts.append(receipt)
                rerun_assistant()
        if kind == "navigation_done":
            navigation = state.get("navigation")
            if (navigation and not navigation.get("arrived") and event.get("navigation_id") == navigation["id"]
                    and navigation["from_page"] == st.session_state.get("page", "Home")):
                state["arrived_route"] = navigation["route"]
                navigation["arrived"] = True
        elif kind == "navigation_entered":
            navigation = state.get("navigation")
            if (navigation and navigation.get("entering") and event.get("navigation_id") == navigation["id"]
                    and navigation["route"]["page"] == st.session_state.get("page", "Home")):
                state.pop("navigation", None)
        elif kind == "chat":
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
                state["live_verifications"] = {}
                state["confirmation_transcripts"] = {}
                receipt["prepared"] = True
            except PlannerError as error:
                receipt.update(message=str(error), failed=True)
            except (OSError, sqlite3.Error):
                receipt.update(message="Voice preparation failed. Try again, or keep typing.", failed=True)
        elif kind == "voice_start":
            session = state.get("live_session", {})
            if event.get("session_id") == session.get("id"):
                session.update(active=True)
        elif kind == "voice_turn":
            pass  # The latest audio boundary is applied before any queued action.
        elif kind == "cancel_tools":
            calls = state.get("live_calls", {})
            completed = [calls[i] for i in event.get("call_ids", []) if i in calls and calls[i].get("saved")]
            if completed:
                receipt["message"] = "The confirmed task was saved before cancellation reached the app. Check its calendar."
        elif kind in ("live_tool", "live_commit"):
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
                if call.get("name") == "save_task" and kind == "live_tool":
                    try:
                        staged = stage_save(event, actions, session)
                    except (OSError, sqlite3.Error):
                        staged = {"result": {"ok": False, "error": "Local storage is unavailable. Nothing was saved."}}
                    if staged.get("verification_id"):
                        receipt.update(call={"id":call["id"], "name":call["name"]},
                                       verification_id=staged["verification_id"], session_id=event.get("session_id"))
                        receipts.append(receipt)
                        del receipts[:-100]
                        rerun_assistant()
                    response = staged["result"]
                elif kind == "live_commit" and call.get("name") == "save_task":
                    response = commit_save(event, actions, session)
                elif kind == "live_commit":
                    response = {"ok": False, "error": "Unsupported confirmation action."}
                else:
                    response = actions.execute(call.get("name"), call.get("args", {}),
                                               str(event.get("utterance", ""))[:2000], turn)
                calls[call["id"]] = response
            if response.get("saved"):
                st.session_state["assistant_refresh"] = True
            receipt.update(call={"id":call.get("id"), "name":call.get("name")},
                           result=response, session_id=event.get("session_id"))
        elif kind == "voice_end":
            session = state.get("live_session", {})
            if session.get("id") and event.get("session_id") == session.get("id"):
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
        handled.add(event["id"])
        handled_order.append(event["id"])
        del handled_order[:-1024]
    if processed:
        rerun_assistant()
    return state.get("arrived_route") or state.get("route")
