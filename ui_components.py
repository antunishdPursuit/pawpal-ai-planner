"""Escaped, presentational components; all actions use native widgets."""
from html import escape
from base64 import b64encode
from app_theme import favicon
from pathlib import Path
import streamlit as st


def brand():
    image = b64encode(Path(favicon()).read_bytes()).decode("ascii")
    st.markdown(
        '<div class="paw-brand"><img alt="" aria-hidden="true" src="data:image/png;base64,' + image +
        '"><div><strong>PawPal</strong><small>AI Planner</small></div></div>', unsafe_allow_html=True,
    )


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


def task_summary(task, pet, state):
    tone = ["", "blue", "rust"][(pet.pet_id - 1) % 3]
    status = "warning" if state == "Overdue" else "success" if state == "Done" else ""
    st.markdown(
        f'<div class="paw-task-title">{escape(task.title)}</div>'
        f'<span class="paw-pet {tone}">{escape(pet.name)}</span> '
        f'<span class="paw-state {status}">{escape(state)}</span>', unsafe_allow_html=True,
    )


def calendar_chip(entry, pet, color):
    at = entry.task.time_of_day.strftime("%I:%M %p").lstrip("0") if entry.task.time_of_day else "Anytime"
    planned = " / planned" if entry.projected else ""
    st.markdown(
        f'<div class="paw-chip {color} {"projected" if entry.projected else ""}">'
        f'<small>{escape(at + planned)}</small><strong>{escape(entry.task.title)}</strong>'
        f'<small>{escape(pet.name)}</small></div>', unsafe_allow_html=True,
    )
