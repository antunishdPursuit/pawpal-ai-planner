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
from task_editor import show_editor, open_editor, cancel_editor, has_draft_content, map_search_url
from gemini_planner import is_configured, configuration
from ui_components import task_summary, calendar_chip, brand

st.set_page_config(page_title="PawPal AI Planner", page_icon=favicon(), layout="wide", initial_sidebar_state="expanded")
apply_theme()


def navigate(page):
    st.session_state.page = page


def select_date(day):
    st.session_state.calendar_date = day
    st.session_state.selected_day = day


def remember_date():
    st.session_state.calendar_date = st.session_state.selected_day


@st.dialog("Plan a care task", width="medium", dismissible=False)
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


def activate_profile(owner_id):
    # Unsaved inputs belong to one user; never carry a draft into another profile.
    draft = st.session_state.get("task_draft")
    draft_prefix = draft.request_id + "_" if draft else None
    cancel_editor()
    for key in list(st.session_state):
        if key.startswith("replace_") or key.startswith("request_") or (draft_prefix and key.startswith(draft_prefix)):
            st.session_state.pop(key, None)
    for key in ("calendar_date", "selected_day", "pending_selected_day", "calendar_pet",
                "calendar_status", "calendar_view", "pet_name", "pet_species", "pet_age", "notice"):
        st.session_state.pop(key, None)
    st.session_state.pet_dialog_open = False
    st.session_state.active_owner_id = owner_id
    st.session_state.page = "Pets"


def profile_form(store):
    with st.form("new_user_form"):
        name = st.text_input("Name", max_chars=80)
        zones = sorted(available_timezones())
        zone = st.selectbox("Timezone", zones, index=zones.index("America/New_York"))
        submitted = st.form_submit_button("Create user", type="primary", use_container_width=True)
    if submitted:
        try:
            owner = store.create_profile(name, zone)
        except (ValueError, sqlite3.Error, OSError) as error:
            st.error(str(error) if isinstance(error, ValueError) else "Could not create this user. Try again.")
        else:
            activate_profile(owner.owner_id)
            st.rerun()


def user_page(store, owner, profiles):
    st.title("User")
    st.caption("Choose who is planning. Each local user has their own pets and calendar.")
    with st.container(key="profile_surface"):
        if owner:
            st.caption("CURRENT USER")
            st.subheader(owner.name)
            with st.expander("Timezone: " + owner.timezone):
                with st.form("timezone_form"):
                    zones = sorted(available_timezones())
                    zone = st.selectbox("Your timezone", zones, index=zones.index(owner.timezone))
                    save_zone = st.form_submit_button("Save timezone")
                if save_zone:
                    try:
                        PlannerStore(store.path, owner.owner_id).save_profile(owner.name, zone)
                    except (ValueError, sqlite3.Error, OSError):
                        st.error("Could not save the timezone. Try again.")
                    else:
                        st.success("Timezone saved. Task times remain local wall times.")
        if profiles:
            others = [p for p in profiles if owner is None or p.owner_id != owner.owner_id]
            if others:
                st.subheader("Change user" if owner else "Choose a user")
                selected = st.selectbox("Saved users", [p.owner_id for p in others],
                                       format_func=lambda value: next(p.name for p in others if p.owner_id == value),
                                       key="user_choice")
                if has_draft_content(st.session_state.get("task_draft")) or st.session_state.get("conversation"):
                    st.warning("Changing users discards the current unsaved task draft and conversation.")
                if st.button("Use this user", type="primary"):
                    activate_profile(selected)
                    st.rerun()
        with st.expander("Add a new local user", expanded=not profiles):
            st.caption("A name and timezone are all you need. No password or sign-in.")
            if has_draft_content(st.session_state.get("task_draft")) or st.session_state.get("conversation"):
                st.warning("Creating a user discards the current unsaved task draft and conversation.")
            profile_form(store)
    with st.expander("Local saving and Gemini"):
        st.caption("Data is saved on this computer, without cloud sync. Local users are not password-protected.")
        st.text(str(store.path))
        st.write("Gemini configured" if is_configured() else "Gemini not configured")
        st.text("Model: " + configuration()[1])
        st.caption("Manual task entry works without Gemini. Requests and relevant pet/task details go to Gemini only when you create a preview.")


def pet_form(store):
    with st.form("pet_form"):
        name = st.text_input("Pet name", max_chars=80, key="pet_name")
        species = st.selectbox("Species", ["dog", "cat", "other"], key="pet_species")
        age = st.number_input("Age", min_value=0, max_value=30, value=2, step=1, key="pet_age")
        submit = st.form_submit_button("Add pet", type="primary", use_container_width=True)
    if submit:
        try:
            pet = store.add_pet(name, species, int(age))
        except (ValueError, sqlite3.Error, OSError) as error:
            st.error(str(error) if isinstance(error, ValueError) else "Could not save this pet. Your entries are still here.")
        else:
            st.session_state.pet_dialog_open = False
            st.session_state.notice = f"{pet.name} added. Plan their first care task."
            st.session_state.page = "Calendar"
            st.rerun()


def sidebar(owner):
    with st.sidebar:
        brand()
        with st.container(key="current_user"):
            if owner:
                st.caption("CURRENT USER")
                st.button(owner.name, icon=":material/account_circle:", on_click=navigate,
                          args=("User",), use_container_width=True, help="Change user")
            else:
                st.caption("Choose a user to begin")
        with st.container(key="workspace_nav"):
            for page, icon in (("User", ":material/person:"), ("Pets", ":material/pets:"),
                               ("Calendar", ":material/calendar_month:")):
                enabled = page == "User" or (owner is not None and (page == "Pets" or bool(owner.pets)))
                st.button(page, icon=icon, on_click=navigate, args=(page,), key=f"nav_{page}",
                          disabled=not enabled, use_container_width=True,
                          help=("Choose a user first" if owner is None else "Add a pet first") if not enabled else None,
                          type="primary" if st.session_state.page == page else "secondary")
        st.divider()
        st.caption("Saved on this device")
        if owner is None:
            st.caption("Choose a user, then add a pet to start planning.")
        elif not owner.pets:
            st.caption("Add your first pet to open the calendar.")
    return st.session_state.page


def pets_page(store, owner):
    title, action = st.columns([3, 1], vertical_alignment="center")
    title.title("Your pets")
    st.caption("Add a pet here. Plan their care in the calendar.")
    if not owner.pets:
        with st.container(key="pets_surface"):
            st.subheader("Meet your first pet")
            st.write("Start with their name, species and age.")
            pet_form(store)
    else:
        action.button("Add a pet", on_click=show_pet_dialog, type="primary", use_container_width=True)
        columns = st.columns(min(3, len(owner.pets)))
        for i, pet in enumerate(owner.pets):
            with columns[i % len(columns)]:
                with st.container(border=True):
                    st.subheader(pet.name)
                    st.caption(f"{pet.species.capitalize()} / Age {pet.age}")


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
    chosen_pet = st.session_state.get("calendar_pet") or owner.pets[0].pet_id
    with actions:
        with st.container(horizontal=True):
            st.button("Plan with PawPal", type="primary", on_click=open_editor,
                      args=(chosen_pet, st.session_state.get("calendar_date") or local_today(), "Conversation"))
            st.button("Add task manually", on_click=open_editor,
                      args=(chosen_pet, st.session_state.get("calendar_date") or local_today(), "Manual"))
    calendar_workspace(store, owner)


def calendar_workspace(store, owner):
    selected = st.session_state.get("calendar_date") or local_today()
    if "selected_day" not in st.session_state:
        st.session_state.selected_day = selected
    with st.container(key="calendar_surface"):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.button("Previous day", on_click=select_date, args=(selected - timedelta(days=1),))
            st.button("Today", on_click=select_date, args=(local_today(),))
            st.button("Next day", on_click=select_date, args=(selected + timedelta(days=1),))
            with st.container(key="view_switch", width=230):
                view = st.radio("Calendar view", ["Week", "Agenda"], index=0, horizontal=True, label_visibility="collapsed", key="calendar_view")
        date_col, pet_col, status_col = st.columns([1.5, 1.3, 1])
        selected = date_col.date_input("Selected day", value=None if "selected_day" in st.session_state else selected, key="selected_day", on_change=remember_date)
        pet_id = pet_col.selectbox("Pet", [None] + [p.pet_id for p in owner.pets],
                                  format_func=lambda v: "All pets" if v is None else (
                                      owner.get_pet(v).name + (f" (ID {v})" if sum(p.name == owner.get_pet(v).name for p in owner.pets) > 1 else "")),
                                  key="calendar_pet")
        status_label = status_col.selectbox("Status", ["All", "Pending", "Overdue", "Done"], key="calendar_status")
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
                        st.button(day.strftime("%a %d") + (" *" if day == selected else ""), key=f"day_{i}", on_click=select_date, args=(day,),
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
        if selected == local_today() and owner.get_all_tasks():
            with st.expander("Today's care summary"):
                due = [t for t in Scheduler.get_daily_tasks(owner, include_completed=True)
                       if pet_id is None or t.assigned_pet_id == pet_id]
                pending = sum(t.status == "pending" for t in due)
                overdue = sum(t.status == "overdue" for t in due)
                done = sum(t.last_completed_date == local_today() for t in owner.get_all_tasks()
                           if pet_id is None or t.assigned_pet_id == pet_id)
                counts = [f"{count} {label}" for count, label in ((pending,"pending"),(overdue,"overdue"),(done,"done")) if count]
                st.write(" / ".join(counts) if counts else "No tasks due today.")
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


def main():
    try:
        root_store = PlannerStore()
        profiles = root_store.list_profiles()
        selected = st.session_state.get("active_owner_id")
        store = PlannerStore(root_store.path, owner_id=selected)
        owner = store.load() if selected is not None else None
        if owner is None:
            if selected is not None:
                activate_profile(None)
            st.session_state.active_owner_id = None
            st.session_state.page = "User"
        elif st.session_state.get("page") not in ("User", "Pets", "Calendar"):
            st.session_state.page = "Pets"
        elif st.session_state.page == "Calendar" and not owner.pets:
            st.session_state.page = "Pets"
    except (sqlite3.Error, OSError):
        st.error("Local storage is unavailable. Check folder permissions or PAWPAL_DB_PATH, then reload.")
        return
    page = sidebar(owner)
    if "notice" in st.session_state:
        st.success(st.session_state.pop("notice"))
    if page == "User":
        user_page(root_store, owner, profiles)
        return
    with using_timezone(owner.timezone):
        if "pending_selected_day" in st.session_state:
            select_date(st.session_state.pop("pending_selected_day"))
        if page == "Pets":
            pets_page(store, owner)
        else:
            calendar_page(store, owner)
        if st.session_state.get("pet_dialog_open") and page == "Pets":
            pet_dialog(store)
        elif st.session_state.get("editor_open") and owner.pets and page == "Calendar":
            task_dialog(store, owner)


main()
