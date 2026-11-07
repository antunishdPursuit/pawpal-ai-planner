"""PawPal AI Planner: a calendar workspace with human-confirmed task creation."""
from copy import copy
from datetime import timedelta
import sqlite3
from zoneinfo import available_timezones

import streamlit as st
from app_theme import apply_theme, favicon
from calendar_view import CalendarEntry, entries_for_day, filter_entries, community_entries, community_overdue
from pawpal_system import Scheduler
from planner_clock import local_today, using_timezone
from planner_storage import PlannerStore
from task_editor import show_editor, open_editor, close_editor, cancel_editor, has_unsaved_draft, map_search_url, snapshot_current_draft, remember_active_draft
from gemini_planner import is_configured, configuration
from ui_components import task_summary, calendar_item, brand, planner_header, pet_identity, task_state
from calendar_presentation import render_timeline
from homepage import show_home
from assistant_ui import render_assistant, suspend_assistant

st.set_page_config(page_title="PawPal AI Planner", page_icon=favicon(), layout="wide", initial_sidebar_state="auto")
apply_theme()


def navigate(page):
    st.session_state.page = page


def pet_calendar(pet_id):
    st.session_state.calendar_owner = st.session_state.active_owner_id
    st.session_state.calendar_pet = pet_id
    navigate("Calendar")


def select_date(day):
    st.session_state.calendar_date = day
    st.session_state.selected_day = day
    st.session_state.calendar_day_picker = day


def remember_date(widget_key):
    select_date(st.session_state[widget_key])


@st.dialog("Plan a care task", width="medium", dismissible=True, on_dismiss=close_editor)
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
                "calendar_status", "calendar_owner", "calendar_view", "pet_name", "pet_species", "pet_age", "notice"):
        st.session_state.pop(key, None)
    st.session_state.pet_dialog_open = False
    st.session_state.active_owner_id = owner_id
    st.session_state.page = "Pets"


def profile_form(store):
    with st.form("new_user_form"):
        name = st.text_input("Name", max_chars=80)
        zones = sorted(available_timezones())
        zone = st.selectbox("Timezone", zones, index=zones.index("America/New_York"))
        submitted = st.form_submit_button("Create pet owner", type="primary", use_container_width=True)
    if submitted:
        try:
            owner = store.create_profile(name, zone)
        except (ValueError, sqlite3.Error, OSError) as error:
            st.error(str(error) if isinstance(error, ValueError) else "Could not create this pet owner. Try again.")
        else:
            activate_profile(owner.owner_id)
            st.rerun()


def user_page(store, owner, profiles):
    with st.container(key="profile_surface"):
        if owner:
            st.caption("CURRENT PET OWNER")
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
                        st.session_state.notice = "Timezone saved. Task times remain local wall times."
                        st.rerun()
        if (has_unsaved_draft()
                or st.session_state.get("conversation") or st.session_state.get("pending_request")):
            st.warning("Selecting or creating another pet owner discards your unsaved draft and conversation.")
        if profiles:
            others = [p for p in profiles if owner is None or p.owner_id != owner.owner_id]
            if others:
                choice, use = st.columns([1.6, 1], vertical_alignment="bottom")
                selected = choice.selectbox("Saved pet owners", [p.owner_id for p in others],
                                       format_func=lambda value: next(p.name for p in others if p.owner_id == value),
                                       key="user_choice")
                if use.button("Use this pet owner", type="primary", use_container_width=True):
                    activate_profile(selected)
                    st.rerun()
        with st.expander("Add a new local pet owner", expanded=not profiles):
            profile_form(store)
    with st.container(key="profile_details"):
        with st.expander("Local saving and Gemini"):
            st.caption("Data is saved on this computer, without cloud sync. Local pet owners are not password-protected.")
            st.text(str(store.path))
            st.write("Gemini configured" if is_configured() else "Gemini not configured")
            st.text("Model: " + configuration()[1])


def pet_form(store):
    with st.form("pet_form", border=False):
        name = st.text_input("Pet name", max_chars=80, key="pet_name")
        species = st.selectbox("Species", ["dog", "cat", "other"], key="pet_species")
        age = st.number_input("Age (years)", min_value=0, max_value=30, value=2, step=1, key="pet_age")
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


def open_planner():
    navigate("Pets" if st.session_state.get("active_owner_id") is not None else "User")


def sidebar(owner, profiles):
    with st.sidebar:
        brand(lambda: navigate("Home"))
        with st.container(key="current_user"):
            if owner:
                st.caption("CURRENT PET OWNER")
                st.button(owner.name, icon=":material/account_circle:", on_click=navigate,
                          args=("User",), use_container_width=True, help="Change pet owner")
            else:
                st.button("Choose pet owner" if profiles else "Add pet owner", on_click=navigate,
                          args=("User",), use_container_width=True)
        with st.container(key="workspace_nav"):
            for page, icon in (("Pets", ":material/pets:"), ("Calendar", ":material/calendar_month:")):
                enabled = page == "User" or (owner is not None and (page == "Pets" or bool(owner.pets)))
                st.button(page, icon=icon, on_click=navigate, args=(page,), key=f"nav_{page}",
                          disabled=not enabled, use_container_width=True,
                          help=("Choose a pet owner first" if owner is None else "Add a pet first") if not enabled else None,
                          type="primary" if st.session_state.page == page else "secondary")
    return st.session_state.page


def pets_page(store, owner):
    if not owner.pets:
        with st.container(key="pets_surface"):
            st.subheader("Meet your first pet")
            st.write("Start with their name, species and age.")
            pet_form(store)
    else:
        with st.container(horizontal=True, key="pets_workspace"):
            with st.container(horizontal=True, key="pet_cards"):
                for pet in owner.pets:
                    with st.container(width=340, key=f"pet_card_{pet.pet_id}"):
                        pet_identity(pet)
                        st.button(f"View {pet.name}'s calendar", key=f"pet_calendar_{pet.pet_id}", use_container_width=True,
                                  on_click=pet_calendar, args=(pet.pet_id,))
            with st.container(width="content", key="pets_heading"):
                st.button("Add a pet", key="add_pet", on_click=show_pet_dialog, type="primary")


def task_card(store, owner, entry, prefix, viewer_id=None):
    task = entry.task
    pet = owner.get_pet(task.assigned_pet_id)
    with st.container(border=True, key=f"care_{prefix}_{task.task_id}"):
        at_value = entry.display_time or task.time_of_day
        at = at_value.strftime("%I:%M %p").lstrip("0") if at_value else "Anytime"
        state = "Planned repeat" if entry.projected else entry.status.capitalize()
        clock, content, status, action = st.columns([1.1, 3.5, 1.2, 1.8], vertical_alignment="top")
        clock.markdown(f'<div class="paw-time">{at}</div>', unsafe_allow_html=True)
        with content:
            task_summary(task, pet, entry.owner_name)
        with status:
            task_state(state)
        if entry.owner_id == viewer_id and not entry.projected and entry.status != "done" and (task.due_date is None or task.due_date <= local_today()):
            if action.button("Mark done", key=f"done_{prefix}_{task.task_id}", use_container_width=True):
                try:
                    _, next_task = store.complete_task(task.task_id)
                except (ValueError, sqlite3.Error, OSError) as error:
                    st.error(str(error) if isinstance(error, ValueError) else "Could not save completion. Try again.")
                else:
                    st.session_state.notice = f"Done. Next occurrence: {next_task.due_date:%B %d}." if next_task else "Task completed."
                    st.rerun()
        with action.expander("Task details"):
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


def calendar_page(store, owner, owners):
    calendar_workspace(store, owner, owners)


def calendar_workspace(store, owner, owners):
    owners = [owner]
    view_owner = copy(owner)
    view_owner.pets = [pet for profile in owners for pet in profile.pets]
    selected = st.session_state.get("calendar_date") or local_today()
    if "selected_day" not in st.session_state:
        st.session_state.selected_day = selected
    chosen_pet = st.session_state.get("calendar_pet")
    if chosen_pet is None or owner.find_pet(chosen_pet) is None:
        chosen_pet = owner.pets[0].pet_id if owner.pets else None
    with st.container(key="calendar_surface"):
        with st.container(horizontal=True, vertical_alignment="center", key="calendar_toolbar"):
            with st.container(horizontal=True, wrap=False, vertical_alignment="center", width="content", key="date_navigation"):
                weekly = st.session_state.get("calendar_view", "Week") == "Week"
                step = timedelta(days=7 if weekly else 1)
                unit = "week" if weekly else "day"
                st.button(f"Previous {unit}", on_click=select_date, args=(selected - step,))
                st.button(f"Next {unit}", on_click=select_date, args=(selected + step,))
            with st.container(key="view_switch", width="content"):
                view = st.radio("Calendar view", ["Week", "Day"], index=0, horizontal=True, label_visibility="collapsed", key="calendar_view")
            if view == "Day":
                period_label = selected.strftime("%A, %B %d")
            else:
                week_start = selected - timedelta(days=selected.weekday())
                period_label = f"{week_start:%B %d} – {week_start + timedelta(days=6):%B %d, %Y}"
            st.markdown(f"**{period_label}**", width="content")
            st.button("Add task", type="primary", key="add_task", on_click=open_editor,
                      args=(chosen_pet, selected, "Conversation"), disabled=not owner.pets,
                      help="Add a pet first" if not owner.pets else None)
        with st.container(key="calendar_filters"):
            if view == "Day":
                date_col, pet_col, status_col = st.columns([1.5, 1.1, 1])
            else:
                pet_col, status_col = st.columns(2)
        owner_id = owner.owner_id
        pets = [p for profile in owners if owner_id is None or profile.owner_id == owner_id for p in profile.pets]
        if st.session_state.get("calendar_pet") not in [None] + [p.pet_id for p in pets]:
            st.session_state.calendar_pet = None
        if view == "Day":
            date_options = {} if "calendar_day_picker" in st.session_state else {"value": selected}
            selected = date_col.date_input("Selected day", key="calendar_day_picker",
                                           on_change=remember_date, args=("calendar_day_picker",), **date_options)
        pet_id = pet_col.selectbox("Pet", [None] + [p.pet_id for p in pets],
                                  format_func=lambda value: "All pets" if value is None else (
                                      view_owner.get_pet(value).name + " / " + next(p.name for p in owners if p.find_pet(value))),
                                  key="calendar_pet")
        status_label = status_col.selectbox("Status", ["All", "Pending", "Overdue", "Done"], key="calendar_status")
        status = None if status_label == "All" else status_label.lower()
        if selected is None:
            st.info("Choose a date to see the calendar.")
            return
        if view == "Week":
            monday = selected - timedelta(days=selected.weekday())
            days = [monday + timedelta(days=i) for i in range(7)]
            columns = []
            for day in days:
                entries = filter_entries(community_entries(owners, day, owner.timezone, owner_id), pet_id, status)
                columns.append([calendar_item(entry, view_owner.get_pet(entry.task.assigned_pet_id)) for entry in entries])
            with st.container(key="week_grid"):
                with st.container(key="week_header"):
                    header = st.columns([.5] + [1] * 7, gap=None, wrap=False)
                    header[0].markdown('<div class="paw-time-heading">Time</div>', unsafe_allow_html=True)
                    for i, day in enumerate(days):
                        header[i + 1].button(day.strftime("%a %d"), key=f"day_{i}", on_click=select_date, args=(day,),
                                             use_container_width=True, type="primary" if day == selected else "secondary")
                st.markdown(render_timeline([day.strftime("%A, %B %d") for day in days], columns), unsafe_allow_html=True)
            if owner.pets:
                st.caption("Dashed cards are estimated repeats. Dates can shift after completion.")
            return
        if selected == local_today():
            due = filter_entries(community_entries(owners, selected, owner.timezone, owner_id)
                                 + community_overdue(owners, owner.timezone, owner_id), pet_id, status)
            due = list({(e.task.task_id, e.status): e for e in due}.values())
            if due:
                with st.expander("Today's care summary"):
                    counts = [f"{sum(e.status == state for e in due)} {state}" for state in ("pending", "overdue", "done")
                              if any(e.status == state for e in due)]
                    st.write(" / ".join(counts))
        visible_entries = filter_entries(community_entries(owners, selected, owner.timezone, owner_id), pet_id, status)
        for warning in Scheduler.detect_conflicts([entry.task for entry in visible_entries if entry.status != "done"], owner.pets):
            st.warning(warning)
        if selected == local_today():
            overdue_entries = filter_entries(community_overdue(owners, owner.timezone, owner_id), pet_id, status)
            if overdue_entries:
                st.caption("Overdue")
                for entry in overdue_entries:
                    task_card(store, view_owner, entry, "overdue", owner.owner_id)
        entries = filter_entries(community_entries(owners, selected, owner.timezone, owner_id), pet_id, status)
        if selected == local_today():
            entries = [e for e in entries if e.status != "overdue"]
        if not entries:
            st.caption("No tasks scheduled for this day with these filters.")
        with st.container(key="day_grid"):
            items = [calendar_item(entry, view_owner.get_pet(entry.task.assigned_pet_id)) for entry in entries]
            st.markdown(render_timeline([selected.strftime("%A, %B %d")], [items],
                                        start_hour=0, end_hour=24), unsafe_allow_html=True)
        for entry in entries:
            task_card(store, view_owner, entry, "agenda", owner.owner_id)


def assistant_navigate(route):
    if not route:
        return False
    target = route.get("owner_id", st.session_state.get("active_owner_id"))
    current = st.session_state.get("active_owner_id")
    changed = (target != current or route["page"] != st.session_state.get("page")
               or st.session_state.get("editor_open") or st.session_state.get("pet_dialog_open"))
    if route["page"] == "Calendar":
        changed = changed or st.session_state.get("calendar_pet") != route.get("pet_id")
        changed = changed or st.session_state.get("calendar_status") != "All" or st.session_state.get("calendar_view") != "Day"
        if route.get("day"):
            changed = changed or str(st.session_state.get("calendar_date")) != route["day"]
    if not changed:
        return False
    if target != current:
        snapshot_current_draft()
        remember_active_draft()
        keys = ("task_draft", "manual_draft", "conversation_draft", "draft_mode", "entry_mode",
                "conversation", "pending_request", "editor_day", "editor_pet_id", "planner_error",
                "preview_blocked", "composer_count")
        drafts = st.session_state.setdefault("assistant_editor_drafts", {})
        drafts[current] = {key: st.session_state[key] for key in keys if key in st.session_state}
        activate_profile(target)
        for key, value in drafts.get(target, {}).items():
            st.session_state[key] = value
    st.session_state.editor_open = False
    st.session_state.pet_dialog_open = False
    st.session_state.page = route["page"]
    if route["page"] == "Calendar":
        st.session_state.calendar_pet = route.get("pet_id")
        st.session_state.calendar_status = "All"
        st.session_state.calendar_view = "Day"
        if route.get("day"):
            from datetime import date
            select_date(date.fromisoformat(route["day"]))
    return True


@st.fragment
def planner_assistant():
    route = render_assistant()
    refresh = st.session_state.pop("assistant_refresh", False)
    changed = assistant_navigate(route) if route else False
    if changed or refresh:
        st.rerun()


def main():
    if st.session_state.get("page", "Home") in ("User", "Pets", "Calendar"):
        planner_assistant()
    else:
        suspend_assistant()
    try:
        root_store = PlannerStore()
        profiles = root_store.list_profiles()
        selected = st.session_state.get("active_owner_id")
        store = PlannerStore(root_store.path, owner_id=selected)
        owner = store.load() if selected is not None else None
        st.session_state.setdefault("page", "Home")
        if owner is None:
            if selected is not None:
                activate_profile(None)
            st.session_state.active_owner_id = None
            if st.session_state.page not in ("Home", "User"):
                st.session_state.page = "User"
        elif st.session_state.get("page") not in ("Home", "User", "Pets", "Calendar"):
            st.session_state.page = "Pets"
        elif st.session_state.page == "Calendar" and not bool(owner.pets):
            st.session_state.page = "Pets"
    except (sqlite3.Error, OSError):
        st.error("Local storage is unavailable. Check folder permissions or PAWPAL_DB_PATH, then reload.")
        return
    page = st.session_state.page if st.session_state.page == "Home" else sidebar(owner, profiles)
    if "notice" in st.session_state:
        st.success(st.session_state.pop("notice"))
    if page == "Home":
        show_home(open_planner)
        return
    title = ("Change pet owner" if owner else "Choose pet owner" if profiles else "Add pet owner") if page == "User" else "Your pets" if page == "Pets" else "Your calendar"
    subtitle = ""
    if page == "Calendar":
        subtitle = owner.timezone
    planner_header(title, subtitle)
    if page == "User":
        user_page(root_store, owner, profiles)
        return
    with using_timezone(owner.timezone):
        target = st.session_state.pop("voice_calendar_target", None)
        if target and target["owner_id"] == owner.owner_id:
            st.session_state.calendar_owner = owner.owner_id
            st.session_state.calendar_pet = target["pet_id"]
            st.session_state.calendar_status = "All"
            st.session_state.calendar_view = "Day"
        if "pending_selected_day" in st.session_state:
            select_date(st.session_state.pop("pending_selected_day"))
        if page == "Pets":
            pets_page(store, owner)
        else:
            calendar_page(store, owner, [owner])
        if st.session_state.get("pet_dialog_open") and page == "Pets":
            pet_dialog(store)
        elif st.session_state.get("editor_open") and owner.pets and page == "Calendar":
            task_dialog(store, owner)


main()
