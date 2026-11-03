from types import SimpleNamespace
from io import BytesIO
import base64
import wave
import live_confirmation
import assistant_ui as ui
from assistant_actions import AssistantActions
from planner_storage import PlannerStore


class State(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


class Rerun(Exception): pass


def audio():
    stream=BytesIO()
    with wave.open(stream,"wb") as recording:
        recording.setnchannels(1);recording.setsampwidth(2);recording.setframerate(16000)
        recording.writeframes(b"\0\0"*16000)
    return base64.b64encode(stream.getvalue()).decode()


def harness(tmp_path,monkeypatch):
    root=PlannerStore(tmp_path/"bridge.sqlite3")
    owner=root.create_profile("Bridge owner")
    pet=PlannerStore(root.path,owner.owner_id).add_pet("Bridge pet","cat",3)
    state=State()
    events=[]
    monkeypatch.setattr(ui.st,"session_state",state)
    monkeypatch.setattr(ui.st,"rerun",lambda:(_ for _ in ()).throw(Rerun()))
    monkeypatch.setattr(ui,"assistant_component",lambda:lambda **kwargs:SimpleNamespace(outbox=events))
    monkeypatch.setattr(ui,"PlannerStore",lambda:root)
    monkeypatch.setattr(ui,"is_configured",lambda:True)
    monkeypatch.setattr(ui,"prepare_live",lambda *args:{"token":"test-only","session_id":"session","issued_at":ui.time()})
    monkeypatch.setattr(ui,"respond",lambda *args:"Typed response")
    monkeypatch.setattr(live_confirmation,"transcribe",lambda *args:"Yes, save it.")
    def drain():
        for _ in range(20):
            try: return ui.render_assistant()
            except Rerun: pass
        raise AssertionError("Event bridge did not drain")
    return root,owner,pet,state,events,drain


def test_prepare_without_start_does_not_block_chat(tmp_path,monkeypatch):
    root,o,p,state,events,drain=harness(tmp_path,monkeypatch)
    events.append({"id":"prepare","kind":"prepare_voice"});drain()
    assert state["assistant_credential"]["token"]=="test-only"
    events.append({"id":"chat","kind":"chat","text":"Hello"});drain()
    assert state["assistant_receipts"][-1]["message"]=="Typed response"
    assert "assistant_credential" not in state


def test_cancel_and_stop_reject_queued_save_before_dispatch(tmp_path,monkeypatch):
    for end_kind in ["cancel_tools","voice_end"]:
        root,o,p,state,events,drain=harness(tmp_path/end_kind,monkeypatch)
        events.append({"id":"prepare","kind":"prepare_voice"});drain()
        a=AssistantActions(root.path,state["assistant_state"])
        proposal=a.execute("preview_task",dict(owner_id=o.owner_id,pet_id=p.pet_id,title="Walk",due_date="2026-12-03",time_of_day=None,anytime_confirmed=True),turn=1)
        events.extend([{"id":"save","kind":"live_tool","session_id":"session","turn":2,"utterance":"yes",
                        "call":{"id":"save-call","name":"save_task","args":{"proposal_id":proposal["proposal_id"]}}},
                       {"id":"cancel","kind":end_kind,"session_id":"session","call_ids":["save-call"],"history":[]}])
        drain()
        receipt=next(r for r in state["assistant_receipts"] if r["id"]=="save")
        assert receipt["result"]["cancelled"]
        assert not PlannerStore(root.path,o.owner_id).load().get_all_tasks()


def test_late_cancel_reports_committed_save_instead_of_cancellation(tmp_path,monkeypatch):
    root,o,p,state,events,drain=harness(tmp_path,monkeypatch)
    events.append({"id":"prepare","kind":"prepare_voice"});drain()
    a=AssistantActions(root.path,state["assistant_state"])
    proposal=a.execute("preview_task",dict(owner_id=o.owner_id,pet_id=p.pet_id,title="Walk",due_date="2026-12-03",time_of_day=None,anytime_confirmed=True),turn=1)
    events.extend([{"id":"turn","kind":"voice_turn","session_id":"session","turn":2,"closed":True},
                   {"id":"save","kind":"live_tool","session_id":"session","turn":2,"audio_turn":2,"preview_id":proposal["proposal_id"],"audio":audio(),
                    "utterance":"stale transcript", "call":{"id":"save-call","name":"save_task","args":{"proposal_id":proposal["proposal_id"]}}}])
    drain()
    verification=state["assistant_receipts"][-1]["verification_id"]
    assert not PlannerStore(root.path,o.owner_id).load().get_all_tasks()
    events.append({"id":"commit","kind":"live_commit","session_id":"session","audio_turn":2,
                   "verification_id":verification,"call":{"id":"save-call","name":"save_task"}})
    drain()
    events.append({"id":"cancel","kind":"cancel_tools","session_id":"session","call_ids":["save-call"]})
    drain()
    assert "saved before cancellation" in state["assistant_receipts"][-1]["message"]
    assert len(PlannerStore(root.path,o.owner_id).load().get_all_tasks())==1


def test_voice_end_counts_non_tool_turns_before_returning_to_text(tmp_path,monkeypatch):
    root,o,p,state,events,drain=harness(tmp_path,monkeypatch)
    events.append({"id":"prepare","kind":"prepare_voice"});drain()
    events.append({"id":"end","kind":"voice_end","session_id":"session","turn":7,"history":[]});drain()
    assert state["assistant_state"]["turn"]==7
    assert "live_session" not in state["assistant_state"]


def test_stop_during_confirmation_asr_prevents_late_commit(tmp_path,monkeypatch):
    root,o,p,state,events,drain=harness(tmp_path,monkeypatch)
    events.append({"id":"prepare","kind":"prepare_voice"});drain()
    a=AssistantActions(root.path,state["assistant_state"])
    proposal=a.execute("preview_task",dict(owner_id=o.owner_id,pet_id=p.pet_id,title="Walk",due_date="2026-12-03",time_of_day=None,anytime_confirmed=True),turn=1)
    def stop_while_verifying(*args):
        events.append({"id":"stop","kind":"voice_end","session_id":"session","turn":2,"history":[]})
        return "Yes, save it."
    monkeypatch.setattr(live_confirmation,"transcribe",stop_while_verifying)
    events.extend([{"id":"turn","kind":"voice_turn","session_id":"session","turn":2,"closed":True},
                   {"id":"save","kind":"live_tool","session_id":"session","turn":2,"audio_turn":2,"preview_id":proposal["proposal_id"],"audio":audio(),
                    "call":{"id":"save-call","name":"save_task","args":{"proposal_id":proposal["proposal_id"]}}}])
    drain()
    verification=next(r["verification_id"] for r in state["assistant_receipts"] if r["id"]=="save")
    events.append({"id":"late-commit","kind":"live_commit","session_id":"session","audio_turn":2,
                   "verification_id":verification,"call":{"id":"save-call","name":"save_task"}})
    drain()
    assert state["assistant_receipts"][-1]["result"]["cancelled"]
    assert not PlannerStore(root.path,o.owner_id).load().get_all_tasks()


def test_latest_audio_boundary_wins_over_earlier_queued_commit(tmp_path,monkeypatch):
    root,o,p,state,events,drain=harness(tmp_path,monkeypatch)
    events.append({"id":"prepare","kind":"prepare_voice"});drain()
    a=AssistantActions(root.path,state["assistant_state"])
    proposal=a.execute("preview_task",dict(owner_id=o.owner_id,pet_id=p.pet_id,title="Walk",due_date="2026-12-03",time_of_day=None,anytime_confirmed=True),turn=1)
    events.extend([{"id":"turn","kind":"voice_turn","session_id":"session","turn":2,"closed":True},
                   {"id":"save","kind":"live_tool","session_id":"session","turn":2,"audio_turn":2,"preview_id":proposal["proposal_id"],"audio":audio(),
                    "call":{"id":"save-call","name":"save_task","args":{"proposal_id":proposal["proposal_id"]}}}])
    drain()
    verification=state["assistant_receipts"][-1]["verification_id"]
    events.extend([{"id":"commit","kind":"live_commit","session_id":"session","audio_turn":2,
                    "verification_id":verification,"call":{"id":"save-call","name":"save_task"}},
                   {"id":"new-turn","kind":"voice_turn","session_id":"session","turn":3,"closed":False}])
    drain()
    assert not next(r for r in state["assistant_receipts"] if r["id"]=="commit")["result"]["ok"]
    assert not PlannerStore(root.path,o.owner_id).load().get_all_tasks()
