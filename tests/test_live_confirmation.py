import base64
from io import BytesIO
import wave
import pytest
import pawpal.planning.live_confirmation as confirmation
from pawpal.assistant.assistant_actions import AssistantActions
from pawpal.domain.planner_storage import PlannerStore
from pawpal.planning.gemini_planner import PlannerError


def fixture(tmp_path):
    root=PlannerStore(tmp_path/"confirmation.sqlite3")
    owner=root.create_profile("Confirmation owner")
    pet=PlannerStore(root.path,owner.owner_id).add_pet("Confirmation pet","cat",3)
    actions=AssistantActions(root.path,{})
    proposal=actions.execute("preview_task",dict(owner_id=owner.owner_id,pet_id=pet.pet_id,title="Walk",
                             due_date="2026-12-03",time_of_day="10:00"),turn=1)
    stream=BytesIO()
    with wave.open(stream,"wb") as recording:
        recording.setnchannels(1);recording.setsampwidth(2);recording.setframerate(16000)
        recording.writeframes(b"\0\0"*16000)
    event={"session_id":"session","call":{"id":"save","name":"save_task","args":{"proposal_id":proposal["proposal_id"]}},
           "turn":2,"audio_turn":2,"preview_id":proposal["proposal_id"],"audio":base64.b64encode(stream.getvalue()).decode(),
           "utterance":"Create a walk. (stale Live transcript)"}
    session={"id":"session","base_turn":0,"audio_turn":2,"audio_closed":True}
    return root,owner,actions,event,session


def test_stale_live_text_cannot_override_completed_audio_confirmation(tmp_path,monkeypatch):
    root,owner,actions,event,session=fixture(tmp_path)
    calls=[]
    monkeypatch.setattr(confirmation,"transcribe",lambda *args:calls.append(1) or "Yes, save it.")
    verified=confirmation.stage_save(event,actions,session)
    assert verified["verification_id"]
    assert not PlannerStore(root.path,owner.owner_id).load().get_all_tasks()
    assert confirmation.stage_save(event,actions,session)==verified
    assert calls==[1]
    ack={**event,**verified}
    saved=confirmation.commit_save(ack,actions,session)
    assert saved["saved"]
    assert len(PlannerStore(root.path,owner.owner_id).load().get_all_tasks())==1


@pytest.mark.parametrize("text",["Yes, but don't save it.","No.","Yes, change it to tomorrow."])
def test_entire_confirmation_rejects_negative_or_changed_details(tmp_path,monkeypatch,text):
    root,owner,actions,event,session=fixture(tmp_path)
    event["utterance"]="Yes"  # A positive Live fragment must not authorize the save.
    monkeypatch.setattr(confirmation,"transcribe",lambda *args:text)
    result=confirmation.stage_save(event,actions,session)
    assert not result["result"]["ok"]
    assert not actions.state.get("live_verifications")
    assert not PlannerStore(root.path,owner.owner_id).load().get_all_tasks()


def test_asr_failure_is_cached_without_transcript_fallback(tmp_path,monkeypatch):
    root,owner,actions,event,session=fixture(tmp_path)
    calls=[]
    def fail(*args):
        calls.append(1)
        raise PlannerError("unavailable")
    monkeypatch.setattr(confirmation,"transcribe",fail)
    event["utterance"]="Yes, save it."
    assert not confirmation.stage_save(event,actions,session)["result"]["ok"]
    assert not confirmation.stage_save(event,actions,session)["result"]["ok"]
    assert calls==[1]
    assert not PlannerStore(root.path,owner.owner_id).load().get_all_tasks()


def test_late_verification_cannot_commit_for_new_audio_session_or_preview(tmp_path,monkeypatch):
    root,owner,actions,event,session=fixture(tmp_path)
    monkeypatch.setattr(confirmation,"transcribe",lambda *args:"Yes")
    verified=confirmation.stage_save(event,actions,session)
    ack={**event,**verified}
    for changed in [{**session,"audio_turn":3},{**session,"audio_closed":False},{**session,"id":"new-session"}]:
        assert not confirmation.commit_save(ack,actions,changed)["ok"]
    actions.state["proposal"]["id"]="new-preview"
    assert not confirmation.commit_save(ack,actions,session)["ok"]
    assert not PlannerStore(root.path,owner.owner_id).load().get_all_tasks()


def test_open_or_overlong_audio_never_reaches_confirmation_asr(tmp_path,monkeypatch):
    root,owner,actions,event,session=fixture(tmp_path)
    monkeypatch.setattr(confirmation,"transcribe",lambda *args:(_ for _ in ()).throw(AssertionError("No ASR")))
    assert not confirmation.stage_save(event,actions,{**session,"audio_closed":False})["result"]["ok"]
    stream=BytesIO()
    with wave.open(stream,"wb") as recording:
        recording.setnchannels(1);recording.setsampwidth(2);recording.setframerate(16000);recording.writeframes(b"\0\0"*(31*16000))
    event["audio"]=base64.b64encode(stream.getvalue()).decode()
    assert not confirmation.stage_save(event,actions,session)["result"]["ok"]


def test_yes_spoken_before_preview_is_displayed_cannot_authorize_it(tmp_path,monkeypatch):
    root,owner,actions,event,session=fixture(tmp_path)
    event["preview_id"]=None
    monkeypatch.setattr(confirmation,"transcribe",lambda *args:(_ for _ in ()).throw(AssertionError("No ASR before preview")))
    assert not confirmation.stage_save(event,actions,session)["result"]["ok"]
    assert not PlannerStore(root.path,owner.owner_id).load().get_all_tasks()


@pytest.mark.parametrize('reply', ["That sounds great to me. Let's do it.", "Yes, I confirm it.", "Yes, you should save it."])
def test_natural_confirmation_saves_once(tmp_path, monkeypatch, reply):
    root, owner, actions, event, session = fixture(tmp_path)
    monkeypatch.setattr(confirmation, 'transcribe', lambda *args: reply)
    verified = confirmation.stage_save(event, actions, session)
    ack = {**event, **verified}
    assert confirmation.commit_save(ack, actions, session)['saved']
    assert len(PlannerStore(root.path, owner.owner_id).load().get_all_tasks()) == 1
    assert not confirmation.commit_save(ack, actions, session)['ok']
    assert len(PlannerStore(root.path, owner.owner_id).load().get_all_tasks()) == 1


def test_rejected_confirmation_recovers_with_new_preview(tmp_path, monkeypatch):
    root, owner, actions, event, session = fixture(tmp_path)
    monkeypatch.setattr(confirmation, 'transcribe', lambda *args: 'Maybe')
    failed = confirmation.stage_save(event, actions, session)['result']
    assert failed['requires_preview']
    assert 'proposal' not in actions.state
    assert not PlannerStore(root.path, owner.owner_id).load().get_all_tasks()
    pet = PlannerStore(root.path, owner.owner_id).load().pets[0]
    fresh = actions.execute('preview_task', dict(owner_id=owner.owner_id, pet_id=pet.pet_id,
        title='Walk', due_date='2026-12-03', time_of_day='10:00'), turn=2)
    event.update(turn=3, audio_turn=3, preview_id=fresh['proposal_id'],
        call={'id': 'retry', 'name': 'save_task', 'args': {'proposal_id': fresh['proposal_id']}})
    session.update(audio_turn=3)
    monkeypatch.setattr(confirmation, 'transcribe', lambda *args: 'Yes, you should save it.')
    verified = confirmation.stage_save(event, actions, session)
    assert confirmation.commit_save({**event, **verified}, actions, session)['saved']
    assert len(PlannerStore(root.path, owner.owner_id).load().get_all_tasks()) == 1


def test_expired_turn_requires_new_preview_instead_of_repeated_save(tmp_path):
    root, owner, actions, event, session = fixture(tmp_path)
    event.update(turn=3, audio_turn=3)
    session.update(audio_turn=3)
    result = confirmation.stage_save(event, actions, session)['result']
    assert result['requires_preview']
    assert 'proposal' not in actions.state
    assert not PlannerStore(root.path, owner.owner_id).load().get_all_tasks()
