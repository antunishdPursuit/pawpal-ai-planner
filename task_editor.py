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

REPEATS = {"NONE": "Does not repeat", "DAILY": "Daily", "WEEKLY": "Weekly", "CUSTOM": "Custom"}


def map_search_url(location: str) -> str:
    return "https://www.google.com/maps/search/?" + urlencode({"api": "1", "query": location})


def open_editor(pet_id, day=None, mode="Manual"):
    st.session_state.editor_open = True
    st.session_state.entry_mode = mode
    if mode == "Manual" and st.session_state.get("task_draft") is None:
        st.session_state.task_draft = TaskDraft(pet_id, "", day or local_today())


def cancel_editor():
    st.session_state.editor_open = False
    st.session_state.pop("task_draft", None)
    st.session_state.pop("conversation", None)
    st.session_state.pop("planner_error", None)
    st.session_state.pop("composer_count", None)


def conversation_input(owner):
    history = st.session_state.get("conversation", [])
    for item in history[-6:]:
        with st.chat_message(item["role"]):
            st.text(item["text"])
    if not is_configured():
        st.info("Gemini is not configured yet. You can still create tasks with Manual.")
    st.caption("Your request and relevant saved pet/task details are sent to Google Gemini. Plan one task at a time.")
    count = st.session_state.get("composer_count", 0)
    request = st.text_area("What would you like to plan?", max_chars=2000, key=f"request_{count}",
                           placeholder="Walk Mochi tomorrow at 8 AM at Central Park")
    if st.button("Create task preview", type="primary"):
        if not request.strip():
            st.error("Describe the task you would like to plan.")
        else:
            try:
                with st.spinner("Planning your task..."):
                    result = GeminiPlanner().propose(request, owner, history)
            except (PlannerError, ValueError) as error:
                st.session_state.planner_error = str(error)
            else:
                st.session_state.conversation = (history + [
                    {"role": "user", "text": request},
                    {"role": "assistant", "text": result.message},
                ])[-6:]
                st.session_state.pop("planner_error", None)
                st.session_state.composer_count = count + 1
                if result.draft is not None:
                    st.session_state.task_draft = result.draft
                st.rerun()
    if st.session_state.get("planner_error"):
        st.error(st.session_state.planner_error)


def show_editor(store, owner):
    with st.container(border=True):
        st.subheader("Plan a care task")
        mode = st.segmented_control("Entry method", ["Conversation", "Manual"],
                                    default=None if "entry_mode" in st.session_state else "Manual", key="entry_mode")
        if mode == "Conversation":
            with st.expander("Conversation", expanded=st.session_state.get("task_draft") is None):
                conversation_input(owner)
        elif st.session_state.get("task_draft") is None:
            st.session_state.task_draft = TaskDraft(owner.pets[0].pet_id, "", local_today())
        draft = st.session_state.get("task_draft")
        if draft is None:
            st.button("Cancel", on_click=cancel_editor)
            return
        st.subheader("Review your task")
        prefix = draft.request_id
        pet_ids = [p.pet_id for p in owner.pets]
        pet_id = st.selectbox("Assign to pet", pet_ids, index=pet_ids.index(draft.pet_id) if draft.pet_id in pet_ids else 0,
                             format_func=lambda value: owner.get_pet(value).name, key=f"{prefix}_pet")
        title = st.text_input("Task title", value=draft.title, max_chars=120, key=f"{prefix}_title")
        due = st.date_input("Date", value=draft.due_date or local_today(), key=f"{prefix}_date")
        anytime = st.checkbox("Anytime", value=draft.time_of_day is None, key=f"{prefix}_anytime")
        at = st.time_input("Time", value=draft.time_of_day or time(9), disabled=anytime, key=f"{prefix}_time")
        repeat = st.selectbox("Repeat", list(REPEATS), index=list(REPEATS).index(draft.repeat),
                              format_func=REPEATS.get, key=f"{prefix}_repeat")
        interval = 1
        if repeat == "CUSTOM":
            interval = st.number_input("Interval in days", min_value=1, max_value=365,
                                       value=draft.interval_days if draft.repeat == "CUSTOM" else 3, key=f"{prefix}_interval")
        location = st.text_input("Location (optional)", value=draft.location, max_chars=300, key=f"{prefix}_location")
        description = st.text_area("Description (optional)", value=draft.description, max_chars=1000, key=f"{prefix}_description")
        current = replace(draft, pet_id=pet_id, title=title, due_date=due, time_of_day=None if anytime else at,
                          repeat=repeat, interval_days=int(interval), location=location, description=description)
        st.session_state.task_draft = current
        warnings = draft_conflicts(owner, current)
        for warning in warnings:
            st.warning(warning)
        acknowledged = False
        if warnings:
            acknowledged = st.checkbox("Keep this time despite the conflict",
                                       key=f"{prefix}_conflict_{due}_{at}_{pet_id}")
        st.caption(f"{due:%A, %B %d, %Y} | {owner.timezone}" if due else "Choose a date.")
        st.caption("Nothing is saved until you confirm.")
        left, right = st.columns(2)
        left.button("Cancel", on_click=cancel_editor, use_container_width=True)
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
