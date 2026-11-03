from datetime import date
import sqlite3
from assistant_actions import AssistantActions
from planner_storage import PlannerStore


def fixture(tmp_path):
    root=PlannerStore(tmp_path/"assistant.sqlite3")
    first=root.create_profile("Owner One")
    second=root.create_profile("Owner Two", "Pacific/Honolulu")
    p1=PlannerStore(root.path,first.owner_id).add_pet("Mochi","cat",3)
    p2=PlannerStore(root.path,second.owner_id).add_pet("Birch","dog",2)
    return root,first,second,p1,p2,AssistantActions(root.path,{})


def preview(a,owner,pet,title="Walk"):
    return a.execute("preview_task",dict(owner_id=owner.owner_id,pet_id=pet.pet_id,
        title=title,due_date="2026-12-02",time_of_day="09:00"),turn=1)


def test_new_records_and_ambiguous_search_are_dynamic(tmp_path):
    root,o1,o2,p1,p2,a=fixture(tmp_path)
    assert a.execute("find_pets",{"query":"Mochi"})["matches"][0]["owner"]==o1.name
    assert a.state.pop("route")["page"]=="Pets"
    new=root.create_profile("New owner")
    newpet=PlannerStore(root.path,new.owner_id).add_pet("Mochi","dog",5)
    result=a.execute("find_pets",{"query":"Mochi"})
    assert result["clarify"] and len(result["matches"])==2
    assert "route" not in a.state
    assert new.owner_id in [i["owner_id"] for i in a.context()["owners"]]
    assert a.execute("show_pets",{"owner_id":new.owner_id})["pets"][0]["pet_id"]==newpet.pet_id


def test_confirmed_save_is_targeted_and_idempotent_and_conversation_can_continue(tmp_path):
    root,o1,o2,p1,p2,a=fixture(tmp_path)
    result=preview(a,o2,p2)
    assert result["ok"] and result["summary"]["timezone"]==o2.timezone
    proposal=result["proposal_id"]
    assert not a.execute("save_task",{"proposal_id":proposal},"yes",turn=1)["ok"]
    assert not a.execute("save_task",{"proposal_id":proposal},"maybe",turn=2)["ok"]
    saved=a.execute("save_task",{"proposal_id":proposal},"yes",turn=2)
    assert saved["saved"]
    assert a.execute("save_task",{"proposal_id":proposal},"yes",turn=2)==saved
    assert len(PlannerStore(root.path,o2.owner_id).load().get_all_tasks())==1
    assert not PlannerStore(root.path,o1.owner_id).load().get_all_tasks()
    schedule=a.execute("show_calendar",{"owner_id":o2.owner_id,"pet_id":p2.pet_id,"day":"2026-12-02"})
    assert schedule["tasks"][0]["title"]=="Walk"
    assert a.execute("list_owners",{})["ok"]


def test_revised_preview_rejects_old_confirmation_and_other_owner_pet(tmp_path):
    root,o1,o2,p1,p2,a=fixture(tmp_path)
    old=preview(a,o1,p1)
    new=preview(a,o1,p1,"Changed")
    assert not a.execute("save_task",{"proposal_id":old["proposal_id"]},"yes",turn=2)["ok"]
    assert not a.execute("show_calendar",dict(owner_id=o1.owner_id,pet_id=p2.pet_id,day="2026-12-02"))["ok"]
    assert not a.execute("delete_task",{})["ok"]
    assert not a.execute("save_task",dict(proposal_id=new["proposal_id"],title="Injected"),"yes",turn=2)["ok"]


def test_conflicts_require_explicit_override_and_fresh_confirmation(tmp_path):
    root,o1,o2,p1,p2,a=fixture(tmp_path)
    first=preview(a,o1,p1)
    a.execute("save_task",{"proposal_id":first["proposal_id"]},"yes",turn=2)
    second=preview(a,o1,p1,"Second")
    assert second["conflicts"]
    assert not a.execute("save_task",{"proposal_id":second["proposal_id"]},"yes",turn=2)["ok"]
    assert a.execute("save_task",{"proposal_id":second["proposal_id"]},"save anyway",turn=2)["saved"]


def test_database_error_retains_proposal_without_claiming_saved(tmp_path,monkeypatch):
    root,o1,o2,p1,p2,a=fixture(tmp_path)
    result=preview(a,o1,p1)
    def fail(*args,**kwargs): raise sqlite3.OperationalError("private storage detail")
    monkeypatch.setattr(PlannerStore,"create_task",fail)
    failed=a.execute("save_task",{"proposal_id":result["proposal_id"]},"yes",turn=2)
    assert not failed["ok"] and "private" not in failed["error"]
    assert a.state["proposal"]["id"]==result["proposal_id"]


def test_later_turn_cannot_confirm_stale_preview(tmp_path):
    root,o1,o2,p1,p2,a=fixture(tmp_path)
    result=preview(a,o1,p1)
    assert not a.execute("save_task",{"proposal_id":result["proposal_id"]},"yes",turn=3)["ok"]
