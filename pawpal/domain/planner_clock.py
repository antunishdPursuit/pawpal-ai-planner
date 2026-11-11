"""An app-session timezone without changing other users' clocks."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime
from zoneinfo import ZoneInfo

_zone = ContextVar("pawpal_timezone", default=None)


def local_today() -> date:
    zone = _zone.get()
    return datetime.now(ZoneInfo(zone)).date() if zone else date.today()


@contextmanager
def using_timezone(name: str):
    ZoneInfo(name)
    token = _zone.set(name)
    try:
        yield
    finally:
        _zone.reset(token)
