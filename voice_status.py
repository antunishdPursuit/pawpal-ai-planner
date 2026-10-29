"""Bounded, credential-free voice connection diagnostics and user feedback."""
import logging
import re

logger = logging.getLogger("pawpal.voice")
CAUSES = {"stopped", "review", "session_limit", "connection_closed", "connection_error",
          "connection_timeout", "server_go_away", "provider_error", "invalid_response",
          "microphone_denied", "audio_unavailable", "page_hidden"}
PHASES = {"idle", "microphone", "connecting", "listening", "speaking", "confirming", "finishing"}


def connection_diagnostic(event):
    raw = event.get("diagnostic")
    if not isinstance(raw, dict):
        return {}
    detail = {}
    cause, phase = raw.get("cause"), raw.get("phase")
    detail["cause"] = cause if isinstance(cause, str) and cause in CAUSES else "connection_error"
    detail["phase"] = phase if isinstance(phase, str) and phase in PHASES else "idle"
    code = raw.get("code")
    if type(code) is int and 1000 <= code <= 4999:
        detail["code"] = code
    duration = raw.get("elapsed_ms")
    if type(duration) in (int, float) and 0 <= duration <= 3_600_000:
        detail["seconds"] = round(duration / 1000, 1)
    if type(raw.get("was_clean")) is bool:
        detail["was_clean"] = raw["was_clean"]
    reason = raw.get("provider_reason")
    if isinstance(reason, str):
        # Provider text is evidence, not markup. Never retain a URL or token.
        reason = re.sub(r"(?:https?|wss?)://\S+", "[connection URL omitted]", reason, flags=re.I)
        reason = re.sub(r"(?:auth_tokens/|AIza)[\w.\-/]+", "[credential omitted]", reason)
        reason = re.sub(r"(?i)(?:access_token|api[_-]?key|token)\s*[:=]\s*[^\s,;]+", "[credential omitted]", reason)
        detail["provider_reason"] = " ".join(reason.split())[:300]
    return detail


def connection_error_message(detail):
    cause, code = detail.get("cause"), detail.get("code")
    if cause == "microphone_denied":
        return "Allow microphone access to use live speech. You can still type instead."
    if cause == "audio_unavailable":
        return "Speech could not start in this browser. Check your microphone or type instead."
    if cause == "connection_timeout":
        message = "Speech took too long to connect."
    elif cause == "server_go_away" or code == 1000:
        message = "The speech service ended this session."
    elif code == 1013:
        message = "The speech service is busy."
    elif code == 1011:
        message = "The speech service had an error."
    elif code in (1007, 1008) or cause == "provider_error":
        message = "The speech service rejected this live session."
    elif cause == "invalid_response":
        message = "The speech service returned an unreadable response."
    else:
        message = "The live connection was interrupted."
    return message + " Your transcript is still available. Try Talk live again or type."


def record_connection_end(detail):
    # Exclude transcript, provider text, session IDs and all credentials.
    logger.warning("Voice ended: cause=%s phase=%s code=%s seconds=%s clean=%s",
                   detail.get("cause"), detail.get("phase"), detail.get("code"),
                   detail.get("seconds"), detail.get("was_clean"))
