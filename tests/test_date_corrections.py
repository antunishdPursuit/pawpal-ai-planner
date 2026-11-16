"""Calendar math and complete typed/voice correction paths; semantic tests opt in."""
from datetime import date, timezone
import json
import os
from types import SimpleNamespace
import pytest
import pawpal.planning.date_intent as dates
import pawpal.assistant.assistant_model as typed
import pawpal.assistant.assistant_ui as ui
from pawpal.domain.planner_storage import PlannerStore
from pawpal.planning.gemini_planner import PlannerError
from test_assistant_actions import fixture
from test_assistant_bridge import harness, audio


def weekday(day=6):
    return dates.DateIntent(kind='weekday', weekday=day, offset=0, anchor='upcoming', absolute='',source_turn=0)


@pytest.fixture(autouse=True)
def fixed_typed_capture_clock(monkeypatch):
    from datetime import datetime,timezone
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):
            return cls(2026,11,11,22,tzinfo=timezone.utc).astimezone(tz)
    monkeypatch.setattr(dates,'datetime',Clock)


@pytest.mark.parametrize('today,expected', [('2026-11-11','2026-11-15'), ('2026-11-15','2026-11-15'), ('2026-11-16','2026-11-22')])
def test_sunday_calendar_math(today, expected):
    assert dates.resolve_date(weekday(), today) == date.fromisoformat(expected)


@pytest.mark.parametrize('zone,expected', [('America/New_York','2026-11-12'),('Pacific/Honolulu','2026-11-12'),('Asia/Tokyo','2026-11-13')])
def test_relative_date_anchors_to_original_turn_across_midnight(monkeypatch,zone,expected):
    state={}
    dates.remember_request(state,'Create a shower tomorrow','2026-11-12T04:59:00+00:00')
    dates.remember_request(state,'9 PM','2026-11-12T05:01:00+00:00')
    intent=dates.DateIntent(kind='offset',weekday=-1,offset=1,anchor='upcoming',absolute='',source_turn=0)
    monkeypatch.setattr(dates,'classify_date',lambda *args:intent)
    dates.verify_date(state['date_requests'],expected,'2026-11-12',zone)
    with pytest.raises(PlannerError):
        from datetime import timedelta
        dates.verify_date(state['date_requests'],(date.fromisoformat(expected)+timedelta(days=1)).isoformat(),'2026-11-12',zone)


def test_new_relative_correction_uses_its_own_turn_day(monkeypatch):
    state={}
    dates.remember_request(state,'Today','2026-11-12T04:59:00+00:00')
    dates.remember_request(state,'Actually tomorrow at9PM','2026-11-12T05:01:00+00:00')
    intent=dates.DateIntent(kind='offset',weekday=-1,offset=1,anchor='upcoming',absolute='',source_turn=1)
    monkeypatch.setattr(dates,'classify_date',lambda *args:intent)
    dates.verify_date(state['date_requests'],'2026-11-13','2026-11-12','America/New_York')


@pytest.mark.parametrize('reply', ['9 PM', '21:00', 'nine in the evening'])
def test_typed_date_survives_time_followup_and_rejects_monday(tmp_path, monkeypatch, reply):
    root, owner, _, pet, _, actions = fixture(tmp_path)
    monkeypatch.setattr(actions, 'today', lambda owner: '2026-11-11')
    monkeypatch.setattr(typed, 'configuration', lambda: ('test', 'test'))
    seen = []
    def classify(requests, today, zone):
        seen.append([t['text'] for t in requests])
        return weekday()
    monkeypatch.setattr(dates, 'classify_date', classify)
    args = dict(owner_id=owner.owner_id, pet_id=pet.pet_id, title='Shower', due_date='2026-11-16', time_of_day='21:00')
    choices = iter([dict(action='reply', message='What time?', arguments_json='{}'),
                    dict(action='preview_task', arguments_json=json.dumps(args)),
                    dict(action='preview_task', arguments_json=json.dumps({**args, 'due_date':'2026-11-15'}))])
    class Client:
        def __init__(self, **kwargs): self.models = self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def generate_content(self, **kwargs):
            return SimpleNamespace(text=json.dumps(next(choices)))
    monkeypatch.setattr(typed.genai, 'Client', Client)
    assert typed.respond('Create a shower this Sunday', actions, [], 1) == 'What time?'
    result = typed.respond(reply, actions, [], 2)
    assert 'Sunday, 2026-11-15' in result
    assert seen == [['Create a shower this Sunday', reply]]
    assert actions.state['proposal']['summary']['date'] == '2026-11-15'
    assert not PlannerStore(root.path,owner.owner_id).load().get_all_tasks()
    saved = actions.execute('save_task', {'proposal_id':actions.state['proposal']['id']}, 'yes', 3)
    assert saved['saved'] and 'date_requests' not in actions.state
    assert PlannerStore(root.path,owner.owner_id).load().get_all_tasks()[0].due_date == date(2026,11,15)


def test_voice_uses_ordered_recordings_not_delayed_live_text(tmp_path, monkeypatch):
    root, owner, pet, state, events, drain = harness(tmp_path, monkeypatch)
    events.append(dict(id='prepare', kind='prepare_voice')); drain()
    spoken = iter(['Create a shower this Sunday', 'nine in the evening'])
    monkeypatch.setattr(ui, 'transcribe', lambda *args: next(spoken))
    monkeypatch.setattr('pawpal.assistant.assistant_actions.AssistantActions.today', lambda *args:'2026-11-11')
    # Capture voice turns on the same fixed clock as typed requests, so "this Sunday" stays 2026-11-15.
    monkeypatch.setattr(ui, 'datetime', dates.datetime)
    captured_at = dates.datetime.now(timezone.utc).isoformat()
    seen = []
    monkeypatch.setattr(dates, 'classify_date', lambda requests,*args: seen.append([t['text'] for t in requests]) or weekday())
    for turn in (1,2):
        events.append(dict(id=f'close-{turn}',kind='voice_turn',session_id='session',turn=turn,closed=True,audio=audio(),
                           captured_at=captured_at))
        drain()
    args = dict(owner_id=owner.owner_id,pet_id=pet.pet_id,title='Shower',due_date='2026-11-16',time_of_day='21:00')
    events.append(dict(id='wrong',kind='live_tool',session_id='session',turn=2,utterance='today (stale)',
                       call=dict(id='wrong-call',name='preview_task',args=args)))
    drain()
    assert 'proposal' not in state['assistant_state']
    assert 'Sunday' in next(r for r in state['assistant_receipts'] if r['id']=='wrong')['result']['error']
    events.append(dict(id='right',kind='live_tool',session_id='session',turn=2,utterance='Monday (stale)',
                       call=dict(id='right-call',name='preview_task',args={**args,'due_date':'2026-11-15'})))
    drain()
    assert seen == [['Create a shower this Sunday','nine in the evening']]
    assert state['assistant_state']['proposal']['summary']['weekday'] == 'Sunday'
    assert not PlannerStore(root.path,owner.owner_id).load().get_all_tasks()


def test_newer_correction_and_verification_failure_cannot_save_old_preview(tmp_path, monkeypatch):
    root, owner, _, pet, _, actions = fixture(tmp_path)
    monkeypatch.setattr(actions, 'today', lambda owner:'2026-11-11')
    args = dict(owner_id=owner.owner_id,pet_id=pet.pet_id,title='Shower',due_date='2026-11-15',time_of_day='21:00')
    dates.remember_request(actions.state, 'Sunday, not Monday')
    monkeypatch.setattr(dates, 'classify_date', lambda *args: weekday())
    old = actions.execute('preview_task',args,turn=1)['proposal_id']
    dates.remember_request(actions.state, 'Actually, Monday at 9 PM')
    monkeypatch.setattr(dates, 'classify_date', lambda *args: weekday(0))
    assert not actions.execute('preview_task',args,turn=2)['ok']
    assert not actions.execute('save_task',dict(proposal_id=old),'yes',3)['ok']
    correct = actions.execute('preview_task',{**args,'due_date':'2026-11-16'},turn=3)
    assert correct['summary']['weekday'] == 'Monday'
    def unavailable(*args): raise PlannerError('Date verifier unavailable')
    monkeypatch.setattr(dates, 'classify_date', unavailable)
    assert not actions.execute('preview_task',args,turn=4)['ok'] and 'proposal' not in actions.state


@pytest.mark.parametrize('failure', ['unclear', 'unavailable'])
@pytest.mark.parametrize('date_failure', [False, True])
def test_unclassified_typed_correction_cannot_later_approve_stale_date(tmp_path,monkeypatch,failure,date_failure):
    from pawpal.planning.confirmation_intent import ConfirmationIntent
    root,owner,_,pet,_,actions=fixture(tmp_path)
    monkeypatch.setattr(actions,'today',lambda owner:'2026-11-11')
    monkeypatch.setattr(typed,'configuration',lambda:('test','test'))
    dates.remember_request(actions.state,'Create a shower Sunday at9PM')
    monkeypatch.setattr(dates,'classify_date',lambda *args:weekday())
    args=dict(owner_id=owner.owner_id,pet_id=pet.pet_id,title='Shower',due_date='2026-11-15',time_of_day='21:00')
    actions.execute('preview_task',args,turn=1)
    def unclassified(*args):
        if failure=='unavailable':raise PlannerError('Unavailable')
        return ConfirmationIntent(decision='unclear',accepts_conflict=False)
    monkeypatch.setattr(typed,'classify_confirmation',unclassified)
    typed.respond('Actually Monday',actions,[],2)
    monkeypatch.setattr(typed,'classify_confirmation',lambda *args:ConfirmationIntent(decision='confirm',accepts_conflict=False))
    def latest_date(*args):
        if date_failure:raise PlannerError('Date verifier unavailable')
        return weekday(0)
    monkeypatch.setattr(dates,'classify_date',latest_date)
    result=typed.respond('yes',actions,[],3)
    assert ('unavailable' if date_failure else 'Monday') in result and 'proposal' not in actions.state
    assert not PlannerStore(root.path,owner.owner_id).load().get_all_tasks()


def test_completed_write_retry_returns_receipt_even_if_date_verifier_is_unavailable(tmp_path,monkeypatch):
    import sqlite3
    root,owner,_,pet,_,actions=fixture(tmp_path)
    monkeypatch.setattr(actions,'today',lambda owner:'2026-11-11')
    dates.remember_request(actions.state,'Create a shower Sunday at9PM')
    monkeypatch.setattr(dates,'classify_date',lambda *args:weekday())
    args=dict(owner_id=owner.owner_id,pet_id=pet.pet_id,title='Shower',due_date='2026-11-15',time_of_day='21:00')
    proposal=actions.execute('preview_task',args,turn=1)['proposal_id']
    create=PlannerStore.create_task
    def wrote_then_failed(*args,**kwargs):
        create(*args,**kwargs)
        raise sqlite3.OperationalError('Lost acknowledgement')
    monkeypatch.setattr(PlannerStore,'create_task',wrote_then_failed)
    assert actions.execute('save_task',dict(proposal_id=proposal),'yes',2)['retryable']
    dates.remember_request(actions.state,'Actually Monday')
    def unavailable(*args):raise PlannerError('Date verifier unavailable')
    monkeypatch.setattr(dates,'classify_date',unavailable)
    assert actions.execute('save_task',dict(proposal_id=proposal),'yes',3)['saved']
    tasks=PlannerStore(root.path,owner.owner_id).load().get_all_tasks()
    assert len(tasks)==1 and tasks[0].due_date==date(2026,11,15)


@pytest.mark.parametrize('failure', ['unclear','unavailable','unheard','invalid_audio'])
def test_unclassified_voice_correction_cannot_later_approve_stale_date(tmp_path,monkeypatch,failure):
    from test_live_confirmation import fixture as voice_fixture
    import pawpal.planning.live_confirmation as confirmation
    from pawpal.planning.confirmation_intent import ConfirmationIntent
    root,owner,actions,event,session=voice_fixture(tmp_path)
    monkeypatch.setattr(actions,'today',lambda owner:'2026-11-11')
    dates.remember_request(actions.state,'Create a shower Sunday at9PM')
    monkeypatch.setattr(dates,'classify_date',lambda *args:weekday())
    proposal=actions.execute('preview_task',dict(owner_id=owner.owner_id,pet_id=actions.owner(owner.owner_id).pets[0].pet_id,
        title='Shower',due_date='2026-11-15',time_of_day='21:00'),turn=1)['proposal_id']
    event.update(app_confirmation=True,preview_id=proposal)
    event['call']['args']['proposal_id']=proposal
    def transcript(*args):
        if failure=='unheard':raise PlannerError('Unintelligible')
        return 'Actually Monday'
    def classify(*args):
        if failure=='unavailable':raise PlannerError('Unavailable')
        return ConfirmationIntent(decision='unclear',accepts_conflict=False)
    monkeypatch.setattr(confirmation,'transcribe',transcript)
    monkeypatch.setattr(confirmation,'classify_confirmation',classify)
    original_audio=event['audio']
    if failure=='invalid_audio':event['audio']='broken'
    assert 'verification_id' not in confirmation.stage_save(event,actions,session)
    if failure in ('unclear','unavailable'):
        assert actions.state['date_requests'][-1]['text']=='Actually Monday'
    else:assert 'proposal' not in actions.state
    event.update(turn=3,audio_turn=3,audio=original_audio)
    event['call']['id']='later-yes';session['audio_turn']=3
    session['request_times'][3]=session['request_times'][2]
    monkeypatch.setattr(confirmation,'transcribe',lambda *args:'yes')
    monkeypatch.setattr(confirmation,'classify_confirmation',lambda *args:ConfirmationIntent(decision='confirm',accepts_conflict=False))
    monkeypatch.setattr(dates,'classify_date',lambda *args:weekday(0))
    verified=confirmation.stage_save(event,actions,session)
    if 'verification_id' in verified:
        assert not confirmation.commit_save({**event,**verified},actions,session)['ok']
    assert 'proposal' not in actions.state
    assert not PlannerStore(root.path,owner.owner_id).load().get_all_tasks()


def test_voice_preview_correction_is_verified_on_the_same_automatic_turn(tmp_path, monkeypatch):
    import pawpal.planning.live_confirmation as confirmation
    from pawpal.planning.confirmation_intent import ConfirmationIntent
    root, owner, pet, state, events, drain = harness(tmp_path, monkeypatch)
    events.append(dict(id='prepare',kind='prepare_voice')); drain()
    from pawpal.assistant.assistant_actions import AssistantActions
    actions = AssistantActions(root.path,state['assistant_state'])
    args = dict(owner_id=owner.owner_id,pet_id=pet.pet_id,title='Shower',due_date='2026-11-11',time_of_day='21:00')
    preview = actions.execute('preview_task',args,turn=1)['proposal_id']
    dates.remember_request(actions.state,'Create a shower today at 9 PM')
    monkeypatch.setattr(confirmation,'transcribe',lambda *args:'No, this Sunday, not Monday')
    monkeypatch.setattr(confirmation,'classify_confirmation',lambda *args:ConfirmationIntent(decision='change',accepts_conflict=False))
    monkeypatch.setattr(actions.__class__,'today',lambda *args:'2026-11-11')
    seen = []
    monkeypatch.setattr(dates,'classify_date',lambda requests,*args:seen.append([t['text'] for t in requests]) or weekday())
    events.extend([dict(id='close',kind='voice_turn',session_id='session',turn=2,closed=True,automatic=True),
        dict(id='change',kind='live_tool',session_id='session',turn=2,audio_turn=2,preview_id=preview,
             audio=audio(),app_confirmation=True,call=dict(id='change-call',name='save_task',args=dict(proposal_id=preview)))])
    drain()
    assert 'proposal' not in actions.state
    events.append(dict(id='new-preview',kind='live_tool',session_id='session',turn=2,audio_turn=2,preview_id=preview,
                       call=dict(id='new-call',name='preview_task',args={**args,'due_date':'2026-11-15'})))
    drain()
    assert seen == [['Create a shower today at 9 PM','No, this Sunday, not Monday']]
    assert actions.state['proposal']['summary']['date']=='2026-11-15'
    assert actions.state['proposal']['id'] != preview


def test_unheard_turn_drops_old_date_and_blocks_preview(tmp_path, monkeypatch):
    root, owner, pet, state, events, drain = harness(tmp_path,monkeypatch)
    events.append(dict(id='prepare',kind='prepare_voice')); drain()
    dates.remember_request(state['assistant_state'],'Create a shower Sunday')
    def unheard(*args): raise PlannerError('Unintelligible')
    monkeypatch.setattr(ui,'transcribe',unheard)
    events.append(dict(id='close',kind='voice_turn',session_id='session',turn=1,closed=True,audio=audio())); drain()
    assert len(state['assistant_state']['date_requests'])==1
    assert state['assistant_state']['date_requests'][0]['text'].startswith('[Unintelligible')
    monkeypatch.setattr(dates,'classify_date',lambda *args:dates.DateIntent(kind='unclear',weekday=-1,offset=0,anchor='upcoming',absolute='',source_turn=0))
    args=dict(owner_id=owner.owner_id,pet_id=pet.pet_id,title='Shower',due_date='2026-11-15',time_of_day='21:00')
    events.append(dict(id='preview',kind='live_tool',session_id='session',turn=1,
                       call=dict(id='preview-call',name='preview_task',args=args))); drain()
    assert 'proposal' not in state['assistant_state']


def test_saved_voice_turn_cannot_create_an_unverified_followup_preview(tmp_path, monkeypatch):
    root, owner, pet, state, events, drain = harness(tmp_path,monkeypatch)
    events.append(dict(id='prepare',kind='prepare_voice')); drain()
    session = state['assistant_state']['live_session']
    session.update(audio_turn=2,audio_closed=True,date_turns={2})
    # A completed save removes the ledger; the old verified turn must not suffice.
    state['assistant_state'].pop('date_requests',None)
    args=dict(owner_id=owner.owner_id,pet_id=pet.pet_id,title='Unexpected task',due_date='2026-11-16',time_of_day='21:00')
    events.append(dict(id='extra',kind='live_tool',session_id='session',turn=2,
                       call=dict(id='extra-call',name='preview_task',args=args))); drain()
    assert not next(r for r in state['assistant_receipts'] if r['id']=='extra')['result']['ok']
    assert 'proposal' not in state['assistant_state']


@pytest.mark.parametrize('stamp',[None,'2020-01-01T00:00:00+00:00','2026-11-11T23:59:00'])
def test_invalid_voice_capture_time_fails_closed(tmp_path,monkeypatch,stamp):
    root,owner,pet,state,events,drain=harness(tmp_path,monkeypatch)
    events.append(dict(id='prepare',kind='prepare_voice'));drain()
    monkeypatch.setattr(ui,'transcribe',lambda *args:pytest.fail('Invalid timestamp reached ASR'))
    events.append(dict(id='bad',kind='voice_turn',session_id='session',turn=1,closed=True,captured_at=stamp,audio=audio()));drain()
    assert state['assistant_state']['date_requests'][0]['text'].startswith('[Unintelligible')
    assert state['assistant_state']['live_session']['request_times'][1]==''


def test_invalid_automatic_timestamp_invalidates_preview_and_later_approval(tmp_path,monkeypatch):
    from test_live_confirmation import fixture as pending_voice
    import pawpal.planning.live_confirmation as confirmation
    root,owner,actions,event,session=pending_voice(tmp_path)
    old=actions.state['proposal']['id']
    dates.remember_request(actions.state,'Create the task today')
    event['app_confirmation']=True;session['request_times'][2]=''
    result=confirmation.stage_save(event,actions,session)
    assert result['result']['requires_preview'] and 'proposal' not in actions.state
    assert 'date_requests' not in actions.state
    session.update(audio_turn=3,request_times={3:'2026-11-12T02:00:00+00:00'})
    event.update(turn=3,audio_turn=3)
    assert 'verification_id' not in confirmation.stage_save(event,actions,session)
    assert not actions.execute('save_task',dict(proposal_id=old),'yes',4)['ok']
    assert not PlannerStore(root.path,owner.owner_id).load().get_all_tasks()


def test_open_voice_capture_timestamp_wins_over_close_timestamp(tmp_path,monkeypatch):
    from datetime import datetime,timezone,timedelta
    root,owner,pet,state,events,drain=harness(tmp_path,monkeypatch)
    events.append(dict(id='prepare',kind='prepare_voice'));drain()
    first=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    monkeypatch.setattr(ui,'transcribe',lambda *args:'Tomorrow at9PM')
    events.extend([dict(id='open',kind='voice_turn',session_id='session',turn=1,closed=False,captured_at=first),
        dict(id='close',kind='voice_turn',session_id='session',turn=1,closed=True,captured_at=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat(),audio=audio())]);drain()
    assert state['assistant_state']['date_requests'][0]['at']==datetime.fromisoformat(first).isoformat()


def test_typed_approval_refreshes_calendar_after_a_voice_preview(tmp_path,monkeypatch):
    from pawpal.assistant.assistant_actions import AssistantActions
    from pawpal.planning.confirmation_intent import ConfirmationIntent
    root,owner,pet,state,events,drain=harness(tmp_path,monkeypatch)
    drain()
    actions=AssistantActions(root.path,state['assistant_state'])
    args=dict(owner_id=owner.owner_id,pet_id=pet.pet_id,title='Sunday shower',due_date='2026-11-15',time_of_day='21:00')
    actions.execute('preview_task',args,turn=1)
    state['assistant_state']['turn']=1
    monkeypatch.setattr(ui,'respond',typed.respond)
    monkeypatch.setattr(typed,'configuration',lambda:('test','test'))
    monkeypatch.setattr(typed,'classify_confirmation',lambda *args:ConfirmationIntent(decision='confirm',accepts_conflict=False))
    events.append(dict(id='approve',kind='chat',text='I approve'));drain()
    assert state['assistant_refresh'] is True
    assert len(PlannerStore(root.path,owner.owner_id).load().get_all_tasks())==1
    assert 'proposal' not in actions.state


CASES = [
    (['Today. No, this Sunday.'], '2026-11-15'),
    (['This Sunday, not this Monday.'], '2026-11-15'),
    (['Not Sunday. Make it Monday.'], '2026-11-16'),
    (['Create a shower Sunday', '21:00'], '2026-11-15'),
    (['Create a shower Sunday', 'nine in the evening'], '2026-11-15'),
    (['This Sunday', 'Actually Monday at 9 PM'], '2026-11-16'),
    (['This Sunday', 'Actually tomorrow', '9 PM'], '2026-11-12'),
    (['This Sunday', 'Cancel it', 'Create a different task tomorrow at 9 PM'], '2026-11-12'),
    (['This Sunday', 'Create a different task at 9 PM'], None),
    (['Create a shower Sunday', 'Where is the calendar?', '9 PM'], '2026-11-15'),
    (['Create a shower Sunday', 'Is Monday free?', '9 PM'], '2026-11-15'),
    (['Shower on November 15, 2026 at 9 PM'], '2026-11-15'),
    (['Shower on Sunday November 16, 2026'], None),
    (['[Unintelligible user turn; require the complete task date to be repeated.]','9 PM'], None),
    (['Create shower next Sunday'], None),
]


@pytest.mark.skipif(os.getenv('PAWPAL_RUN_DATE_INTENT') != '1', reason='Opt-in real provider; fictional text only')
@pytest.mark.parametrize('requests,expected', CASES)
def test_real_provider_date_corrections(requests, expected):
    intent = dates.classify_date(requests, '2026-11-11', 'America/New_York')
    if expected is None:
        with pytest.raises(PlannerError): dates.resolve_date(intent,'2026-11-11')
    else:
        assert dates.resolve_date(intent,'2026-11-11').isoformat() == expected


@pytest.mark.skipif(os.getenv('PAWPAL_RUN_DATE_INTENT') != '1', reason='Opt-in real provider; fictional text only')
@pytest.mark.parametrize('last,expected,source', [('9 PM','2026-11-12',0),('Actually tomorrow at9PM','2026-11-13',1)])
def test_real_provider_selects_original_or_corrected_date_turn(last,expected,source):
    requests=[dict(text='Create a shower tomorrow',local_date='2026-11-11'),dict(text=last,local_date='2026-11-12')]
    intent=dates.classify_date(requests,'2026-11-12','America/New_York')
    assert intent.source_turn==source
    assert dates.resolve_date(intent,requests[source]['local_date']).isoformat()==expected
