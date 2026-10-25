"""PawPal AI Planner's local Streamlit interface."""
from datetime import date, timedelta
import sqlite3
from zoneinfo import available_timezones

import streamlit as st
from app_theme import apply_theme, favicon
from calendar_view import entries_for_day, filter_entries, day_conflicts
from pawpal_system import Scheduler
from planner_clock import local_today, using_timezone
from planner_storage import PlannerStore
from task_editor import show_editor, open_editor, map_search_url
from gemini_planner import is_configured, configuration

st.set_page_config(page_title="PawPal AI Planner", page_icon=favicon(), layout="wide")
apply_theme()


def navigate(page):
    st.session_state.page = page


def move_date(days):
    st.session_state.selected_day = (st.session_state.get("selected_day") or local_today()) + timedelta(days=days)


def today_date():
    st.session_state.selected_day = local_today()


def profile_form(store, owner=None):
    with st.form("profile_form"):
        name = st.text_input("Your name", value=owner.name if owner else "", max_chars=80)
        zones = sorted(available_timezones())
        current = owner.timezone if owner else "America/New_York"
        zone = st.selectbox("Timezone", zones, index=zones.index(current))
        submitted = st.form_submit_button("Save profile", type="primary")
    if submitted:
        try:
            store.save_profile(name, zone)
        except (ValueError, sqlite3.Error, OSError) as error:
            st.error(str(error) if isinstance(error, ValueError) else "Could not save your profile. Check local storage permissions and try again.")
        else:
            st.session_state.notice = "Profile saved."
            st.rerun()


def pets_page(store, owner):
    st.header("Your pets")
    if not owner.pets:
        st.info("Add your first pet to start planning care.")
    for pet in owner.pets:
        with st.container(border=True):
            st.text(pet.name)
            st.caption(f"{pet.species} \u00b7 Age {pet.age} \u00b7 ID {pet.pet_id}")
            st.caption(f"{len(pet.tasks)} saved task occurrences")
    with st.expander("Add a pet", expanded=not owner.pets):
        with st.form("pet_form", clear_on_submit=True):
            name = st.text_input("Pet name", max_chars=80)
            species = st.selectbox("Species", ["dog", "cat", "other"])
            age = st.number_input("Age", min_value=0, max_value=30, value=2, step=1)
            submit = st.form_submit_button("Add pet", type="primary")
        if submit:
            try:
                pet = store.add_pet(name, species, int(age))
            except (ValueError, sqlite3.Error, OSError) as error:
                st.error(str(error) if isinstance(error, ValueError) else "Could not save this pet. Please try again.")
            else:
                st.session_state.notice = f"{pet.name} added."
                st.rerun()


def task_card(store, owner, entry, prefix):
    task = entry.task
    pet = owner.get_pet(task.assigned_pet_id)
    with st.container(border=True):
        st.text(task.title)
        at = task.time_of_day.strftime("%I:%M %p").lstrip("0") if task.time_of_day else "Anytime"
        state = "Planned repeat" if entry.projected else entry.status.capitalize()
        st.caption(f"{pet.name} \u00b7 {at} \u00b7 {state}")
        if task.location_text:
            st.text(task.location_text)
            st.link_button("Open in Maps", map_search_url(task.location_text))
        if task.description:
            st.text(task.description)
        if task.due_date:
            st.caption(f"Due {task.due_date:%B %d, %Y}")
        if task.schedule:
            label = task.schedule.schedule_type.value
            if label == "custom":
                label = f"every {task.schedule.interval} days"
            st.caption(f"Repeats {label}")
        if entry.projected:
            st.caption("Estimate; its date can shift when the preceding task is completed.")
        elif entry.status != "done" and (task.due_date is None or task.due_date <= local_today()):
            if st.button("Mark done", key=f"done_{prefix}_{task.task_id}"):
                try:
                    _, next_task = store.complete_task(task.task_id)
                except (ValueError, sqlite3.Error, OSError) as error:
                    st.error(str(error) if isinstance(error, ValueError) else "Could not save completion. Try again.")
                else:
                    st.session_state.notice = f"Done. Next occurrence: {next_task.due_date:%B %d}." if next_task else "Task completed."
                    st.rerun()


def calendar_page(store, owner):
    st.header("Your calendar")
    if not owner.pets:
        st.info("Add a pet before creating care tasks.")
        st.button("Add your first pet", on_click=navigate, args=("Pets",), type="primary")
        return
    actions = st.columns([1, 1, 3])
    actions[0].button("Plan with PawPal", type="primary", on_click=open_editor,
                      args=(owner.pets[0].pet_id, st.session_state.get("selected_day") or local_today(), "Conversation"))
    actions[1].button("Add task manually", on_click=open_editor,
                      args=(owner.pets[0].pet_id, st.session_state.get("selected_day") or local_today(), "Manual"))
    if st.session_state.get("editor_open"):
        calendar_col, editor_col = st.columns([7, 3], gap="large")
        with calendar_col:
            calendar_workspace(store, owner)
        with editor_col:
            show_editor(store, owner)
    else:
        calendar_workspace(store, owner)


def calendar_workspace(store, owner):
    selected = st.session_state.get("selected_day", local_today())
    view = st.segmented_control("Calendar view", ["Week", "Agenda"], default="Week")
    step = 7 if view == "Week" else 1
    controls = st.columns([1, 1, 1, 4])
    controls[0].button("Today", on_click=today_date, use_container_width=True)
    controls[1].button("Previous", on_click=move_date, args=(-step,), use_container_width=True)
    controls[2].button("Next", on_click=move_date, args=(step,), use_container_width=True)
    selected = controls[3].date_input("Selected day", value=None if "selected_day" in st.session_state else selected, key="selected_day")
    if selected is None:
        st.info("Choose a date to see the agenda.")
        return
    filters = st.columns(2)
    pet_id = filters[0].selectbox("Pet", [None] + [p.pet_id for p in owner.pets],
                                format_func=lambda value: "All pets" if value is None else f"{owner.get_pet(value).name} (ID {value})")
    status_label = filters[1].selectbox("Status", ["All", "Pending", "Overdue", "Done"])
    status = None if status_label == "All" else status_label.lower()
    due_today = Scheduler.get_daily_tasks(owner, include_completed=True)
    metrics = st.columns(3)
    metrics[0].metric("Pending", sum(t.status == "pending" for t in due_today))
    metrics[1].metric("Overdue", sum(t.status == "overdue" for t in due_today))
    metrics[2].metric("Done today", sum(t.last_completed_date == local_today() for t in owner.get_all_tasks()))
    if view == "Week":
        monday = selected - timedelta(days=selected.weekday())
        st.subheader(f"{monday:%B %d} \u2013 {monday + timedelta(days=6):%B %d, %Y}")
        with st.container(key="week_grid"):
            for i, col in enumerate(st.columns(7)):
                day = monday + timedelta(days=i)
                with col:
                    st.button(day.strftime("%a %d"), key=f"day_{i}", on_click=lambda d=day: st.session_state.update(selected_day=d),
                              use_container_width=True, type="primary" if day == selected else "secondary")
                    entries = filter_entries(entries_for_day(owner, day), pet_id, status)
                    st.caption(f"{len(entries)} task{'s' if len(entries) != 1 else ''}")
                    for entry in entries[:3]:
                        st.text(entry.task.title)
                    if len(entries) > 3:
                        st.caption(f"+{len(entries)-3} more")
        st.caption("Planned repeats are estimates. Viewing dates does not save or advance tasks.")
    st.subheader(selected.strftime("%A, %B %d"))
    warnings = day_conflicts(owner, selected)
    for warning in warnings:
        st.warning(warning)
    entries = filter_entries(entries_for_day(owner, selected), pet_id, status)
    if selected == local_today():
        overdue = [t for t in owner.get_all_tasks() if t.status == "overdue"]
        from calendar_view import CalendarEntry
        overdue_entries = filter_entries([CalendarEntry(t, t.due_date) for t in Scheduler.sort_by_time(overdue)], pet_id, status)
        if overdue_entries:
            st.subheader("Overdue")
            for entry in overdue_entries:
                task_card(store, owner, entry, "overdue")
    if not entries:
        st.info("No tasks match this day and these filters.")
    for entry in entries:
        task_card(store, owner, entry, "agenda")


def main():
    st.title("PawPal AI Planner")
    try:
        store = PlannerStore()
        owner = store.load()
    except (sqlite3.Error, OSError):
        st.error("Local storage is unavailable. Check folder permissions or PAWPAL_DB_PATH, then reload.")
        return
    if owner is None:
        st.header("Create your local profile")
        st.write("Save your name and timezone, then add a pet to plan their care.")
        profile_form(store)
        return
    with using_timezone(owner.timezone):
        if "pending_selected_day" in st.session_state:
            st.session_state.selected_day = st.session_state.pop("pending_selected_day")
        if "notice" in st.session_state:
            st.success(st.session_state.pop("notice"))
        page = st.segmented_control("Navigation", ["Calendar", "Pets", "Settings"], default=None if "page" in st.session_state else "Calendar", key="page", label_visibility="collapsed")
        if page == "Pets":
            pets_page(store, owner)
        elif page == "Settings":
            st.header("Settings")
            profile_form(store, owner)
            st.subheader("Local saving")
            st.text(str(store.path))
            st.caption("Saved on this computer. No cloud sync or account login.")
            st.subheader("Gemini")
            st.write("Configured" if is_configured() else "Not configured")
            st.text("Model: " + configuration()[1])
            st.caption("Set GEMINI_API_KEY in the repository's local .env file. The key is never saved in the task database.")
            st.caption("One request per Create task preview. A 30-second timeout and no automatic retries bound requests. Manual entry works without Gemini.")
        else:
            calendar_page(store, owner)


main()
