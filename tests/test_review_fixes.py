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
