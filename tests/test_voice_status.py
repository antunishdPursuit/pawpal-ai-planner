import logging
from voice_status import connection_diagnostic, connection_error_message, record_connection_end


def test_close_reason_is_bounded_and_credentials_are_not_retained(caplog):
    diagnostic = connection_diagnostic({"diagnostic": {
        "cause": "connection_closed", "phase": "listening", "code": 1008,
        "elapsed_ms": 12345, "was_clean": True,
        "provider_reason": "Rejected wss://example.test/?access_token=secret auth_tokens/private token=secret\n" + "x" * 500,
        "token": "private", "transcript": "private words",
    }})
    assert diagnostic["seconds"] == 12.3
    assert "secret" not in diagnostic["provider_reason"]
    assert "auth_tokens/" not in diagnostic["provider_reason"]
    assert len(diagnostic["provider_reason"]) <= 300
    assert "token" not in diagnostic and "transcript" not in diagnostic
    with caplog.at_level(logging.WARNING, logger="pawpal.voice"):
        record_connection_end(diagnostic)
    assert "code=1008" in caplog.text and "seconds=12.3" in caplog.text
    assert "private" not in caplog.text and "provider_reason" not in caplog.text


def test_failure_feedback_distinguishes_service_network_and_permission():
    assert "busy" in connection_error_message({"code": 1013})
    assert "rejected" in connection_error_message({"code": 1008})
    assert "had an error" in connection_error_message({"code": 1011})
    assert "interrupted" in connection_error_message({"code": 1006})
    assert "ended this session" in connection_error_message({"cause": "server_go_away"})
    assert "microphone access" in connection_error_message({"cause": "microphone_denied"})
    assert "took too long" in connection_error_message({"cause": "connection_timeout"})


def test_malformed_diagnostics_cannot_inject_messages_or_expand_logs():
    assert connection_diagnostic({"diagnostic": []}) == {}
    detail = connection_diagnostic({"diagnostic": {"cause": "<script>", "phase": "secret",
                                                  "code": True, "elapsed_ms": float("nan")}})
    assert detail == {"cause": "connection_error", "phase": "idle"}
    assert "<script>" not in connection_error_message(detail)

    detail = connection_diagnostic({"diagnostic": {"cause": {}, "phase": []}})
    assert detail == {"cause": "connection_error", "phase": "idle"}
