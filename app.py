"""PawPal AI Planner: a calendar workspace with human-confirmed task creation."""
from datetime import timedelta
import sqlite3
from zoneinfo import available_timezones

import streamlit as st
from app_theme import apply_theme, favicon
from calendar_view import CalendarEntry, entries_for_day, filter_entries, day_conflicts
from pawpal_system import Scheduler
from planner_clock import local_today, using_timezone
from planner_storage import PlannerStore
from task_editor import show_editor, open_editor, map_search_url
from gemini_planner import is_configured, configuration
from ui_components import summary, task_summary, calendar_chip, empty_panel, brand

st.set_page_config(page_title="PawPal AI Planner", page_icon=favicon(), layout="wide", initial_sidebar_state="auto")
apply_theme()


def navigate(page):
    st.session_state.page = page


def move_date(days):
    st.session_state.selected_day = (st.session_state.get("selected_day") or local_today()) + timedelta(days=days)


def today_date():
    st.session_state.selected_day = local_today()


def dismiss_editor():
    # Dismissal closes the dialog but preserves unsaved content.
    st.session_state.editor_open = False


@st.dialog("Plan a care task", width="medium", on_dismiss=dismiss_editor)
def task_dialog(store, owner):
    with using_timezone(owner.timezone):
        show_editor(store, owner)


def show_pet_dialog():
    st.session_state.pet_dialog_open = True


def dismiss_pet_dialog():
    st.session_state.pet_dialog_open = False


@st.dialog("Add a pet", width="small", on_dismiss=dismiss_pet_dialog)
def pet_dialog(store):
    pet_form(store)


def profile_form(store, owner=None):
    with st.form("profile_form"):
        name = st.text_input("Your name", value=owner.name if owner else "", max_chars=80)
        zones = sorted(available_timezones())
        current = owner.timezone if owner else "America/New_York"
        zone = st.selectbox("Timezone", zones, index=zones.index(current))
        submitted = st.form_submit_button("Save profile", type="primary", use_container_width=True)
    if submitted:
        try:
            store.save_profile(name, zone)
        except (ValueError, sqlite3.Error, OSError) as error:
            st.error(str(error) if isinstance(error, ValueError) else "Could not save your profile. Check local storage permissions and try again.")
        else:
            st.session_state.notice = "Profile saved."
            st.rerun()


def pet_form(store):
    with st.form("pet_form"):
        name = st.text_input("Pet name", max_chars=80)
        species = st.selectbox("Species", ["dog", "cat", "other"])
        age = st.number_input("Age", min_value=0, max_value=30, value=2, step=1)
        submit = st.form_submit_button("Add pet", type="primary", use_container_width=True)
    if submit:
        try:
            pet = store.add_pet(name, species, int(age))
        except (ValueError, sqlite3.Error, OSError) as error:
            st.error(str(error) if isinstance(error, ValueError) else "Could not save this pet. Your entries are still here.")
        else:
            st.session_state.pet_dialog_open = False
            st.session_state.notice = f"{pet.name} added."
            st.rerun()


def sidebar(owner):
    with st.sidebar:
        brand()
        st.radio("Workspace", ["Calendar", "Pets", "Settings"], key="page", label_visibility="collapsed")
        st.divider()
        st.text(owner.name)
        st.caption(f"{len(owner.pets)} registered pet{'s' if len(owner.pets) != 1 else ''}")
        st.caption("Saved on this device")
    return st.session_state.page


def pets_page(store, owner):
    title, action = st.columns([3, 1], vertical_alignment="center")
    title.title("Your pets")
    action.button("Add a pet", on_click=show_pet_dialog, type="primary", use_container_width=True)
    st.caption("Profiles keep each care task connected to the right pet.")
    if not owner.pets:
        empty_panel("Meet your first pet", "Add their name, species and age. Then start a care plan from the calendar.")
    else:
        columns = st.columns(min(3, len(owner.pets)))
        for i, pet in enumerate(owner.pets):
            with columns[i % len(columns)]:
                with st.container(border=True):
                    st.subheader(pet.name)
                    st.caption(f"{pet.species.capitalize()} / Age {pet.age} / ID {pet.pet_id}")
                    st.write(f"{sum(t.status != 'done' for t in pet.tasks)} active care tasks")
                    st.caption(f"{len(pet.tasks)} saved task occurrences")


def task_card(store, owner, entry, prefix):
    task = entry.task
    pet = owner.get_pet(task.assigned_pet_id)
    with st.container(border=True, key=f"care_{prefix}_{task.task_id}"):
        at = task.time_of_day.strftime("%I:%M %p").lstrip("0") if task.time_of_day else "Anytime"
        state = "Planned repeat" if entry.projected else entry.status.capitalize()
        clock, content, action = st.columns([1.1, 5, 1.5], vertical_alignment="center")
        clock.markdown(f'<div class="paw-time">{at}</div>', unsafe_allow_html=True)
        with content:
            task_summary(task, pet, state)
        if not entry.projected and entry.status != "done" and (task.due_date is None or task.due_date <= local_today()):
            if action.button("Mark done", key=f"done_{prefix}_{task.task_id}", use_container_width=True):
                try:
                    _, next_task = store.complete_task(task.task_id)
                except (ValueError, sqlite3.Error, OSError) as error:
                    st.error(str(error) if isinstance(error, ValueError) else "Could not save completion. Try again.")
                else:
                    st.session_state.notice = f"Done. Next occurrence: {next_task.due_date:%B %d}." if next_task else "Task completed."
                    st.rerun()
        with st.expander("Task details"):
            if task.description:
                st.text(task.description)
            if task.due_date:
                st.caption(f"Due {task.due_date:%B %d, %Y}")
            if task.schedule:
                label = task.schedule.schedule_type.value
                if label == "custom":
                    label = f"every {task.schedule.interval} days"
                st.caption(f"Repeats {label}")
            if task.location_text:
                st.text(task.location_text)
                st.link_button("Open in Maps", map_search_url(task.location_text))
            if entry.projected:
                st.caption("Estimated repeat; its date can shift when the preceding task is completed.")


def calendar_page(store, owner):
    heading, actions = st.columns([3, 2], vertical_alignment="center")
    heading.title("Care calendar")
    heading.caption(local_today().strftime("%A, %B %d") + " / " + owner.timezone)
    if owner.pets:
        with actions:
            with st.container(horizontal=True):
                st.button("Plan with PawPal", type="primary", on_click=open_editor,
                          args=(owner.pets[0].pet_id, st.session_state.get("selected_day") or local_today(), "Conversation"))
                st.button("Add task manually", on_click=open_editor,
                          args=(owner.pets[0].pet_id, st.session_state.get("selected_day") or local_today(), "Manual"))
        due = Scheduler.get_daily_tasks(owner, include_completed=True)
        summary(sum(t.status == "pending" for t in due), sum(t.status == "overdue" for t in due),
                sum(t.last_completed_date == local_today() for t in owner.get_all_tasks()))
    else:
        empty_panel("Your care plan starts with a pet", "Add your pet to schedule walks, meals and appointments. Confirm each task before it enters your calendar.")
        st.button("Add your first pet", on_click=show_pet_dialog, type="primary")
    calendar_workspace(store, owner)


def calendar_workspace(store, owner):
    selected = st.session_state.get("selected_day") or local_today()
    with st.container(key="calendar_surface"):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.button("Previous day", on_click=move_date, args=(-1,))
            st.button("Today", on_click=today_date)
            st.button("Next day", on_click=move_date, args=(1,))
            with st.container(key="view_switch", width=230):
                view = st.segmented_control("Calendar view", ["Week", "Agenda"], default="Week", label_visibility="collapsed")
        date_col, pet_col, status_col = st.columns([1.5, 1.3, 1])
        selected = date_col.date_input("Selected day", value=None if "selected_day" in st.session_state else selected, key="selected_day")
        pet_id = pet_col.selectbox("Pet", [None] + [p.pet_id for p in owner.pets],
                                  format_func=lambda v: "All pets" if v is None else f"{owner.get_pet(v).name} (ID {v})")
        status_label = status_col.selectbox("Status", ["All", "Pending", "Overdue", "Done"])
        status = None if status_label == "All" else status_label.lower()
        if selected is None:
            st.info("Choose a date to see the agenda.")
            return
        if view == "Week":
            monday = selected - timedelta(days=selected.weekday())
            st.markdown(f'<h2 class="paw-week-title">{monday:%B %d} &ndash; {monday + timedelta(days=6):%B %d, %Y}</h2>', unsafe_allow_html=True)
            with st.container(key="week_grid"):
                for i, col in enumerate(st.columns(7, gap=None, wrap=False)):
                    day = monday + timedelta(days=i)
                    with col:
                        st.button(day.strftime("%a %d"), key=f"day_{i}", on_click=lambda d=day: st.session_state.update(selected_day=d),
                                  use_container_width=True, type="primary" if day == selected else "secondary")
                        entries = filter_entries(entries_for_day(owner, day), pet_id, status)
                        for entry in entries[:2]:
                            pet = owner.get_pet(entry.task.assigned_pet_id)
                            color = ["", "blue", "rust"][(pet.pet_id - 1) % 3]
                            calendar_chip(entry, pet, color)
                        if not entries:
                            st.markdown('<div class="paw-empty-day">No tasks</div>', unsafe_allow_html=True)
                        if len(entries) > 2:
                            st.caption(f"+{len(entries)-2} more in agenda")
        st.subheader(selected.strftime("%A, %B %d") + " agenda")
        for warning in day_conflicts(owner, selected):
            st.warning(warning)
        if selected == local_today():
            overdue = [t for t in owner.get_all_tasks() if t.status == "overdue"]
            overdue_entries = filter_entries([CalendarEntry(t, t.due_date) for t in Scheduler.sort_by_time(overdue)], pet_id, status)
            if overdue_entries:
                st.caption("Overdue / original due dates retained")
                for entry in overdue_entries:
                    task_card(store, owner, entry, "overdue")
        entries = filter_entries(entries_for_day(owner, selected), pet_id, status)
        for entry in entries:
            task_card(store, owner, entry, "agenda")
        if not entries:
            st.caption("No tasks match this day and these filters.")
        if view == "Week" and owner.pets:
            st.caption("Dashed cards are estimated repeats. Dates can shift after completion.")


def settings_page(store, owner):
    st.title("Settings")
    with st.container(key="settings_surface"):
        st.subheader("Your profile")
        profile_form(store, owner)
        with st.expander("Local saving and Gemini"):
            st.text(str(store.path))
            st.caption("Saved on this computer. No cloud sync or account login.")
            st.write("Gemini configured" if is_configured() else "Gemini not configured")
            st.text("Model: " + configuration()[1])
            st.caption("Set GEMINI_API_KEY in the repository's local .env file. Never share or commit it.")
            st.caption("One request per preview; 30-second timeout; no automatic retries. Manual entry works without Gemini.")


def main():
    try:
        store = PlannerStore()
        owner = store.load()
    except (sqlite3.Error, OSError):
        st.error("Local storage is unavailable. Check folder permissions or PAWPAL_DB_PATH, then reload.")
        return
    if owner is None:
        st.title("PawPal AI Planner")
        intro, setup = st.columns([1, 1.2], gap="large")
        with intro:
            st.image(favicon(), width=64)
            st.header("Plan your pet's care")
            st.write("Keep walks, meals and appointments together. Type what you need, review the details, and save it to your calendar.")
            st.caption("Start with your profile, add your pets, then plan their care.")
        with setup:
            with st.container(key="profile_surface"):
                st.subheader("Create your local profile")
                profile_form(store)
        return
    with using_timezone(owner.timezone):
        if "pending_selected_day" in st.session_state:
            st.session_state.selected_day = st.session_state.pop("pending_selected_day")
        page = sidebar(owner)
        if "notice" in st.session_state:
            st.success(st.session_state.pop("notice"))
        if page == "Pets":
            pets_page(store, owner)
        elif page == "Settings":
            settings_page(store, owner)
        else:
            calendar_page(store, owner)
        if st.session_state.get("pet_dialog_open"):
            pet_dialog(store)
        elif st.session_state.get("editor_open") and owner.pets:
            task_dialog(store, owner)


main()
