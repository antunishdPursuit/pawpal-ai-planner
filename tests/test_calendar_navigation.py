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
    assert not app.text_input
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
    assert any("No tasks scheduled" in item.value for item in app.caption)
    timeline = next(item.value for item in app.markdown if "paw-calendar-view" in item.value)
    assert "--paw-calendar-hours:24" in timeline
    assert timeline.count('class="paw-hour-label"') == 25
    button(app, "Next day").click().run()
    assert app.session_state.selected_day == date(2026, 11, 7)
    button(app, "Previous day").click().run()
    assert app.session_state.selected_day == date(2026, 11, 6)
    app.radio(key="calendar_view").set_value("Week").run()
    assert not app.text_input
    assert app.session_state.selected_day == date(2026, 11, 6)
    assert [item.label for item in app.selectbox] == ["Pet", "Status"]
    assert "Next week" in [item.label for item in app.button]
    assert not app.exception


def test_day_picker_updates_week_range_and_preserves_chosen_day():
    app = calendar_app()
    app.radio(key="calendar_view").set_value("Day").run()
    app.date_input[0].set_value(date(2026, 12, 31)).run()
    app.radio(key="calendar_view").set_value("Week").run()
    assert not app.exception
    assert any("December 28 \u2013 January 03, 2027" in item.value for item in app.markdown)
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


def personal_calendar_fixture():
    source = Path("app.py").read_text(encoding="utf-8").rsplit("\nmain()", 1)[0]
    fixture = """
from datetime import date, time, timedelta
from pawpal_system import Owner, Pet, Task
if "fixture_owners" not in st.session_state:
    owner = Owner("Current")
    first, second = Pet("First", "cat", 2), Pet("Second", "dog", 1)
    owner.add_pet(first)
    owner.add_pet(second)
    for pet in (first, second):
        pet.add_task(Task("Current care", "", pet.pet_id, one_off_due_date=local_today(), time_of_day=time(9)))
    first.add_task(Task("Late care", "", first.pet_id, one_off_due_date=local_today()-timedelta(days=1)))
    other = Owner("Other private owner")
    other_pet = Pet("Other private pet", "cat", 2)
    other.add_pet(other_pet)
    other_pet.add_task(Task("Other private task", "", other_pet.pet_id, one_off_due_date=local_today()))
    st.session_state.fixture_owners = (owner, other, first.pet_id)
owner, other, first_pet_id = st.session_state.fixture_owners
st.session_state.setdefault("calendar_date", local_today())
st.session_state.fixture_pet_id = first_pet_id
calendar_workspace(None, owner, [owner, other])
"""
    return AppTest.from_string(source + fixture).run(timeout=20)


def test_personal_calendar_ignores_other_profiles_and_filters_conflicts():
    app = personal_calendar_fixture()
    assert not app.exception
    assert [item.label for item in app.selectbox] == ["Pet", "Status"]
    app.radio(key="calendar_view").set_value("Day").run()
    assert len(app.warning) == 1
    assert "Other private" not in " ".join(item.value for item in app.markdown)
    app.selectbox(key="calendar_pet").set_value(app.session_state.fixture_pet_id).run()
    assert not app.warning
    assert not app.exception


def test_overdue_tasks_do_not_get_described_as_an_empty_calendar():
    app = personal_calendar_fixture()
    app.radio(key="calendar_view").set_value("Day").run()
    app.selectbox(key="calendar_status").set_value("Overdue").run()
    assert any("Late care" in item.value for item in app.markdown)
    assert any("No tasks scheduled for this day" in item.value for item in app.caption)
    assert not any("No tasks match" in item.value for item in app.caption)
    assert not app.warning
    assert not app.exception
