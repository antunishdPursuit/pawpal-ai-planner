"""Escaped calendar markup. Display blocks never imply a task duration."""
from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class CalendarItem:
    title: str
    minute: int | None = None
    pet: str = ""
    owner: str = ""
    location: str = ""
    tone: str = ""
    projected: bool = False
    status: str = "pending"


def _clock(minute):
    hour, part = divmod(minute, 60)
    return f"{hour % 12 or 12}:{part:02d} {'AM' if hour < 12 else 'PM'}"


def _event(item, *, top=None, lane=0, lanes=1):
    tone = item.tone if item.tone in ("blue", "rust") else ""
    state = item.status if item.status in ("done", "overdue") else ""
    kind = "paw-anytime-event" if top is None else "paw-time-event"
    classes = f"paw-calendar-event {kind} {tone} {state}" + (" projected" if item.projected else "")
    at = _clock(item.minute) if item.minute is not None else "Anytime"
    hint = "Planned repeat" if item.projected else state.capitalize()
    meta = " / ".join(part for part in (item.pet, item.owner) if part) or item.location
    detail = " · ".join(part for part in (at, hint) if part)
    label = " · ".join(part for part in dict.fromkeys((item.title, detail, meta, item.location)) if part)
    style = "" if top is None else (
        f' style="top:calc({top:.6f} * var(--paw-calendar-hour));'
        f'left:calc({100 * lane / lanes:.6f}% + var(--paw-space-1));'
        f'right:calc({100 * (lanes-lane-1) / lanes:.6f}% + var(--paw-space-1))"'
    )
    return (f'<article class="{classes}" title="{escape(label, quote=True)}" '
            f'aria-label="{escape(label, quote=True)}"{style}>'
            f'<strong>{escape(item.title)}</strong><span>{escape(detail)}</span>'
            + (f'<small>{escape(meta)}</small>' if meta else '') + '</article>')


def _layout(items):
    """Assign intersecting fixed-size display blocks to separate visual lanes."""
    # Shared CSS uses 96px/hour, 80px blocks, and a 4px gap: 52.5 minutes.
    occupied = 52.5
    groups, group, bottom = [], [], -1
    for item in sorted(items, key=lambda value: value.minute):
        if group and item.minute >= bottom:
            groups.append(group)
            group = []
        group.append(item)
        bottom = max(bottom, item.minute + occupied)
    if group:
        groups.append(group)
    for group in groups:
        ends, placed = [], []
        for item in group:
            lane = next((i for i, end in enumerate(ends) if end <= item.minute), len(ends))
            if lane == len(ends):
                ends.append(0)
            ends[lane] = item.minute + occupied
            placed.append((item, lane))
        for item, lane in placed:
            yield item, lane, len(ends)


def render_timeline(day_labels, columns, *, start_hour=None, end_hour=None):
    """Render point-in-time tasks and Anytime tasks without modifying records."""
    if len(day_labels) != len(columns) or not columns:
        raise ValueError("Each calendar day needs one item column.")
    timed = [item.minute for column in columns for item in column if item.minute is not None]
    if any(type(minute) is not int or not 0 <= minute < 1440 for minute in timed):
        raise ValueError("Calendar times must be minutes within the displayed day.")
    start = min(8, min(timed, default=480) // 60) if start_hour is None else start_hour
    end = min(24, max(18, max(timed, default=1020) // 60 + 1)) if end_hour is None else end_hour
    if not 0 <= start < end <= 24 or any(not start * 60 <= minute <= end * 60 for minute in timed):
        raise ValueError("The calendar range must contain every timed item.")
    count = len(columns)
    out = [f'<div class="paw-calendar-view" style="--paw-calendar-columns:{count};--paw-calendar-hours:{end-start}">']
    if any(item.minute is None for column in columns for item in column):
        out.append('<div class="paw-anytime-grid"><div class="paw-anytime-label">Anytime</div>')
        for label, column in zip(day_labels, columns):
            out.append(f'<section class="paw-anytime-day" aria-label="{escape(label, quote=True)} Anytime tasks">')
            out.extend(_event(item) for item in column if item.minute is None)
            out.append('</section>')
        out.append('</div>')
    out.append('<div class="paw-time-grid"><div class="paw-time-axis" aria-hidden="true">')
    for hour in range(start, end + 1):
        text = f"{hour % 12 or 12} {'AM' if hour % 24 < 12 else 'PM'}"
        out.append(f'<span class="paw-hour-label" style="top:calc({hour-start} * var(--paw-calendar-hour))">{text}</span>')
    out.append('</div>')
    for label, column in zip(day_labels, columns):
        out.append(f'<section class="paw-day-track" aria-label="{escape(label, quote=True)} timed tasks">')
        for item, lane, lanes in _layout([item for item in column if item.minute is not None]):
            out.append(_event(item, top=(item.minute - start * 60) / 60, lane=lane, lanes=lanes))
        out.append('</section>')
    out.append('</div></div>')
    return ''.join(out)
