"""Local, transactional storage for the PawPal domain model."""
from contextlib import contextmanager
from dataclasses import dataclass
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


@dataclass(frozen=True)
class LocalProfile:
    owner_id: int
    name: str
    timezone: str
    pet_count: int


class PlannerStore:
    def __init__(self, path: str | Path | None = None, owner_id: int | None = None):
        self.owner_id = owner_id
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

    @staticmethod
    def _reserve_ids(conn):
        # IDs belong to the database, including profiles not currently selected.
        for table, column, counter in (("owner", "owner_id", _owner_ids),
                                       ("pet", "pet_id", _pet_ids),
                                       ("task", "task_id", _task_ids)):
            counter.reserve(conn.execute(f"SELECT COALESCE(MAX({column}), 0) FROM {table}").fetchone()[0])

    def list_profiles(self) -> list[LocalProfile]:
        with self.connection() as conn:
            return [LocalProfile(**dict(row)) for row in conn.execute(
                "SELECT o.owner_id, o.name, o.timezone, COUNT(p.pet_id) AS pet_count "
                "FROM owner o LEFT JOIN pet p ON p.owner_id=o.owner_id "
                "GROUP BY o.owner_id ORDER BY o.owner_id")]

    @staticmethod
    def _profile_values(name, timezone):
        name = clean_text(name, "Owner name", 80, True)
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            raise ValueError("Choose a valid timezone.") from None
        return name, timezone

    def create_profile(self, name: str, timezone: str = "America/New_York") -> Owner:
        name, timezone = self._profile_values(name, timezone)
        with self.transaction() as conn:
            if any(row[0].casefold() == name.casefold() for row in conn.execute("SELECT name FROM owner")):
                raise ValueError("That user already exists. Choose them from the saved users.")
            self._reserve_ids(conn)
            owner = Owner(name, timezone)
            conn.execute("INSERT INTO owner VALUES (?, ?, ?)", (owner.owner_id, name, timezone))
            return self._load(conn, owner.owner_id)

    def _load(self, conn, owner_id=None) -> Owner | None:
        self._reserve_ids(conn)
        selected = self.owner_id if owner_id is None else owner_id
        row = (conn.execute("SELECT * FROM owner WHERE owner_id=?", (selected,)).fetchone()
               if selected is not None else conn.execute("SELECT * FROM owner ORDER BY owner_id LIMIT 1").fetchone())
        if row is None:
            return None
        owner = Owner(row["name"], row["timezone"])
        owner.owner_id = row["owner_id"]
        _owner_ids.reserve(owner.owner_id)
        for r in conn.execute("SELECT * FROM pet WHERE owner_id=? ORDER BY pet_id", (owner.owner_id,)):
            pet = Pet(r["name"], r["species"], r["age"], pet_id=r["pet_id"])
            _pet_ids.reserve(pet.pet_id)
            owner.add_pet(pet)
        schedules = {r["task_id"]: r for r in conn.execute(
            "SELECT s.* FROM schedule s JOIN task t ON t.task_id=s.task_id "
            "JOIN pet p ON p.pet_id=t.pet_id WHERE p.owner_id=?", (owner.owner_id,))}
        for r in conn.execute(
            "SELECT t.* FROM task t JOIN pet p ON p.pet_id=t.pet_id WHERE p.owner_id=? ORDER BY t.task_id",
            (owner.owner_id,)):
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

    def load_community(self) -> list[Owner]:
        """Read every local profile in one snapshot; writes remain owner-scoped."""
        with self.connection() as conn:
            conn.execute("BEGIN")
            ids = [row[0] for row in conn.execute("SELECT owner_id FROM owner ORDER BY owner_id")]
            return [self._load(conn, owner_id) for owner_id in ids]

    def _save(self, conn, owner: Owner):
        # Replace only this owner's aggregate atomically, under a write lock.
        # Other local users and concurrent readers retain their complete state.
        conn.execute("DELETE FROM schedule WHERE task_id IN "
                     "(SELECT t.task_id FROM task t JOIN pet p ON p.pet_id=t.pet_id WHERE p.owner_id=?)",
                     (owner.owner_id,))
        conn.execute("DELETE FROM task WHERE pet_id IN (SELECT pet_id FROM pet WHERE owner_id=?)",
                     (owner.owner_id,))
        conn.execute("DELETE FROM pet WHERE owner_id=?", (owner.owner_id,))
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
        name, timezone = self._profile_values(name, timezone)
        with self.transaction() as conn:
            owner = self._load(conn)
            if owner is None:
                if self.owner_id is not None:
                    raise ValueError("Choose an existing user or create a new one.")
                owner = Owner(name, timezone)
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

    def create_task(self, draft: TaskDraft, allow_conflicts: bool = False) -> Task:
        with self.transaction() as conn:
            owner = self._load(conn)
            if owner is None:
                raise ValueError("Create your profile first.")
            existing = next((t for t in owner.get_all_tasks() if t.creation_request_id == draft.request_id), None)
            if existing:
                return existing
            draft = draft.validate(owner)
            from calendar_view import draft_conflicts
            with using_timezone(owner.timezone):
                if draft_conflicts(owner, draft) and not allow_conflicts:
                    raise ValueError("This time conflicts with another task. Review the warning and choose whether to keep it.")
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
