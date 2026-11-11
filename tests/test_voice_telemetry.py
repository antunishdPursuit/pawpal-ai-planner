from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import json

from pawpal.assistant.voice_telemetry import record_voice_event


def read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf8").splitlines()]


def test_records_survive_reopening_and_exclude_all_dialogue_and_credentials(tmp_path):
    path = tmp_path / "logs" / "voice.jsonl"
    attempt = str(uuid4())
    assert record_voice_event("credential_requested", attempt_id=attempt, path=path)
    assert record_voice_event("live_ended", attempt_id=attempt, failed=True, path=path, diagnostic={
        "cause": "connection_closed", "phase": "listening", "code": 1006, "elapsed_ms": 12500,
        "was_clean": False, "network_online": True, "input_chunks": 12, "output_chunks": 3,
        "milestones": [{"stage": "microphone", "at_ms": 0}, {"stage": "listening", "at_ms": 800}],
        "provider_reason": "secret dialogue and token=PRIVATE", "token": "PRIVATE",
        "transcript": "private dialogue", "owner_id": 42, "pet": "Luna", "task": "Walk",
    })
    records = read(path)
    assert [r["event"] for r in records] == ["credential_requested", "live_ended"]
    assert all(r["attempt"] == attempt and r["at"].endswith("+00:00") for r in records)
    assert records[1]["connection"]["code"] == 1006
    assert records[1]["connection"]["seconds"] == 12.5
    assert records[1]["connection"]["milestones"][-1]["stage"] == "listening"
    text = path.read_text()
    for forbidden in ("PRIVATE", "dialogue", "Luna", "Walk", "provider_reason", "owner_id", "token", "transcript"):
        assert forbidden not in text


def test_rotation_keeps_recent_records_and_caps_backup_count(tmp_path):
    path = tmp_path / "voice.jsonl"
    for i in range(60):
        assert record_voice_event("live_ended", path=path, max_bytes=600,
                                 diagnostic={"cause": "stopped", "phase": "listening", "elapsed_ms": i * 1000})
    files = list(tmp_path.glob("voice.jsonl*"))
    assert len(files) == 4
    assert all(f.stat().st_size <= 600 for f in files)
    assert read(path)[-1]["connection"]["seconds"] == 59


def test_parallel_sessions_write_complete_independent_lines(tmp_path):
    path = tmp_path / "voice.jsonl"
    attempts = [str(uuid4()) for _ in range(24)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(pool.map(lambda attempt: record_voice_event("credential_requested", attempt_id=attempt, path=path), attempts))
    assert {r["attempt"] for r in read(path)} == set(attempts)


def test_unwritable_logs_do_not_interrupt_voice_and_malformed_data_is_bounded(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    assert not record_voice_event("live_ended", path=blocker / "voice.jsonl")
    assert not record_voice_event("live_ended", path=tmp_path)
    assert not record_voice_event([], path=tmp_path / "voice.jsonl")
    path = tmp_path / "voice.jsonl"
    assert not record_voice_event("arbitrary private message", path=path)
    assert record_voice_event("live_ended", path=path, attempt_id="token=PRIVATE", diagnostic={
        "cause": [], "phase": {}, "input_chunks": -1, "output_chunks": True,
        "milestones": [{"stage": "PRIVATE", "at_ms": 0}] * 50,
    })
    result = read(path)[0]
    assert "attempt" not in result
    assert result["connection"] == {"cause": "connection_error", "phase": "idle", "milestones": []}
