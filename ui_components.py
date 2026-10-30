"""Escaped, presentational components; all actions use native widgets."""
from html import escape
from base64 import b64encode
from app_theme import favicon
from pathlib import Path
from calendar_presentation import CalendarItem
import streamlit as st


def brand(on_home):
    image = b64encode(Path(favicon()).read_bytes()).decode("ascii")
    st.button(f"![](data:image/png;base64,{image}) **PawPal** AI PLANNER",
              key="brand_home", on_click=on_home, use_container_width=True,
              help="Go to homepage")


def summary(pending, overdue, done):
    st.markdown(
        '<div class="paw-summary" aria-label="Today\'s care summary">'
        f'<span><strong>{pending}</strong>Pending today</span>'
        f'<span><strong>{overdue}</strong>Overdue</span>'
        f'<span><strong>{done}</strong>Done today</span></div>',
        unsafe_allow_html=True,
    )


def empty_panel(title, body):
    st.markdown(f'<div class="paw-empty"><h2>{escape(title)}</h2><p>{escape(body)}</p></div>',
                unsafe_allow_html=True)


def task_summary(task, pet, owner_name=""):
    tone = ["", "blue", "rust"][(pet.pet_id - 1) % 3]
    st.markdown(
        f'<div class="paw-task-title">{escape(task.title)}</div>'
        f'<span class="paw-pet {tone}">{escape(pet.name + (" / " + owner_name if owner_name else ""))}</span>', unsafe_allow_html=True,
    )


def calendar_item(entry, pet):
    """Keep the existing community projection and viewer-zone clock intact."""
    at = entry.display_time if entry.display_time is not None else entry.task.time_of_day
    return CalendarItem(
        title=entry.task.title, minute=at.hour * 60 + at.minute if at is not None else None,
        pet=pet.name, owner=entry.owner_name, location=entry.task.location_text,
        tone=["", "blue", "rust"][(pet.pet_id - 1) % 3],
        projected=entry.projected, status=entry.status,
    )


def planner_header(title, subtitle=""):
    """Static planner header; native navigation and headings stay accessible."""
    with st.container(key="planner_header"):
        st.title(title)
        if subtitle:
            st.caption(subtitle)


def pet_identity(pet):
    """Compact species identity without inventing a pet photograph."""
    shapes = {
        "dog": '<path d="M8 30 5 27V18l5 4h13l4-9V7l7 2 3 6 6 1v5l-7 4-2 9-1 10h-4l-1-10H17l-2 10h-4V32Z"/>',
        "cat": '<path d="M12 23V8l11 8h4l11-8v15c7 14-1 21-13 21S5 37 12 23Z"/><path d="M18 28h1m12 0h1m-9 6 2 2 2-2"/>',
    }
    shape = shapes.get(pet.species.lower(), '<circle cx="25" cy="28" r="14"/><path d="M18 28h14m-7-7v14"/>')
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 50 50" fill="none" stroke="#245C45" '
           'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + shape + '</svg>')
    image = b64encode(svg.encode("utf8")).decode("ascii")
    st.html(
        '<div class="paw-pet-identity"><img alt="" aria-hidden="true" src="data:image/svg+xml;base64,'
        + image + '"><div><h3>' + escape(pet.name) + '</h3><p>'
        + escape(pet.species.capitalize()) + ' / Age ' + str(pet.age) + '</p></div></div>',
    )


def task_state(state):
    status = "warning" if state == "Overdue" else "success" if state == "Done" else ""
    st.markdown(f'<span class="paw-state {status}">{escape(state)}</span>', unsafe_allow_html=True)
