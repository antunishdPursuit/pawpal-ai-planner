from datetime import date, time, timedelta
from unittest.mock import patch
from pawpal_system import Owner, Pet, Task, Schedule, ScheduleType
from task_contract import TaskDraft
from voice_planner import live_config
from planner_storage import LocalProfile, PlannerStore
from calendar_view import draft_conflicts, entries_for_day


def test_live_context_excludes_other_profiles():
    owner = Owner("Current")
    owner.add_pet(Pet("Mochi", "cat", 2))
    config = live_config(owner, [LocalProfile(999, "PRIVATE_OTHER_PROFILE", "UTC", 3)])
    instruction = config["system_instruction"]
    assert "PRIVATE_OTHER_PROFILE" not in instruction
    assert '"users"' not in instruction
    assert "Mochi" in instruction


def test_custom_history_survives_reopen(tmp_path):
    store = PlannerStore(tmp_path / "care.sqlite3")
    store.create_profile("Current")
    pet = store.add_pet("Mochi", "cat", 2)
    first = date(2026, 11, 1)
    task = store.create_task(TaskDraft(pet.pet_id, "Feed", first, repeat="CUSTOM", interval_days=2))
    with patch("pawpal_system.local_today", return_value=first), patch("planner_clock.local_today", return_value=first):
        store.complete_task(task.task_id)
    with patch("pawpal_system.local_today", return_value=first + timedelta(days=2)), patch("planner_clock.local_today", return_value=first + timedelta(days=2)):
        store.complete_task(task.task_id)
    owner = PlannerStore(store.path).load()
    for day in (first, first + timedelta(days=2)):
        assert len([e for e in entries_for_day(owner, day) if e.completion]) == 1
    assert len(owner.get_all_tasks()) == 1


def test_recurring_conflicts_include_later_dates():
    owner = Owner("Current")
    pet = Pet("Mochi", "cat", 2)
    owner.add_pet(pet)
    first = date.today()
    pet.add_task(Task("Appointment", "", pet.pet_id, one_off_due_date=first + timedelta(days=500), time_of_day=time(9)))
    assert draft_conflicts(owner, TaskDraft(pet.pet_id, "Daily", first, time(9), "DAILY"))
    assert not draft_conflicts(owner, TaskDraft(pet.pet_id, "Daily", first, time(10), "DAILY"))


def test_recurrence_intersection_and_nonintersection():
    owner = Owner("Current")
    pet = Pet("Mochi", "cat", 2)
    owner.add_pet(pet)
    first = date.today()
    pet.add_task(Task("Every four days", "", pet.pet_id, schedule=Schedule(ScheduleType.CUSTOM, first, 4), time_of_day=time(9)))
    assert not draft_conflicts(owner, TaskDraft(pet.pet_id, "Offset", first + timedelta(days=1), time(9), "CUSTOM", 2))
    assert draft_conflicts(owner, TaskDraft(pet.pet_id, "Overlap", first + timedelta(days=2), time(9), "CUSTOM", 6))
