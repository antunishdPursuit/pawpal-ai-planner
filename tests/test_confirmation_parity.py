"""Application routing checks; real language interpretation has a separate opt-in test."""
import json
import sqlite3
from types import SimpleNamespace
import pytest
import pawpal.assistant.assistant_model as typed
import pawpal.planning.live_confirmation as voice
from pawpal.planning.confirmation_intent import ConfirmationIntent
from pawpal.planning.gemini_planner import PlannerError
from pawpal.domain.planner_storage import PlannerStore
from test_live_confirmation import fixture


def prepare(tmp_path, monkeypatch, decision='confirm', field='other', accepts=False):
    root, owner, actions, event, session = fixture(tmp_path)
    intent = ConfirmationIntent(decision=decision, accepts_conflict=accepts, question_field=field)
    monkeypatch.setattr(typed, 'configuration', lambda: ('test-only', 'test-model'))
    monkeypatch.setattr(typed, 'classify_confirmation', lambda *args: intent)
    monkeypatch.setattr(voice, 'classify_confirmation', lambda *args: intent)
    monkeypatch.setattr(voice, 'transcribe', lambda *args: 'I agree')
    event['app_confirmation'] = True
    return root, owner, actions, event, session


def count(root, owner):
    return len(PlannerStore(root.path, owner.owner_id).load().get_all_tasks())


@pytest.mark.parametrize('reply', ['I agree', 'I approve', 'Yes, you should.', 'Go ahead', 'That works for me'])
def test_typed_semantic_approval_saves_without_a_conversational_tool(tmp_path, monkeypatch, reply):
    root, owner, actions, _, _ = prepare(tmp_path, monkeypatch)
    assert typed.respond(reply, actions, [], 2).startswith('Saved ')
    assert count(root, owner) == 1 and 'proposal' not in actions.state


@pytest.mark.parametrize('decision', ['cancel', 'unclear', 'question'])
def test_voice_and_text_non_approvals_preserve_or_clear_the_same_preview(tmp_path, monkeypatch, decision):
    root, owner, actions, event, session = prepare(tmp_path, monkeypatch, decision, 'time')
    text = typed.respond('What time did you say?', actions, [], 2)
    assert count(root, owner) == 0
    assert ('proposal' in actions.state) == (decision != 'cancel')
    root2, owner2, a2, event2, session2 = prepare(tmp_path/'voice', monkeypatch, decision, 'time')
    result = voice.stage_save(event2, a2, session2)['result']
    assert result['decision'] == decision and count(root2, owner2) == 0
    assert ('proposal' in a2.state) == (decision != 'cancel')
    if decision == 'question':
        assert text == result['answer'] and '10:00 AM' in text


def test_question_then_later_approval_keeps_one_preview_and_one_save(tmp_path, monkeypatch):
    root, owner, actions, _, _ = prepare(tmp_path, monkeypatch, 'question', 'time')
    preview = actions.state['proposal']['id']
    assert '10:00 AM' in typed.respond('What time?', actions, [], 2)
    assert actions.state['proposal']['id'] == preview
    monkeypatch.setattr(typed, 'classify_confirmation', lambda *args:
        ConfirmationIntent(decision='confirm', accepts_conflict=False))
    assert typed.respond('That works for me', actions, [], 5).startswith('Saved ')
    assert count(root, owner) == 1


def model_choice(monkeypatch, choice, check=lambda payload: None):
    class Client:
        def __init__(self, **kwargs): self.models = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def generate_content(self, **kwargs):
            check(json.loads(kwargs['contents']))
            result = dict(choice)
            if 'correction_context' in kwargs['config'].response_json_schema['properties']:
                result.setdefault('correction_context', 'retain')
            return SimpleNamespace(text=json.dumps(result))
    monkeypatch.setattr(typed.genai, 'Client', Client)


def test_change_uses_previous_details_but_requires_new_preview(tmp_path, monkeypatch):
    root, owner, actions, event, _ = prepare(tmp_path, monkeypatch, 'change')
    previous = actions.state['proposal']['id']
    draft = actions.state['proposal']['draft']
    args = dict(owner_id=owner.owner_id, pet_id=draft.pet_id, title='Walk', due_date='2026-12-03', time_of_day='09:00')
    def check(payload):
        assert payload['previous_proposal']['time'] == '10:00' and payload['latest_proposal'] is None
    model_choice(monkeypatch, dict(action='preview_task', arguments_json=json.dumps(args)), check)
    assert 'Shall I save' in typed.respond('Yes, but at 9 AM instead', actions, [], 2)
    assert actions.state['proposal']['id'] != previous and count(root, owner) == 0


def test_correction_context_survives_followup_and_provider_failure(tmp_path, monkeypatch):
    root, owner, actions, _, _ = prepare(tmp_path, monkeypatch, 'change')
    draft_pet = actions.state['proposal']['draft'].pet_id
    original = dict(actions.state['proposal']['summary'], location='West gate', description='Bring water')
    actions.state['proposal']['summary'] = original
    model_choice(monkeypatch, dict(action='reply', message='AM or PM?', arguments_json='{}'))
    assert typed.respond('Make it 9 instead', actions, [], 2) == 'AM or PM?'
    assert 'proposal' not in actions.state and count(root, owner) == 0
    def unavailable(payload):
        assert payload['previous_proposal'] == original
        raise RuntimeError('provider unavailable')
    model_choice(monkeypatch, {}, unavailable)
    with pytest.raises(PlannerError):
        typed.respond('PM', actions, [], 3)
    assert actions.state['correction_context'] == original
    args = dict(owner_id=owner.owner_id, pet_id=draft_pet, title='Walk', due_date='2026-12-03', time_of_day='21:00', location='West gate', description='Bring water')
    def retained(payload):
        assert payload['previous_proposal'] == original and payload['latest_proposal'] is None
    model_choice(monkeypatch, dict(action='preview_task', arguments_json=json.dumps(args)), retained)
    assert 'Shall I save' in typed.respond('PM', actions, [], 4)
    assert 'correction_context' not in actions.state and count(root, owner) == 0
    assert actions.state['proposal']['summary']['location'] == 'West gate'


def test_repeat_details_includes_optional_fields_and_conflict_warning(tmp_path, monkeypatch):
    root, owner, actions, _, _ = prepare(tmp_path, monkeypatch, 'question', 'details')
    actions.state['proposal']['summary'].update(location='West gate', description='Bring water', repeat='CUSTOM', interval_days=3)
    actions.state['proposal']['conflicts'] = ['Existing walk at 10 AM']
    reply = typed.respond('Repeat all the details', actions, [], 2)
    assert all(text in reply for text in ['West gate', 'Bring water', 'Every 3 days', 'Existing walk at 10 AM', 'Explicit acceptance'])
    assert 'proposal' in actions.state and count(root, owner) == 0


@pytest.mark.parametrize('reply', ['Cancel that', 'How many pets are there?', 'Create a different task'])
def test_abandoned_correction_is_not_supplied_to_later_requests(tmp_path, monkeypatch, reply):
    root, owner, actions, _, _ = prepare(tmp_path, monkeypatch, 'change')
    model_choice(monkeypatch, dict(action='reply', message='AM or PM?', arguments_json='{}'))
    typed.respond('Change it to 9', actions, [], 2)
    model_choice(monkeypatch, dict(action='reply', message='Okay', arguments_json='{}', correction_context='discard'))
    typed.respond(reply, actions, [], 3)
    assert 'correction_context' not in actions.state and 'proposal' not in actions.state
    def clean(payload):
        assert payload['previous_proposal'] is None
    model_choice(monkeypatch, dict(action='reply', message='Ready', arguments_json='{}'), clean)
    typed.respond('What next?', actions, [], 4)
    assert count(root, owner) == 0


@pytest.mark.parametrize('action', ['save_task', 'preview_task'])
def test_question_cannot_be_upgraded_to_a_write_by_the_model(tmp_path, monkeypatch, action):
    root, owner, actions, event, _ = prepare(tmp_path, monkeypatch, 'question')
    model_choice(monkeypatch, dict(action=action, arguments_json=json.dumps(event['call']['args'])))
    with pytest.raises(PlannerError, match='unsupported action'):
        typed.respond('Should I save it?', actions, [], 2)
    assert count(root, owner) == 0 and 'proposal' in actions.state


@pytest.mark.parametrize('accepts', [False, True])
def test_typed_conflict_requires_explicit_semantic_acceptance(tmp_path, monkeypatch, accepts):
    root, owner, actions, _, _ = prepare(tmp_path, monkeypatch, accepts=accepts)
    draft = actions.state['proposal']['draft']
    PlannerStore(root.path, owner.owner_id).create_task(draft)
    actions.execute('preview_task', dict(owner_id=owner.owner_id, pet_id=draft.pet_id,
        title='Second task', due_date='2026-12-03', time_of_day='10:00'), turn=1)
    reply = typed.respond('I accept the overlap' if accepts else 'I agree', actions, [], 2)
    assert count(root, owner) == (2 if accepts else 1)
    assert ('Saved ' in reply) == accepts


@pytest.mark.parametrize('path', ['typed', 'voice'])
def test_preview_replacement_during_classification_cannot_grant_approval(tmp_path, monkeypatch, path):
    root, owner, actions, event, session = prepare(tmp_path, monkeypatch)
    def replace(*args):
        actions.state['proposal']['id'] = 'changed-preview'
        return ConfirmationIntent(decision='confirm', accepts_conflict=False)
    monkeypatch.setattr(typed if path == 'typed' else voice, 'classify_confirmation', replace)
    result = typed.respond('I agree', actions, [], 2) if path == 'typed' else voice.stage_save(event, actions, session)
    assert 'changed' in str(result).lower() and count(root, owner) == 0


def test_typed_storage_retry_is_bounded_without_new_consent(tmp_path, monkeypatch):
    root, owner, actions, _, _ = prepare(tmp_path, monkeypatch)
    original, attempts = PlannerStore.create_task, []
    def transient(store, *args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1: raise sqlite3.OperationalError('busy')
        return original(store, *args, **kwargs)
    monkeypatch.setattr(PlannerStore, 'create_task', transient)
    assert typed.respond('I approve', actions, [], 2).startswith('Saved ')
    assert len(attempts) == 2 and count(root, owner) == 1


def test_live_question_cannot_replace_the_pending_preview(tmp_path, monkeypatch):
    from test_assistant_bridge import harness, audio
    from pawpal.assistant.assistant_actions import AssistantActions
    root, owner, pet, state, events, drain = harness(tmp_path, monkeypatch)
    events.append({'id': 'prepare', 'kind': 'prepare_voice'}); drain()
    actions = AssistantActions(root.path, state['assistant_state'])
    args = dict(owner_id=owner.owner_id, pet_id=pet.pet_id, title='Walk', due_date='2026-12-03', time_of_day='10:00')
    preview = actions.execute('preview_task', args, turn=1)['proposal_id']
    monkeypatch.setattr(voice, 'classify_confirmation', lambda *args:
        ConfirmationIntent(decision='question', accepts_conflict=False, question_field='time'))
    events.extend([{'id': 'close', 'kind': 'voice_turn', 'session_id': 'session', 'turn': 2, 'closed': True},
        {'id': 'question', 'kind': 'live_tool', 'session_id': 'session', 'turn': 2, 'audio_turn': 2,
         'preview_id': preview, 'audio': audio(), 'app_confirmation': True,
         'call': {'id': 'question-call', 'name': 'save_task', 'args': {'proposal_id': preview}}}])
    drain()
    events.append({'id': 'replacement', 'kind': 'live_tool', 'session_id': 'session', 'turn': 2,
        'audio_turn': 2, 'preview_id': preview,
        'call': {'id': 'replacement-call', 'name': 'preview_task', 'args': {**args, 'time_of_day': '11:00'}}})
    drain()
    assert state['assistant_state']['proposal']['id'] == preview and count(root, owner) == 0
    assert not next(r for r in state['assistant_receipts'] if r['id'] == 'replacement')['result']['ok']
