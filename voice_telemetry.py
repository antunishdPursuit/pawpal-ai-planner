"""Local, bounded voice metadata. No audio, dialogue, identity or credentials."""
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import RLock
from uuid import UUID

from planner_storage import default_database
from voice_status import connection_diagnostic

MAX_BYTES = 1024 * 1024
BACKUPS = 3
EVENTS = {"diagnostics_enabled", "credential_requested", "credential_prepared", "credential_failed", "live_ended"}
_lock = RLock()


class _FileHandler(RotatingFileHandler):
    def handleError(self, record):
        raise OSError("Voice diagnostic write failed")


def diagnostics_path():
    return default_database().parent / "logs" / "voice.jsonl"


def record_voice_event(event, *, attempt_id=None, diagnostic=None, failed=None,
                       preparation_seconds=None, path=None, max_bytes=MAX_BYTES):
    """Best-effort writes must never interfere with the actual voice workflow."""
    if not isinstance(event, str) or event not in EVENTS:
        return False
    record = {"schema": 1, "at": datetime.now(timezone.utc).isoformat(), "event": event}
    if isinstance(attempt_id, str):
        try:
            record["attempt"] = str(UUID(attempt_id))
        except ValueError:
            pass
    if type(failed) is bool:
        record["failed"] = failed
    if type(preparation_seconds) in (int, float) and 0 <= preparation_seconds <= 3600:
        record["preparation_seconds"] = round(preparation_seconds, 3)
    if isinstance(diagnostic, dict):
        detail = connection_diagnostic({"diagnostic": diagnostic})
        # Raw service text may echo private input; keep it in temporary UI only.
        detail.pop("provider_reason", None)
        record["connection"] = detail
    try:
        destination = Path(path) if path is not None else diagnostics_path()
        payload = json.dumps(record, ensure_ascii=True, allow_nan=False)
        with _lock:
            destination.parent.mkdir(parents=True, exist_ok=True)
            handler = _FileHandler(destination, maxBytes=max_bytes,
                                          backupCount=BACKUPS, encoding="utf8", delay=True)
            try:
                handler.setFormatter(logging.Formatter("%(message)s"))
                handler.emit(logging.LogRecord("pawpal.voice.local", logging.INFO, "", 0, payload, (), None))
            finally:
                handler.close()
        return True
    except (OSError, ValueError, TypeError):
        logging.getLogger("pawpal.voice").warning("Could not write local voice diagnostics; voice remains available.")
        return False
