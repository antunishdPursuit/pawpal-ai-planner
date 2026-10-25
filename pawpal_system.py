from dataclasses import dataclass, field
from datetime import date, time, timedelta
from enum import Enum
from typing import Optional
from planner_clock import local_today


class ScheduleType(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    CUSTOM = "custom"


@dataclass
class Schedule:
    schedule_type: ScheduleType
    start_date: date
    interval: int = 1               # set automatically for DAILY/WEEKLY; required for CUSTOM

    def __post_init__(self):
        if self.schedule_type == ScheduleType.DAILY:
            self.interval = 1
        elif self.schedule_type == ScheduleType.WEEKLY:
            self.interval = 7
        elif self.schedule_type == ScheduleType.CUSTOM:
            if self.interval <= 0:
                raise ValueError("CUSTOM schedule requires interval > 0")
        self.next_due_date: date = self.start_date

    def calculate_next_due_date(self) -> date:
        """Advance next_due_date by interval days and return the new date."""
        self.next_due_date = self.next_due_date + timedelta(days=self.interval)
        return self.next_due_date

    def is_due_today(self) -> bool:
        """Return True if the task is due today or is overdue."""
        return self.next_due_date <= local_today()


class _IDCounter:
    """Simple auto-incrementing ID generator shared across entity types."""
    def __init__(self):
        self._count = 0

    def next(self) -> int:
        self._count += 1
        return self._count

    def reserve(self, used_id: int):
        self._count = max(self._count, used_id)


_pet_ids = _IDCounter()
_task_ids = _IDCounter()
_owner_ids = _IDCounter()


@dataclass
class Task:
    title: str
    description: str
    assigned_pet_id: int
    schedule: Optional[Schedule] = None
    time_of_day: Optional[time] = None          # e.g. time(7, 0) for 7:00am
    task_id: int = field(default_factory=_task_ids.next)
    last_completed_date: Optional[date] = None
    one_off_due_date: Optional[date] = None
    location_text: str = ""
    creation_request_id: Optional[str] = None

    @property
    def due_date(self) -> Optional[date]:
        return self.schedule.next_due_date if self.schedule else self.one_off_due_date

    @property
    def status(self) -> str:
        """Derive task status from completion and schedule: done, overdue, or pending."""
        today = local_today()
        if self.last_completed_date is not None:
            # Daily/weekly tasks are individual occurrences; keep completed history.
            if not self.schedule or self.schedule.schedule_type != ScheduleType.CUSTOM:
                return "done"
            if self.last_completed_date == today:
                return "done"
        if self.due_date is not None and self.due_date < today:
            return "overdue"
        return "pending"

    def mark_complete(self) -> bool:
        """Complete this occurrence once; custom routines advance in place.

        Return False when already done. Daily/weekly occurrences keep their
        original due date; Scheduler creates a separate next occurrence.
        """
        if self.status == "done":
            return False
        self.last_completed_date = local_today()
        if self.schedule and self.schedule.schedule_type == ScheduleType.CUSTOM:
            self.schedule.next_due_date = local_today() + timedelta(days=self.schedule.interval)
        return True

    def next_occurrence(self) -> Optional["Task"]:
        """Return a new Task instance for the next recurrence, or None if not recurring."""
        if not self.schedule:
            return None
        completed_on = self.last_completed_date or local_today()
        next_start = completed_on + timedelta(days=self.schedule.interval)
        new_schedule = Schedule(
            schedule_type=self.schedule.schedule_type,
            start_date=next_start,
            interval=self.schedule.interval
        )
        return Task(
            title=self.title,
            description=self.description,
            assigned_pet_id=self.assigned_pet_id,
            schedule=new_schedule,
            time_of_day=self.time_of_day,
            location_text=self.location_text
        )

    def update_task(self, title: str = None, description: str = None, schedule: Schedule = None):
        """Update one or more task fields; raises ValueError if title is empty."""
        if title is not None:
            if title.strip() == "":
                raise ValueError("title cannot be empty")
            self.title = title
        if description is not None:
            self.description = description
        if schedule is not None:
            self.schedule = schedule

    def to_display_dict(self) -> dict:
        """Return a plain dict of task fields formatted for terminal display."""
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "time_of_day": self.time_of_day.strftime("%I:%M %p") if self.time_of_day else "no time set",
            "status": self.status,
            "due_today": self.schedule.is_due_today() if self.schedule else "no schedule",
            "next_due": str(self.schedule.next_due_date) if self.schedule else "N/A",
            "last_completed": str(self.last_completed_date) if self.last_completed_date else "never",
            "location": self.location_text,
        }


@dataclass
class Pet:
    name: str
    species: str
    age: int
    pet_id: int = field(default_factory=_pet_ids.next)
    tasks: list[Task] = field(default_factory=list)

    def add_task(self, task: Task):
        """Add a task to this pet; raises ValueError on mismatched pet or duplicate task."""
        if task.assigned_pet_id != self.pet_id:
            raise ValueError(f"Task is assigned to pet_id {task.assigned_pet_id}, not {self.pet_id}")
        if any(t.task_id == task.task_id for t in self.tasks):
            raise ValueError(f"Task {task.task_id} already exists for this pet")
        self.tasks.append(task)

    def remove_task(self, task_id: int):
        """Remove a task by ID; raises ValueError if not found."""
        original_len = len(self.tasks)
        self.tasks = [t for t in self.tasks if t.task_id != task_id]
        if len(self.tasks) == original_len:
            raise ValueError(f"Task {task_id} not found")

    def get_tasks(self) -> list[Task]:
        """Return a shallow copy of all tasks for this pet."""
        return list(self.tasks)     # shallow copy to prevent external mutation

    def get_tasks_by_status(self, status: str) -> list[Task]:
        """Return all tasks matching the given status: 'pending', 'done', or 'overdue'."""
        return [t for t in self.tasks if t.status == status]

    def get_due_tasks_today(self) -> list[Task]:
        """Return tasks due today, excluding already-completed ones, sorted by time_of_day."""
        due = [
            t for t in self.tasks
            if t.status != "done"
            and (t.due_date is None or t.due_date <= local_today())
        ]
        return sorted(due, key=lambda t: (t.time_of_day is None, t.time_of_day))


class Owner:
    def __init__(self, name: str, timezone: str = "America/New_York"):
        self.owner_id: int = _owner_ids.next()
        self.name = name
        self.timezone = timezone
        self.pets: list[Pet] = []

    def add_pet(self, pet: Pet):
        """Register a pet to this owner; raises ValueError on duplicate pet_id."""
        if any(p.pet_id == pet.pet_id for p in self.pets):
            raise ValueError(f"Pet {pet.pet_id} already registered")
        self.pets.append(pet)

    def remove_pet(self, pet_id: int):
        """Remove a pet by ID; raises ValueError if not found."""
        original_len = len(self.pets)
        self.pets = [p for p in self.pets if p.pet_id != pet_id]
        if len(self.pets) == original_len:
            raise ValueError(f"Pet {pet_id} not found")

    def find_pet(self, pet_id: int) -> Optional[Pet]:
        """Returns None if not found — use when existence is uncertain."""
        return next((p for p in self.pets if p.pet_id == pet_id), None)

    def get_pet(self, pet_id: int) -> Pet:
        """Raises ValueError if not found — use when pet is expected to exist."""
        pet = self.find_pet(pet_id)
        if pet is None:
            raise ValueError(f"Pet {pet_id} not found")
        return pet

    def get_tasks_for_pet(self, pet_id: int, status: str = None) -> list[Task]:
        """Return tasks for a specific pet, optionally filtered by status."""
        pet = self.get_pet(pet_id)
        if status:
            return pet.get_tasks_by_status(status)
        return pet.get_tasks()

    def get_all_tasks(self) -> list[Task]:
        """Return every pet's tasks in a new list, including completed history."""
        return [task for pet in self.pets for task in pet.get_tasks()]

    def view_daily_plan(self):
        """Print a formatted daily schedule for all pets owned by this owner."""
        print(f"\n=== Daily Plan for {self.name} ===")
        if not self.pets:
            print("No pets registered.")
            return
        daily_tasks = Scheduler.get_daily_tasks(self)
        for pet in self.pets:
            due = [task for task in daily_tasks if task.assigned_pet_id == pet.pet_id]
            print(f"\n{pet.name} ({pet.species}, age {pet.age}):")
            if not due:
                print("  No tasks due today.")
            else:
                for task in due:
                    d = task.to_display_dict()
                    print(f"  [{d['status'].upper()}] {d['time_of_day']}  {d['title']} — {d['description']}")
                    print(f"       Next due: {d['next_due']} | Last completed: {d['last_completed']}")


class Scheduler:
    """Read an owner's tasks and apply scheduling rules across their pets."""

    @staticmethod
    def get_daily_tasks(owner: Owner, include_completed: bool = False) -> list[Task]:
        """Read Owner.get_all_tasks(); return due tasks and optionally today's completions.

        Unscheduled tasks are available today. Future occurrences and older
        completed history stay outside the daily view.
        """
        today = local_today()
        daily_tasks = []
        for task in owner.get_all_tasks():
            if task.status == "done":
                if include_completed and task.last_completed_date == today:
                    daily_tasks.append(task)
            elif task.due_date is None or task.due_date <= today:
                daily_tasks.append(task)
        return Scheduler.sort_by_time(daily_tasks)

    @staticmethod
    def sort_by_time(tasks: list[Task]) -> list[Task]:
        """Sort tasks by time_of_day; tasks with no time sort last."""
        return sorted(tasks, key=lambda t: (t.time_of_day is None, t.time_of_day))

    @staticmethod
    def complete_and_reschedule(task: Task, pet: "Pet") -> Optional[Task]:
        """Mark a task complete and auto-create the next occurrence for daily/weekly tasks.

        Returns the new Task, or None for custom/one-off/already-done tasks.
        A task must belong to the supplied pet before it can be completed.
        """
        if task.assigned_pet_id != pet.pet_id or not any(
            existing is task for existing in pet.tasks
        ):
            raise ValueError("Task must belong to the supplied pet")
        if not task.mark_complete():
            return None
        if task.schedule and task.schedule.schedule_type in (ScheduleType.DAILY, ScheduleType.WEEKLY):
            new_task = task.next_occurrence()
            pet.add_task(new_task)
            return new_task
        return None

    @staticmethod
    def detect_conflicts(tasks: list[Task], pets: list = None) -> list[str]:
        """Check for tasks scheduled at the same time; return a list of warning strings."""
        warnings = []
        id_to_name = {p.pet_id: p.name for p in pets} if pets else {}

        # group tasks by their time_of_day — skip tasks with no time set
        time_buckets: dict[time, list[Task]] = {}
        for task in tasks:
            if task.time_of_day is None:
                continue
            time_buckets.setdefault(task.time_of_day, []).append(task)

        for slot, bucket in time_buckets.items():
            if len(bucket) > 1:
                labels = [
                    f"'{t.title}' ({id_to_name.get(t.assigned_pet_id, f'pet_id={t.assigned_pet_id}')})"
                    for t in bucket
                ]
                warnings.append(f"CONFLICT at {slot.strftime('%I:%M %p')}: {' vs '.join(labels)}")

        return warnings

    @staticmethod
    def filter_tasks(tasks: list[Task], status: str = None, pet_name: str = None,
                     pets: list = None) -> list[Task]:
        """Filter tasks by completion status and/or pet name in a single pass."""
        id_to_name = {p.pet_id: p.name.lower() for p in pets} if (pet_name and pets) else {}
        return [
            t for t in tasks
            if (not status or t.status == status)
            and (not pet_name or id_to_name.get(t.assigned_pet_id) == pet_name.lower())
        ]


# --- Quick terminal test ---
if __name__ == "__main__":
    owner = Owner("Alex")

    dog = Pet(name="Buddy", species="Dog", age=3)
    cat = Pet(name="Whiskers", species="Cat", age=5)
    owner.add_pet(dog)
    owner.add_pet(cat)

    feed_dog = Task(
        title="Feed",
        description="Morning kibble",
        assigned_pet_id=dog.pet_id,
        schedule=Schedule(ScheduleType.DAILY, start_date=local_today())
    )
    walk_dog = Task(
        title="Walk",
        description="30 min walk around the block",
        assigned_pet_id=dog.pet_id,
        schedule=Schedule(ScheduleType.CUSTOM, start_date=local_today(), interval=2)
    )
    feed_cat = Task(
        title="Feed",
        description="Wet food twice daily",
        assigned_pet_id=cat.pet_id,
        schedule=Schedule(ScheduleType.DAILY, start_date=local_today())
    )

    dog.add_task(feed_dog)
    dog.add_task(walk_dog)
    cat.add_task(feed_cat)

    owner.view_daily_plan()

    print("\n--- Marking Buddy's feed as complete ---")
    next_feed = Scheduler.complete_and_reschedule(feed_dog, dog)
    print(f"Next feed due: {next_feed.schedule.next_due_date}")

    print("\n--- Attempting to mark complete again today ---")
    Scheduler.complete_and_reschedule(feed_dog, dog)

    owner.view_daily_plan()
