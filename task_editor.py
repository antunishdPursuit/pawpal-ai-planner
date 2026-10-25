"""One editable confirmation path for task creation."""
from dataclasses import replace
from datetime import time
import sqlite3
from urllib.parse import urlencode
import streamlit as st

from calendar_view import draft_conflicts
from planner_clock import local_today
from task_contract import TaskDraft

REPEATS = {"NONE": "Does not repeat", "DAILY": "Daily", "WEEKLY": "Weekly", "CUSTOM": "Custom"}


def map_search_url(location: str) -> str:
    return "https://www.google.com/maps/search/?" + urlencode({"api": "1", "query": location})


def open_editor(pet_id, day=None):
    st.session_state.editor_open = True
    if st.session_state.get("task_draft") is None:
        st.session_state.task_draft = TaskDraft(pet_id, "", day or local_today())


def cancel_editor():
    st.session_state.editor_open = False
    st.session_state.pop("task_draft", None)


def show_editor(store, owner):
    draft = st.session_state.task_draft
    with st.container(border=True):
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
