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
        if self.completion:
            return "done"
        if self.projected or (
            self.task.schedule and self.task.schedule.schedule_type == ScheduleType.CUSTOM
            and self.day > local_today()
        ):
            return "pending"
        return self.task.status


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



def draft_conflicts(owner, draft):
    """Only conflicts involving this proposed time, on this proposed date."""
    if draft.time_of_day is None or draft.due_date is None:
        return []
    matching = [e.task for e in entries_for_day(owner, draft.due_date)
                if e.status != "done" and e.task.time_of_day == draft.time_of_day]
    if not matching:
        return []
    candidate = Task(draft.title or "New task", "", draft.pet_id, task_id=0,
                     time_of_day=draft.time_of_day)
    return Scheduler.detect_conflicts(matching + [candidate], owner.pets)
