from types import SimpleNamespace
import sqlite3
import pytest
import live_confirmation as confirmation
from confirmation_intent import ConfirmationIntent
from gemini_planner import PlannerError
from planner_storage import PlannerStore
from test_live_confirmation import fixture


def automatic_fixture(tmp_path, monkeypatch, decision='confirm', conflict=False):
    root, owner, actions, event, session = fixture(tmp_path)
    event['app_confirmation'] = True
    monkeypatch.setattr(confirmation, 'transcribe', lambda *args: 'Yes, you should.')
    monkeypatch.setattr(confirmation, 'classify_confirmation', lambda *args:
        ConfirmationIntent(decision=decision, accepts_conflict=conflict))
    return root, owner, actions, event, session


def test_semantic_approval_bypasses_phrase_match_and_saves_once(tmp_path, monkeypatch):
    root, owner, actions, event, session = automatic_fixture(tmp_path, monkeypatch)
    verified = confirmation.stage_save(event, actions, session)
    assert not PlannerStore(root.path, owner.owner_id).load().get_all_tasks()
    result = confirmation.commit_save({**event, **verified}, actions, session)
    assert result['saved'] and result['transcript'] == 'Yes, you should.'
    assert len(PlannerStore(root.path, owner.owner_id).load().get_all_tasks()) == 1
    assert not confirmation.commit_save({**event, **verified}, actions, session)['ok']


@pytest.mark.parametrize('decision', ['change', 'cancel', 'unclear'])
def test_non_approval_never_saves(tmp_path, monkeypatch, decision):
    root, owner, actions, event, session = automatic_fixture(tmp_path, monkeypatch, decision)
    result = confirmation.stage_save(event, actions, session)['result']
    assert result['decision'] == decision
    assert ('proposal' in actions.state) == (decision == 'unclear')
    assert not PlannerStore(root.path, owner.owner_id).load().get_all_tasks()


def test_unclear_reply_can_be_confirmed_on_later_turn_without_new_preview(tmp_path, monkeypatch):
    root, owner, actions, event, session = automatic_fixture(tmp_path, monkeypatch, 'unclear')
    proposal_id = actions.state['proposal']['id']
    assert confirmation.stage_save(event, actions, session)['result']['decision'] == 'unclear'
    event.update(turn=3, audio_turn=3)
    event['call']['id'] = 'retry'
    session.update(audio_turn=3)
    monkeypatch.setattr(confirmation, 'classify_confirmation', lambda *args:
        ConfirmationIntent(decision='confirm', accepts_conflict=False))
    verified = confirmation.stage_save(event, actions, session)
    assert actions.state['proposal']['id'] == proposal_id
    assert confirmation.commit_save({**event, **verified}, actions, session)['saved']


def test_provider_failure_keeps_preview_and_fails_closed(tmp_path, monkeypatch):
    root, owner, actions, event, session = automatic_fixture(tmp_path, monkeypatch)
    def fail(*args):
        raise PlannerError('Unavailable')
    monkeypatch.setattr(confirmation, 'classify_confirmation', fail)
    assert confirmation.stage_save(event, actions, session)['result']['decision'] == 'unclear'
    assert actions.state['proposal']['id'] == event['preview_id']
    assert not actions.state.get('live_verifications')


def test_transient_storage_error_reuses_approval_without_duplicate(tmp_path, monkeypatch):
    root, owner, actions, event, session = automatic_fixture(tmp_path, monkeypatch)
    verified = confirmation.stage_save(event, actions, session)
    original = PlannerStore.create_task
    attempts = []
    def transient(store, *args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise sqlite3.OperationalError('busy')
        return original(store, *args, **kwargs)
    monkeypatch.setattr(PlannerStore, 'create_task', transient)
    assert confirmation.commit_save({**event, **verified}, actions, session)['saved']
    assert len(attempts) == 2
    assert len(PlannerStore(root.path, owner.owner_id).load().get_all_tasks()) == 1


def test_persistent_storage_error_is_bounded_and_preserves_preview(tmp_path, monkeypatch):
    root, owner, actions, event, session = automatic_fixture(tmp_path, monkeypatch)
    verified = confirmation.stage_save(event, actions, session)
    attempts = []
    def fail(*args, **kwargs):
        attempts.append(1)
        raise sqlite3.OperationalError('busy')
    monkeypatch.setattr(PlannerStore, 'create_task', fail)
    result = confirmation.commit_save({**event, **verified}, actions, session)
    assert not result['ok'] and result['retryable']
    assert len(attempts) == 2
    assert actions.state['proposal']['id'] == event['preview_id']


@pytest.mark.parametrize('accepts', [False, True])
def test_conflict_needs_semantic_explicit_acceptance(tmp_path, monkeypatch, accepts):
    root, owner, actions, event, session = automatic_fixture(tmp_path, monkeypatch, conflict=accepts)
    # Seed an actual conflicting task, then prepare another preview.
    draft = actions.state['proposal']['draft']
    PlannerStore(root.path, owner.owner_id).create_task(draft)
    fresh = actions.execute('preview_task', dict(owner_id=owner.owner_id, pet_id=draft.pet_id,
        title='Another walk', due_date=draft.due_date.isoformat(), time_of_day='10:00'), turn=1)
    event['preview_id'] = fresh['proposal_id']
    event['call']['args']['proposal_id'] = fresh['proposal_id']
    result = confirmation.stage_save(event, actions, session)
    if accepts:
        assert confirmation.commit_save({**event, **result}, actions, session)['saved']
    else:
        assert result['result']['decision'] == 'unclear'
        assert len(PlannerStore(root.path, owner.owner_id).load().get_all_tasks()) == 1


def test_structured_classifier_validates_provider_output(monkeypatch):
    import confirmation_intent as module
    monkeypatch.setattr(module, 'configuration', lambda: ('test-only', 'test-model'))
    output = ['{"decision":"confirm","accepts_conflict":false}']
    class Client:
        def __init__(self, **kwargs):
            self.models = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def generate_content(self, **kwargs):
            assert kwargs['config'].response_json_schema['properties']['decision']['enum']
            return SimpleNamespace(text=output[0])
    monkeypatch.setattr(module.genai, 'Client', Client)
    assert module.classify_confirmation('Yes, you should.', {'pet': 'Mochi'}, []).decision == 'confirm'
    for malformed in ['{"decision":"save","accepts_conflict":false}', '{}', 'not JSON',
                      '{"decision":"confirm","accepts_conflict":"false"}']:
        output[0] = malformed
        with pytest.raises(PlannerError):
            module.classify_confirmation('Yes', {}, [])
