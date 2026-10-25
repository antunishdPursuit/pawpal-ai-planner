"""One editable confirmation path for task creation."""
from dataclasses import replace
from datetime import time
import sqlite3
from urllib.parse import urlencode
import streamlit as st

from calendar_view import draft_conflicts
from planner_clock import local_today
from task_contract import TaskDraft
from gemini_planner import GeminiPlanner, PlannerError, is_configured
from voice_ui import render_voice

REPEATS = {"NONE": "Does not repeat", "DAILY": "Daily", "WEEKLY": "Weekly", "CUSTOM": "Custom"}


def map_search_url(location: str) -> str:
    return "https://www.google.com/maps/search/?" + urlencode({"api": "1", "query": location})


def has_draft_content(draft):
    return draft is not None and bool(draft.title.strip() or draft.description.strip()
                                      or draft.location.strip() or draft.time_of_day is not None
                                      or draft.repeat != "NONE"
                                      or draft.pet_id != st.session_state.get("editor_pet_id", draft.pet_id)
                                      or draft.due_date != st.session_state.get("editor_day", draft.due_date))


def open_editor(pet_id, day=None, mode="Manual"):
    st.session_state.editor_open = True
    st.session_state.entry_mode = mode
    st.session_state.editor_day = day
    st.session_state.editor_pet_id = pet_id
    st.session_state.conversation_requested = mode == "Conversation"
    draft = st.session_state.get("task_draft")
    if not has_draft_content(draft):
        st.session_state.pop("task_draft", None)
        if mode == "Manual":
            st.session_state.task_draft = TaskDraft(pet_id, "", day)


def cancel_editor():
    st.session_state.editor_open = False
    st.session_state.pop("task_draft", None)
    st.session_state.pop("conversation", None)
    st.session_state.pop("planner_error", None)
    st.session_state.pop("composer_count", None)
    st.session_state.pop("preview_blocked", None)
    st.session_state.pop("conversation_requested", None)
    st.session_state.pop("editor_day", None)
    st.session_state.pop("editor_pet_id", None)
    st.session_state.pop("pending_request", None)
    st.session_state.pop("voice_credential", None)
    st.session_state.pop("voice_event_id", None)
    st.session_state.pop("voice_error", None)


def keep_draft():
    st.session_state.pop("voice_credential", None)
    count = st.session_state.get("composer_count", 0)
    key = f"request_{count}"
    if key in st.session_state:
        st.session_state.pending_request = st.session_state[key]
    st.session_state.editor_open = False


def start_over():
    day = st.session_state.get("editor_day")
    pet_id = st.session_state.get("editor_pet_id")
    cancel_editor()
    st.session_state.editor_day = day
    st.session_state.editor_pet_id = pet_id
    st.session_state.editor_open = True
    st.session_state.entry_mode = "Manual"


def conversation_input(store, owner, profiles):
    history = st.session_state.get("conversation", [])
    for item in history[-6:]:
        with st.chat_message(item["role"]):
            st.text(item["text"])
    if not is_configured():
        st.info("Gemini is not configured yet. You can still create tasks with Manual.")
    count = st.session_state.get("composer_count", 0)
    request = st.text_area("What would you like to plan?", value=st.session_state.get("pending_request", ""),
                           max_chars=2000, key=f"request_{count}",
                           placeholder="Walk Mochi tomorrow at 8 AM at Central Park")
    draft = st.session_state.get("task_draft")
    replace_allowed = True
    if has_draft_content(draft):
        replace_allowed = st.checkbox("Replace my current draft with a new preview",
                                      key=f"replace_{draft.request_id}")
    render_voice(store, owner, profiles, replace_allowed)
    if st.button("Create task preview", type="primary", disabled=not replace_allowed):
        if not request.strip():
            st.error("Describe the task you would like to plan.")
        else:
            try:
                with st.spinner("Planning your task..."):
                    result = GeminiPlanner().propose(request, owner, history)
            except (PlannerError, ValueError) as error:
                st.session_state.planner_error = str(error)
                st.session_state.preview_blocked = True
            else:
                st.session_state.pop("voice_error", None)
                st.session_state.conversation = (history + [
                    {"role": "user", "text": request},
                    {"role": "assistant", "text": result.message},
                ])[-6:]
                st.session_state.pop("planner_error", None)
                st.session_state.composer_count = count + 1
                st.session_state.pop("pending_request", None)
                st.session_state.preview_blocked = result.draft is None
                st.session_state.conversation_requested = result.draft is None
                if result.draft is not None:
                    st.session_state.task_draft = result.draft
                st.rerun()
    if st.session_state.get("planner_error"):
        st.error(st.session_state.planner_error)


def entry_mode_changed():
    st.session_state.pop("voice_credential", None)
    key = f"request_{st.session_state.get('composer_count', 0)}"
    if key in st.session_state:
        st.session_state.pending_request = st.session_state[key]
    st.session_state.conversation_requested = st.session_state.get("entry_mode") == "Conversation"


def show_editor(store, owner):
    with st.container(key="task_editor"):
        mode = st.radio("Entry method", ["Conversation", "Manual"], horizontal=True,
                        index=None if "entry_mode" in st.session_state else 1,
                        key="entry_mode", on_change=entry_mode_changed)
        if mode == "Conversation":
            with st.expander("Request and response", expanded=st.session_state.get("conversation_requested", False) or st.session_state.get("task_draft") is None or st.session_state.get("preview_blocked", False)):
                conversation_input(store, owner, store.list_profiles())
        elif st.session_state.get("task_draft") is None:
            st.session_state.task_draft = TaskDraft(st.session_state.get("editor_pet_id") or owner.pets[0].pet_id, "",
                                                    st.session_state.get("editor_day") or local_today())
        draft = st.session_state.get("task_draft")
        if draft is None or (mode == "Conversation" and st.session_state.get("preview_blocked")):
            if draft is not None:
                st.info("Your previous draft is preserved. Continue the conversation or choose Manual to review it.")
            if st.button("Keep draft"):
                keep_draft()
                st.rerun()
            return
        if owner.find_pet(draft.pet_id) is None:
            st.error("This draft belongs to another user. Start over.")
            st.button("Start over", on_click=start_over)
            if st.button("Keep draft"):
                keep_draft()
                st.rerun()
            return
        st.subheader("Review your task")
        st.button("Start over", on_click=start_over, help="Discard this draft and conversation")
        prefix = draft.request_id
        pet_ids = [p.pet_id for p in owner.pets]
        title = st.text_input("Task title", value=draft.title, max_chars=120, key=f"{prefix}_title")
        pet_col, date_col = st.columns(2)
        pet_id = pet_col.selectbox("Assign to pet", pet_ids, index=pet_ids.index(draft.pet_id) if draft.pet_id in pet_ids else 0,
                                   format_func=lambda value: f"{owner.get_pet(value).name} (ID {value})", key=f"{prefix}_pet")
        due = date_col.date_input("Date", value=draft.due_date or local_today(), key=f"{prefix}_date")
        repeat_col, time_col = st.columns(2)
        repeat = repeat_col.selectbox("Repeat", list(REPEATS), index=list(REPEATS).index(draft.repeat),
                                     format_func=REPEATS.get, key=f"{prefix}_repeat")
        with time_col:
            anytime = st.checkbox("Anytime", value=draft.time_of_day is None, key=f"{prefix}_anytime")
            at = None if anytime else st.time_input("Time", value=draft.time_of_day or time(9), key=f"{prefix}_time")
        interval = draft.interval_days
        if repeat == "CUSTOM":
            interval = repeat_col.number_input("Interval in days", min_value=1, max_value=365,
                                               value=draft.interval_days, key=f"{prefix}_interval")
        location = st.text_input("Location (optional)", value=draft.location, max_chars=300, key=f"{prefix}_location")
        with st.expander("Description (optional)", expanded=bool(draft.description)):
            description = st.text_area("Description", value=draft.description, max_chars=1000, key=f"{prefix}_description")
        current = replace(draft, pet_id=pet_id, title=title, due_date=due, time_of_day=None if anytime else at,
                          repeat=repeat, interval_days=int(interval), location=location, description=description)
        st.session_state.task_draft = current
        warnings = draft_conflicts(owner, current)
        for warning in warnings:
            st.warning(warning)
        acknowledged = False
        if warnings:
            acknowledged = st.checkbox("Keep this time despite the conflict",
                                       key=f"{prefix}_conflict_{due}_{at}_{pet_id}_{repeat}_{interval}")
        st.caption(f"{due:%A, %B %d, %Y} | {owner.timezone}" if due else "Choose a date.")
        st.caption("Nothing is saved until you confirm.")
        with st.container(key="confirm_actions"):
            left, right = st.columns(2)
            if left.button("Keep draft", use_container_width=True):
                keep_draft()
                st.rerun()
            if right.button("Confirm and save", type="primary", use_container_width=True, disabled=due is None or (not anytime and at is None)):
                try:
                    saved = store.create_task(current, allow_conflicts=acknowledged)
                except (ValueError, sqlite3.Error, OSError) as error:
                    st.error(str(error) if isinstance(error, ValueError) else "Could not save. Your draft is still here; check local storage and try again.")
                else:
                    st.session_state.pending_selected_day = saved.due_date or local_today()
                    cancel_editor()
                    st.session_state.notice = "Task saved."
                    st.rerun()
