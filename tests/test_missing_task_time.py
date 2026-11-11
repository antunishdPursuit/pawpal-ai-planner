import json
from types import SimpleNamespace
from pawpal.assistant.assistant_actions import AssistantActions
from pawpal.domain.planner_storage import PlannerStore
from pawpal.planning.gemini_planner import decode_proposal, MISSING_TIME_MESSAGE
import pawpal.assistant.assistant_model as assistant_model


def fixture(tmp_path):
    root=PlannerStore(tmp_path/"time.sqlite3")
    owner=root.create_profile("Time owner")
    pet=PlannerStore(root.path,owner.owner_id).add_pet("Time pet","cat",3)
    actions=AssistantActions(root.path,{})
    args=dict(owner_id=owner.owner_id,pet_id=pet.pet_id,title="Walk",due_date="2026-12-03",time_of_day=None)
    return root,owner,pet,actions,args


def test_omitted_time_asks_and_creates_no_preview_or_task(tmp_path):
    root,owner,pet,actions,args=fixture(tmp_path)
    result=actions.execute("preview_task",args,turn=1)
    assert not result["ok"] and result["needs_time"] and result["error"]==MISSING_TIME_MESSAGE
    assert "proposal" not in actions.state
    assert not PlannerStore(root.path,owner.owner_id).load().get_all_tasks()
    completed=actions.execute("preview_task",{**args,"time_of_day":"10:30"},turn=2)
    assert completed["ok"] and completed["summary"]["time"]=="10:30"


def test_explicit_anytime_is_supported_but_not_inferred(tmp_path):
    root,owner,pet,actions,args=fixture(tmp_path)
    assert actions.execute("preview_task",{**args,"anytime_confirmed":True},turn=1)["summary"]["time"]=="Anytime"
    assert not actions.execute("preview_task",{**args,"anytime_confirmed":False},turn=2)["ok"]
    assert "proposal" not in actions.state


def test_task_dialog_ai_also_clarifies_missing_time(tmp_path):
    root,owner,pet,actions,args=fixture(tmp_path)
    owner=PlannerStore(root.path,owner.owner_id).load()
    proposal=dict(kind="task",message="A walk",pet_id=pet.pet_id,title="Walk",due_date="2026-12-03",
                  time_of_day=None,repeat="NONE",interval_days=1,description="",location="")
    missing=decode_proposal(json.dumps(proposal),owner)
    assert missing.kind=="clarify" and missing.message==MISSING_TIME_MESSAGE and missing.draft is None
    explicit=decode_proposal(json.dumps({**proposal,"anytime_confirmed":True}),owner)
    assert explicit.kind=="task" and explicit.draft.time_of_day is None


def fake_model(monkeypatch,args):
    choice=SimpleNamespace(text=json.dumps(dict(action="preview_task",message="",arguments_json=json.dumps(args))))
    class Client:
        def __init__(self,**kwargs): self.models=SimpleNamespace(generate_content=lambda **kwargs:choice)
        def __enter__(self): return self
        def __exit__(self,*args): pass
    monkeypatch.setattr(assistant_model,"configuration",lambda:("test-only","test-model"))
    monkeypatch.setattr(assistant_model.genai,"Client",Client)


def test_typed_assistant_directly_asks_missing_time(tmp_path,monkeypatch):
    root,owner,pet,actions,args=fixture(tmp_path)
    fake_model(monkeypatch,args)
    assert assistant_model.respond("Create a walk tomorrow",actions,[],1)==MISSING_TIME_MESSAGE


def test_typed_confirmation_explicitly_states_the_time(tmp_path,monkeypatch):
    root,owner,pet,actions,args=fixture(tmp_path)
    fake_model(monkeypatch,{**args,"time_of_day":"10:30"})
    reply=assistant_model.respond("At10:30AM",actions,[],1)
    assert "10:30 AM" in reply and "America/New_York" in reply and "Shall I save it?" in reply
