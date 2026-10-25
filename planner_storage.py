"""Local, transactional storage for the PawPal domain model."""
from contextlib import contextmanager
from datetime import date, time
import os
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pawpal_system import (
    Owner, Pet, Task, Schedule, ScheduleType, Scheduler,
    _owner_ids, _pet_ids, _task_ids,
)
from planner_clock import using_timezone
from task_contract import TaskDraft, clean_text

SCHEMA = """
CREATE TABLE IF NOT EXISTS owner (
 owner_id INTEGER PRIMARY KEY, name TEXT NOT NULL, timezone TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pet (
 pet_id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES owner(owner_id),
 name TEXT NOT NULL, species TEXT NOT NULL, age INTEGER NOT NULL CHECK(age BETWEEN 0 AND 30)
);
CREATE TABLE IF NOT EXISTS task (
 task_id INTEGER PRIMARY KEY, pet_id INTEGER NOT NULL REFERENCES pet(pet_id),
 title TEXT NOT NULL, description TEXT NOT NULL, one_off_due_date TEXT,
 time_of_day TEXT, last_completed_date TEXT, location_text TEXT NOT NULL,
 creation_request_id TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS schedule (
 task_id INTEGER PRIMARY KEY REFERENCES task(task_id),
 schedule_type TEXT NOT NULL CHECK(schedule_type IN ('DAILY','WEEKLY','CUSTOM')),
 start_date TEXT NOT NULL, interval_days INTEGER NOT NULL CHECK(interval_days > 0),
 next_due_date TEXT NOT NULL
);
"""


def default_database() -> Path:
    override = os.environ.get("PAWPAL_DB_PATH")
    if override:
        return Path(override).expanduser()
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    return base / "PawPalAIPlanner" / "pawpal.sqlite3"


def _date(value):
    return date.fromisoformat(value) if value else None


def _iso(value):
    return value.isoformat() if value is not None else None


class PlannerStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_database()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _load(self, conn) -> Owner | None:
        row = conn.execute("SELECT * FROM owner ORDER BY owner_id LIMIT 1").fetchone()
        if row is None:
            return None
        owner = Owner(row["name"], row["timezone"])
        owner.owner_id = row["owner_id"]
        _owner_ids.reserve(owner.owner_id)
        for r in conn.execute("SELECT * FROM pet WHERE owner_id=? ORDER BY pet_id", (owner.owner_id,)):
            pet = Pet(r["name"], r["species"], r["age"], pet_id=r["pet_id"])
            _pet_ids.reserve(pet.pet_id)
            owner.add_pet(pet)
        schedules = {r["task_id"]: r for r in conn.execute("SELECT * FROM schedule")}
        for r in conn.execute("SELECT * FROM task ORDER BY task_id"):
            pet = owner.find_pet(r["pet_id"])
            if pet is None:
                continue
            schedule = None
            if r["task_id"] in schedules:
                sr = schedules[r["task_id"]]
                schedule = Schedule(ScheduleType[sr["schedule_type"]], _date(sr["start_date"]), sr["interval_days"])
                schedule.next_due_date = _date(sr["next_due_date"])
            task = Task(
                title=r["title"], description=r["description"], assigned_pet_id=pet.pet_id,
                task_id=r["task_id"], schedule=schedule,
                time_of_day=time.fromisoformat(r["time_of_day"]) if r["time_of_day"] else None,
                last_completed_date=_date(r["last_completed_date"]),
                one_off_due_date=_date(r["one_off_due_date"]), location_text=r["location_text"],
                creation_request_id=r["creation_request_id"],
            )
            _task_ids.reserve(task.task_id)
            pet.add_task(task)
        return owner

    def load(self) -> Owner | None:
        with self.connection() as conn:
            # A consistent snapshot while another session may be saving.
            conn.execute("BEGIN")
            return self._load(conn)

    def _save(self, conn, owner: Owner):
        # Small single-profile aggregate: replace it atomically, under a write lock.
        # Readers see either the old complete state or the new complete state.
        conn.execute("DELETE FROM schedule")
        conn.execute("DELETE FROM task")
        conn.execute("DELETE FROM pet")
        conn.execute(
            "INSERT INTO owner VALUES (?, ?, ?) ON CONFLICT(owner_id) DO UPDATE SET name=excluded.name, timezone=excluded.timezone",
            (owner.owner_id, owner.name, owner.timezone),
        )
        for pet in owner.pets:
            conn.execute("INSERT INTO pet VALUES (?, ?, ?, ?, ?)",
                         (pet.pet_id, owner.owner_id, pet.name, pet.species, pet.age))
            for task in pet.tasks:
                conn.execute("INSERT INTO task VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                    task.task_id, pet.pet_id, task.title, task.description,
                    _iso(task.one_off_due_date), _iso(task.time_of_day),
                    _iso(task.last_completed_date), task.location_text, task.creation_request_id,
                ))
                if task.schedule:
                    s = task.schedule
                    conn.execute("INSERT INTO schedule VALUES (?, ?, ?, ?, ?)", (
                        task.task_id, s.schedule_type.name, _iso(s.start_date),
                        s.interval, _iso(s.next_due_date),
                    ))

    def save_profile(self, name: str, timezone: str = "America/New_York") -> Owner:
        name = clean_text(name, "Owner name", 80, True)
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            raise ValueError("Choose a valid timezone.") from None
        with self.transaction() as conn:
            owner = self._load(conn) or Owner(name, timezone)
            owner.name, owner.timezone = name, timezone
            self._save(conn, owner)
            return self._load(conn)

    def add_pet(self, name: str, species: str, age: int) -> Pet:
        name = clean_text(name, "Pet name", 80, True)
        species = clean_text(species, "Species", 40, True)
        if type(age) is not int or not 0 <= age <= 30:
            raise ValueError("Pet age must be between 0 and 30.")
        with self.transaction() as conn:
            owner = self._load(conn)
            if owner is None:
                raise ValueError("Create your profile first.")
            pet = Pet(name, species, age)
            owner.add_pet(pet)
            self._save(conn, owner)
            return self._load(conn).get_pet(pet.pet_id)

    def create_task(self, draft: TaskDraft) -> Task:
        with self.transaction() as conn:
            owner = self._load(conn)
            if owner is None:
                raise ValueError("Create your profile first.")
            existing = next((t for t in owner.get_all_tasks() if t.creation_request_id == draft.request_id), None)
            if existing:
                return existing
            draft = draft.validate(owner)
            schedule = None if draft.repeat == "NONE" else Schedule(
                ScheduleType[draft.repeat], draft.due_date, draft.interval_days,
            )
            task = Task(
                draft.title, draft.description, draft.pet_id, schedule=schedule,
                time_of_day=draft.time_of_day,
                one_off_due_date=draft.due_date if schedule is None else None,
                location_text=draft.location, creation_request_id=draft.request_id,
            )
            owner.get_pet(draft.pet_id).add_task(task)
            self._save(conn, owner)
            return next(t for t in self._load(conn).get_all_tasks() if t.task_id == task.task_id)

    def complete_task(self, task_id: int) -> tuple[Task, Task | None]:
        with self.transaction() as conn:
            owner = self._load(conn)
            if owner is None:
                raise ValueError("Create your profile first.")
            task = next((t for t in owner.get_all_tasks() if t.task_id == task_id), None)
            if task is None:
                raise ValueError("Task no longer exists. Refresh the calendar.")
            with using_timezone(owner.timezone):
                from planner_clock import local_today
                if task.status != "done" and task.due_date is not None and task.due_date > local_today():
                    raise ValueError("Complete this task when it is due.")
                next_task = Scheduler.complete_and_reschedule(task, owner.get_pet(task.assigned_pet_id))
            self._save(conn, owner)
            saved = self._load(conn)
            by_id = {t.task_id: t for t in saved.get_all_tasks()}
            return by_id[task_id], by_id[next_task.task_id] if next_task else None
