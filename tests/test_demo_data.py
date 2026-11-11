from datetime import date, time, timedelta

import pytest

from pawpal.domain.calendar_view import community_entries
from pawpal.domain.planner_storage import PlannerStore
from seed_demo import DEMO_WEEK, PROFILES, seed_demo
from pawpal.domain.task_contract import TaskDraft


def rows(store):
    with store.connection() as conn:
        return {table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1")]
                for table in ("owner", "pet", "task", "schedule")}


def test_demo_is_complete_visible_across_the_week_and_does_not_duplicate(tmp_path):
    store = PlannerStore(tmp_path / "demo.sqlite3")
    assert seed_demo(store)
    owners = store.load_community()
    assert len(owners) == 3
    assert all("(demo)" in owner.name for owner in owners)
    pets = [pet for owner in owners for pet in owner.pets]
    assert len(pets) == 5
    assert all(len(pet.tasks) == 2 for pet in pets)
    tasks = [task for owner in owners for task in owner.get_all_tasks()]
    assert len(tasks) == 10
    assert all(task.schedule is None and task.last_completed_date is None for task in tasks)
    assert {task.due_date for task in tasks} == {DEMO_WEEK + timedelta(days=i) for i in range(7)}
    entries = [entry for i in range(7) for entry in community_entries(
        owners, DEMO_WEEK + timedelta(days=i), "America/New_York")]
    assert len(entries) == 10
    assert {entry.task.task_id for entry in entries} == {task.task_id for task in tasks}
    before = rows(store)
    assert seed_demo(store) is False
    assert rows(store) == before
    with store.connection() as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_demo_preserves_existing_users_pets_tasks_and_schedules(tmp_path):
    store = PlannerStore(tmp_path / "existing.sqlite3")
    owner = store.create_profile("Existing user")
    selected = PlannerStore(store.path, owner.owner_id)
    pet = selected.add_pet("Existing pet", "cat", 6)
    selected.create_task(TaskDraft(pet.pet_id, "Existing care", date(2026, 10, 29),
                                   time(8), repeat="WEEKLY"))
    before = rows(store)
    assert seed_demo(store)
    after = rows(store)
    for table, records in before.items():
        assert after[table][:len(records)] == records
    assert len(after["owner"]) == 4
    assert len(after["pet"]) == 6
    assert len(after["task"]) == 11


def test_demo_name_collision_refuses_without_partial_data(tmp_path):
    store = PlannerStore(tmp_path / "collision.sqlite3")
    store.create_profile(PROFILES[1][0])
    before = rows(store)
    with pytest.raises(ValueError, match="No records were added or replaced"):
        seed_demo(store)
    assert rows(store) == before


def test_demo_write_failure_rolls_back_the_whole_set(tmp_path, monkeypatch):
    store = PlannerStore(tmp_path / "rollback.sqlite3")
    store.create_profile("Existing user")
    before = rows(store)
    save = store._save

    def fail_on_second_owner(conn, owner):
        if owner.name == PROFILES[1][0]:
            raise RuntimeError("Simulated write failure")
        save(conn, owner)

    monkeypatch.setattr(store, "_save", fail_on_second_owner)
    with pytest.raises(RuntimeError, match="Simulated write failure"):
        seed_demo(store)
    assert rows(store) == before
