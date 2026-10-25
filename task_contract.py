"""Shared input contract for manual and AI-created tasks."""
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time
from uuid import uuid4
from pawpal_system import Owner


def clean_text(value: str, label: str, limit: int, required=False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text.")
    value = value.strip()
    if required and not value:
        raise ValueError(f"Enter {label.lower()}.")
    if len(value) > limit:
        raise ValueError(f"{label} must be at most {limit} characters.")
    if any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise ValueError(f"{label} contains unsupported characters.")
    return value


@dataclass(frozen=True)
class TaskDraft:
    pet_id: int
    title: str
    due_date: date | None = None
    time_of_day: time | None = None
    repeat: str = "NONE"
    interval_days: int = 1
    description: str = ""
    location: str = ""
    request_id: str = field(default_factory=lambda: str(uuid4()))

    def validate(self, owner: Owner) -> "TaskDraft":
        if type(self.pet_id) is not int or owner.find_pet(self.pet_id) is None:
            raise ValueError("Choose a registered pet.")
        if self.due_date is not None and (
            not isinstance(self.due_date, date) or isinstance(self.due_date, datetime)
        ):
            raise ValueError("Choose a valid date.")
        if self.time_of_day is not None and (
            not isinstance(self.time_of_day, time) or self.time_of_day.tzinfo is not None
        ):
            raise ValueError("Choose a local time or Anytime.")
        if self.repeat not in {"NONE", "DAILY", "WEEKLY", "CUSTOM"}:
            raise ValueError("Choose a supported repeat option.")
        if self.repeat != "NONE" and self.due_date is None:
            raise ValueError("Choose a start date for a repeating task.")
        if type(self.interval_days) is not int or not 1 <= self.interval_days <= 365:
            raise ValueError("Custom interval must be between 1 and 365 days.")
        try:
            from uuid import UUID
            UUID(self.request_id)
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Start a new task draft.") from None
        interval = 1 if self.repeat == "DAILY" else 7 if self.repeat == "WEEKLY" else self.interval_days
        return replace(
            self, title=clean_text(self.title, "Task title", 120, True),
            description=clean_text(self.description, "Description", 1000),
            location=clean_text(self.location, "Location", 300),
            interval_days=interval,
        )
