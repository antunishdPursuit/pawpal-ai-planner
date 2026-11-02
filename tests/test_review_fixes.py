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
