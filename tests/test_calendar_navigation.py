from datetime import date
from pathlib import Path
from streamlit.testing.v1 import AppTest


def calendar_app():
    source = Path("app.py").read_text(encoding="utf-8").rsplit("\nmain()", 1)[0]
    fixture = """
from datetime import date
from pawpal_system import Owner
st.session_state.setdefault("calendar_date", date(2026, 11, 6))
owner = Owner("Calendar fixture")
calendar_workspace(None, owner, [owner])
"""
    return AppTest.from_string(source + fixture).run(timeout=20)


def button(app, label):
    return next(item for item in app.button if item.label == label)


def test_week_navigation_moves_seven_days_and_has_no_today_button():
    app = calendar_app()
    assert not app.exception
    assert app.text_input[0].label == "Selected week"
    assert app.text_input[0].value == "November 02 \u2013 November 08, 2026"
    assert not app.subheader
    assert any("November 02 – November 08, 2026" in item.value for item in app.markdown)
    assert not any("paw-week-title" in item.value for item in app.markdown)
    assert not app.date_input
    assert "Choose week" not in [item.label for item in app.button]
    assert "Today" not in [item.label for item in app.button]
    button(app, "Next week").click().run()
    assert app.session_state.selected_day == date(2026, 11, 13)
    button(app, "Previous week").click().run()
    assert app.session_state.selected_day == date(2026, 11, 6)
    assert not app.exception


def test_empty_day_keeps_full_day_timeline_and_day_navigation():
    app = calendar_app()
    app.radio(key="calendar_view").set_value("Day").run()
    assert not app.exception
    assert app.date_input[0].label == "Selected day"
    assert app.session_state.selected_day == date(2026, 11, 6)
    assert not app.subheader
    assert any("Friday, November 06" in item.value for item in app.markdown)
    assert any("No tasks match" in item.value for item in app.caption)
    timeline = next(item.value for item in app.markdown if "paw-calendar-view" in item.value)
    assert "--paw-calendar-hours:24" in timeline
    assert timeline.count('class="paw-hour-label"') == 25
    button(app, "Next day").click().run()
    assert app.session_state.selected_day == date(2026, 11, 7)
    button(app, "Previous day").click().run()
    assert app.session_state.selected_day == date(2026, 11, 6)
    app.radio(key="calendar_view").set_value("Week").run()
    assert app.text_input[0].label == "Selected week"
    assert app.text_input[0].value == "November 02 \u2013 November 08, 2026"
    assert app.session_state.selected_day == date(2026, 11, 6)
    assert app.selectbox(key="calendar_owner").label == "Pet owner"
    assert "Next week" in [item.label for item in app.button]
    assert not app.exception


def test_day_picker_updates_week_range_and_preserves_chosen_day():
    app = calendar_app()
    app.radio(key="calendar_view").set_value("Day").run()
    app.date_input[0].set_value(date(2026, 12, 31)).run()
    app.radio(key="calendar_view").set_value("Week").run()
    assert not app.exception
    assert app.text_input[0].value == "December 28 \u2013 January 03, 2027"
    app.radio(key="calendar_view").set_value("Day").run()
    assert app.date_input[0].value == date(2026, 12, 31)
    assert not app.exception


def test_week_navigation_then_day_view_keeps_the_new_date():
    app = calendar_app()
    button(app, "Next week").click().run()
    app.radio(key="calendar_view").set_value("Day").run()
    assert app.date_input[0].value == date(2026, 11, 13)
    assert app.session_state.calendar_date == date(2026, 11, 13)
    assert not app.exception
