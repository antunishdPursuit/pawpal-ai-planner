"""Read-only calendar projections; viewing a date never creates tasks."""
from dataclasses import dataclass
from datetime import date
from pawpal_system import Owner, Task, ScheduleType, Scheduler
from planner_clock import local_today


@dataclass(frozen=True)
class CalendarEntry:
    task: Task
    day: date
    projected: bool = False
    completion: bool = False

    @property
    def status(self):
        return "pending" if self.projected else "done" if self.completion else self.task.status


def entries_for_day(owner: Owner, day: date) -> list[CalendarEntry]:
    today = local_today()
    entries = []
    for task in owner.get_all_tasks():
        custom = task.schedule and task.schedule.schedule_type == ScheduleType.CUSTOM
        if task.last_completed_date == day:
            entries.append(CalendarEntry(task, day, completion=True))
            if not custom:
                continue
        if task.status == "done" and not custom:
            continue
        due = task.due_date or today
        if day == due and not (task.status == "done" and due == today):
            entries.append(CalendarEntry(task, day))
        elif task.schedule and day > max(due, today):
            anchor = max(due, today)
            if (day - anchor).days % task.schedule.interval == 0:
                entries.append(CalendarEntry(task, day, projected=True))
    return sorted(entries, key=lambda e: (e.task.time_of_day is None, e.task.time_of_day, e.task.task_id))


def filter_entries(entries, pet_id=None, status=None):
    return [e for e in entries if (pet_id is None or e.task.assigned_pet_id == pet_id)
            and (status is None or e.status == status)]


def day_conflicts(owner: Owner, day: date, candidate=None) -> list[str]:
    tasks = [e.task for e in entries_for_day(owner, day) if e.status != "done"]
    if candidate is not None:
        tasks.append(candidate)
    return Scheduler.detect_conflicts(tasks, owner.pets)
