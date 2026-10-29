from datetime import date
import task_editor as editor
from task_contract import TaskDraft


class State(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


def setup(monkeypatch):
    state=State(editor_day=date(2026,11,3),editor_pet_id=1,entry_mode='Conversation')
    monkeypatch.setattr(editor.st,'session_state',state)
    editor.activate_entry_mode('Conversation')
    return state


def switch(state,mode):
    state.entry_mode=mode
    editor.entry_mode_changed()


def test_manual_draft_does_not_leak_into_conversation_and_edits_survive(monkeypatch):
    state=setup(monkeypatch)
    state.request_0='unfinished conversation'
    switch(state,'Manual')
    manual=TaskDraft(1,'Old manual title',state.editor_day)
    state.task_draft=manual
    state[manual.request_id+'_title']='Latest manual title'
    switch(state,'Conversation')
    assert 'task_draft' not in state
    assert state.manual_draft.title=='Latest manual title'
    assert state.pending_request=='unfinished conversation'
    assert editor.has_unsaved_draft()
    switch(state,'Manual')
    assert state.task_draft.request_id==manual.request_id
    assert state.task_draft.title=='Latest manual title'


def test_generated_preview_and_manual_draft_remain_independent(monkeypatch):
    state=setup(monkeypatch)
    ai=TaskDraft(1,'Generated walk',state.editor_day)
    state.task_draft=ai  # Same producer contract used by typed and live proposals.
    switch(state,'Manual')
    assert 'task_draft' not in state
    manual=TaskDraft(1,'Manual grooming',state.editor_day)
    state.task_draft=manual
    switch(state,'Conversation')
    assert state.task_draft==ai and state.manual_draft==manual
    switch(state,'Manual')
    assert state.task_draft==manual and state.conversation_draft==ai


def test_reopening_defaults_to_conversation_without_exposing_closed_manual_draft(monkeypatch):
    state=setup(monkeypatch)
    switch(state,'Manual')
    state.task_draft=TaskDraft(1,'Retained manual task',state.editor_day)
    editor.close_editor()
    editor.open_editor(1,state.editor_day,'Conversation')
    assert 'task_draft' not in state and state.manual_draft.title=='Retained manual task'
    switch(state,'Manual')
    assert state.task_draft.title=='Retained manual task'


def test_reset_stays_in_current_mode_and_owner_cleanup_clears_all_drafts(monkeypatch):
    state=setup(monkeypatch)
    state.task_draft=TaskDraft(1,'Generated',state.editor_day)
    state.manual_draft=TaskDraft(1,'Manual',state.editor_day)
    state.conversation=[{'role':'user','text':'private'}]
    editor.start_over()
    assert state.entry_mode=='Conversation' and state.editor_open
    assert state.editor_day==date(2026,11,3) and state.editor_pet_id==1
    assert all(key not in state for key in ('task_draft','manual_draft','conversation_draft','conversation'))
    state.manual_draft=TaskDraft(1,'Unsaved',state.editor_day)
    editor.cancel_editor()
    assert not editor.has_unsaved_draft()


def test_previous_ai_preview_can_be_recovered_without_loading_manual_draft(monkeypatch):
    state=setup(monkeypatch)
    state.task_draft=TaskDraft(1,'AI preview',state.editor_day)
    state.manual_draft=TaskDraft(1,'Manual task',state.editor_day)
    state.preview_blocked=True
    state.planner_error='Failed request'
    editor.restore_previous_preview()
    assert not state.get('preview_blocked') and 'planner_error' not in state
    assert state.task_draft.title=='AI preview' and state.manual_draft.title=='Manual task'


def test_switching_mode_releases_credentials_and_records_an_explicit_exit(monkeypatch):
    state=setup(monkeypatch)
    state.voice_credential={'token':'private'}
    state.voice_attempt_id='anonymous-test-attempt'
    events=[]
    monkeypatch.setattr(editor,'record_voice_event',lambda *args,**kwargs: events.append((args,kwargs)))
    switch(state,'Manual')
    assert 'voice_credential' not in state and 'voice_attempt_id' not in state
    assert events==[(('entry_mode_changed',),{'attempt_id':'anonymous-test-attempt'})]


def test_unclassified_older_manual_draft_never_appears_as_an_ai_preview(monkeypatch):
    legacy=TaskDraft(1,'Older manual work',date(2026,11,3))
    state=State(task_draft=legacy,entry_mode='Conversation')
    monkeypatch.setattr(editor.st,'session_state',state)
    editor.activate_entry_mode('Conversation')
    assert 'task_draft' not in state and state.manual_draft==legacy
    switch(state,'Manual')
    assert state.task_draft==legacy
