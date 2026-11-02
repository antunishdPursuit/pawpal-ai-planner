"""Read-only calendar projections; viewing a date never creates tasks."""
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from pawpal_system import Owner, Task, ScheduleType, Scheduler
from planner_clock import local_today, using_timezone


@dataclass(frozen=True)
class CalendarEntry:
    task: Task
    day: date
    projected: bool = False
    completion: bool = False
    owner_id: int | None = None
    owner_name: str = ""
    display_time: time | None = None
    source_status: str | None = None

    @property
    def status(self):
        if self.source_status is not None:
            return self.source_status
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
        if task.last_completed_date == day or day in task.completion_dates:
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
    """Check exact start-time overlap across finite and recurring schedules."""
    from math import gcd
    if draft.time_of_day is None or draft.due_date is None:
        return []
    step = {"NONE": 0, "DAILY": 1, "WEEKLY": 7}.get(draft.repeat, draft.interval_days)
    matching = []
    for task in owner.get_all_tasks():
        if task.time_of_day != draft.time_of_day:
            continue
        custom = task.schedule and task.schedule.schedule_type == ScheduleType.CUSTOM
        if task.status == "done" and not custom:
            continue
        anchor = task.due_date or local_today()
        interval = task.schedule.interval if task.schedule else 0
        def sequences(start, period):
            # Match the calendar: the due date plus projected future dates.
            return [(start, 0)] + ([(max(start, local_today()) + timedelta(days=period), period)] if period else [])
        def intersects(a, n, b, m):
            if not n and not m:
                return a == b
            if not n:
                return a >= b and (a - b).days % m == 0
            if not m:
                return b >= a and (b - a).days % n == 0
            return (a - b).days % gcd(n, m) == 0
        overlap = any(intersects(a, n, b, m)
                      for a, n in sequences(draft.due_date, step)
                      for b, m in sequences(anchor, interval))
        if overlap:
            matching.append(task)
    if not matching:
        return []
    candidate = Task(draft.title or "New task", "", draft.pet_id, task_id=0,
                     time_of_day=draft.time_of_day)
    return Scheduler.detect_conflicts(matching + [candidate], owner.pets)


def community_entries(owners, day, timezone, owner_id=None):
    """Project timed occurrences into the viewer's zone; Anytime stays a care date."""
    zone = ZoneInfo(timezone)
    start = datetime.combine(day, time.min, zone)
    end = datetime.combine(day + timedelta(days=1), time.min, zone) - timedelta(microseconds=1)
    result = []
    for owner in owners:
        if owner_id is not None and owner.owner_id != owner_id:
            continue
        source_zone = ZoneInfo(owner.timezone)
        first, last = start.astimezone(source_zone).date(), end.astimezone(source_zone).date()
        dates = {day, first, last}
        with using_timezone(owner.timezone):
            for source_day in sorted(dates):
                for entry in entries_for_day(owner, source_day):
                    at = entry.task.time_of_day
                    displayed = datetime.combine(source_day, at, source_zone).astimezone(zone) if at else None
                    shown_day = displayed.date() if displayed else source_day
                    if shown_day == day:
                        result.append(replace(entry, day=day, owner_id=owner.owner_id,
                                              owner_name=owner.name,
                                              display_time=displayed.time() if displayed else None,
                                              source_status=entry.status))
    return sorted(result, key=lambda e: (e.display_time is None, e.display_time or time.max, e.task.task_id))


def community_overdue(owners, timezone, owner_id=None):
    result = []
    for owner in owners:
        if owner_id is not None and owner.owner_id != owner_id:
            continue
        with using_timezone(owner.timezone):
            for task in owner.get_all_tasks():
                if task.status != "overdue":
                    continue
                at = task.time_of_day
                shown = datetime.combine(task.due_date, at, ZoneInfo(owner.timezone)).astimezone(ZoneInfo(timezone)) if at else None
                result.append(CalendarEntry(task, shown.date() if shown else task.due_date,
                                            owner_id=owner.owner_id, owner_name=owner.name,
                                            display_time=shown.time() if shown else None, source_status="overdue"))
    return sorted(result, key=lambda e: (e.day, e.display_time is None, e.display_time or time.max, e.task.task_id))
