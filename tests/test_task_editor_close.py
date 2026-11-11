from datetime import date,time
from uuid import uuid4
import pawpal.planning.task_editor as task_editor
from pawpal.domain.task_contract import TaskDraft


class State(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


def test_close_snapshots_latest_widget_edits_and_preserves_calendar_context(monkeypatch):
    draft=TaskDraft(1,'Old title',date(2026,11,3),time_of_day=time(9))
    prefix=draft.request_id
    state=State(task_draft=draft,editor_open=True,calendar_date=date(2026,11,3),
                voice_credential={'token':'private'},conversation=[{'role':'user','text':'keep this'}],
                composer_count=2,request_2='unfinished request')
    state.update({f'{prefix}_title':'Latest title',f'{prefix}_pet':2,f'{prefix}_date':date(2026,11,4),
                  f'{prefix}_repeat':'CUSTOM',f'{prefix}_interval':7,f'{prefix}_anytime':False,
                  f'{prefix}_time':time(14,30),f'{prefix}_location':'Window nook',
                  f'{prefix}_description':'Latest description'})
    monkeypatch.setattr(task_editor.st,'session_state',state)
    task_editor.close_editor()
    saved=state.task_draft
    assert (saved.title,saved.pet_id,saved.due_date,saved.repeat,saved.interval_days)==('Latest title',2,date(2026,11,4),'CUSTOM',7)
    assert (saved.time_of_day,saved.location,saved.description)==(time(14,30),'Window nook','Latest description')
    assert saved.request_id==draft.request_id
    assert state.pending_request=='unfinished request'
    assert state.conversation==[{'role':'user','text':'keep this'}]
    assert state.calendar_date==date(2026,11,3) and not state.editor_open
    assert 'voice_credential' not in state


def test_close_handles_anytime_and_records_only_explicit_voice_dialog_exit(monkeypatch):
    draft=TaskDraft(1,'Walk',date(2026,11,3),time_of_day=time(9))
    attempt=str(uuid4())
    state=State(task_draft=draft,editor_open=True,voice_attempt_id=attempt,
                **{f'{draft.request_id}_anytime':True})
    events=[]
    monkeypatch.setattr(task_editor.st,'session_state',state)
    monkeypatch.setattr(task_editor,'record_voice_event',lambda *args,**kwargs:events.append((args,kwargs)))
    task_editor.close_editor()
    assert state.task_draft.time_of_day is None
    assert events==[(('dialog_closed',),{'attempt_id':attempt})]
    assert 'voice_attempt_id' not in state
    task_editor.close_editor()
    assert len(events)==1


def test_empty_dialog_close_does_not_save_or_invent_a_voice_event(monkeypatch):
    state=State(editor_open=True)
    monkeypatch.setattr(task_editor.st,'session_state',state)
    monkeypatch.setattr(task_editor,'record_voice_event',lambda *args,**kwargs: (_ for _ in ()).throw(AssertionError('No voice session')))
    task_editor.close_editor()
    assert state=={'editor_open':False}
