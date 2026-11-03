"""Bounded demo-wide actions shared by typed and live assistant transports."""
from datetime import date, time
import sqlite3
from uuid import uuid4

from calendar_view import entries_for_day, draft_conflicts
from planner_clock import local_today, using_timezone
from planner_storage import PlannerStore
from task_contract import TaskDraft
from voice_completion import confirmed
from gemini_planner import _ambiguous_time, MISSING_TIME_MESSAGE


def field_schema(kind, description=""):
    return {"type": kind, "description": description}


TASK_FIELDS = {
    "owner_id": field_schema("integer", "The target pet owner ID"),
    "pet_id": field_schema("integer", "The registered pet ID"),
    "title": field_schema("string"), "due_date": field_schema("string", "YYYY-MM-DD in owner's timezone"),
    "time_of_day": {"type": ["string", "null"], "description": "HH:MM, 24 hour. Ask if missing; null only for an explicit Anytime choice."},
    "anytime_confirmed": {"type": "boolean", "description": "True only if the user explicitly chose Anytime/no specific time. Missing time is not consent."},
    "repeat": {"type": "string", "enum": ["NONE", "DAILY", "WEEKLY", "CUSTOM"]},
    "interval_days": field_schema("integer"), "description": field_schema("string"), "location": field_schema("string"),
}


def tool(name, description, properties, required=()):
    return {"name": name, "description": description, "behavior": "BLOCKING",
            "parameters_json_schema": {"type": "object", "properties": properties,
                                       "required": list(required), "additionalProperties": False}}


TOOLS = [
    tool("get_context", "Refresh owner identities, focus, local today and timezones before relative dates. Does not navigate.", {}),
    tool("list_owners", "List current local demo owners and open owner selection.", {}),
    tool("find_pets", "Find pets and their owners by name. A unique match opens its owner's Pets screen; ask about multiple matches.",
         {"query": field_schema("string")}, ["query"]),
    tool("find_tasks", "Find saved tasks and their repeat schedules by title, optionally within an owner/pet. A unique match opens its calendar.",
         {"query": field_schema("string"), "owner_id": field_schema("integer"), "pet_id": field_schema("integer")}, ["query"]),
    tool("show_pets", "Show a selected owner's pets and open their Pets screen.",
         {"owner_id": field_schema("integer")}, ["owner_id"]),
    tool("show_calendar", "Read the actual daily calendar including repeating occurrences and open it. Omit pet_id for all pets.",
         {"owner_id": field_schema("integer"), "pet_id": field_schema("integer"),
          "day": field_schema("string", "YYYY-MM-DD, owner local date")}, ["owner_id", "day"]),
    tool("preview_task", "Validate a proposed task and show its full details for confirmation. Never saves. Any changes need a new preview.",
         TASK_FIELDS, ["owner_id", "pet_id", "title", "due_date", "time_of_day"]),
    tool("save_task", "Save ONLY the latest server-held proposal after explicit user confirmation of its displayed details. No modified fields allowed.",
         {"proposal_id": field_schema("string")}, ["proposal_id"]),
]


class AssistantActions:
    def __init__(self, path, state):
        self.root = PlannerStore(path)
        self.state = state
        self.state.setdefault("context", {})
        self.state.setdefault("receipts", {})

    def owners(self):
        return self.root.load_community()

    def owner(self, owner_id):
        if type(owner_id) is not int:
            raise ValueError("Choose a pet owner first.")
        owner = PlannerStore(self.root.path, owner_id).load()
        if owner is None:
            raise ValueError("That pet owner no longer exists. Search again.")
        return owner

    def context(self):
        # Refresh identities and dates so newly added records need no code changes.
        return {"focus": self.state["context"], "owners": [
            {"owner_id": o.owner_id, "name": o.name, "timezone": o.timezone,
             "today": self.today(o), "pets": [{"pet_id": p.pet_id, "name": p.name} for p in o.pets]}
            for o in self.owners()]}

    @staticmethod
    def today(owner):
        with using_timezone(owner.timezone):
            return local_today().isoformat()

    def route(self, owner, page, pet_id=None, day=None):
        route = {"owner_id": owner.owner_id, "page": page, "pet_id": pet_id, "day": day}
        self.state["context"] = route
        self.state["route"] = route

    def execute(self, name, args, utterance="", turn=0):
        try:
            if not isinstance(args, dict):
                raise ValueError("Invalid action details.")
            spec = next((t for t in TOOLS if t["name"] == name), None)
            if not spec or set(args) - set(spec["parameters_json_schema"]["properties"]):
                raise ValueError("That action is not supported.")
            if any(key not in args for key in spec["parameters_json_schema"]["required"]):
                raise ValueError("Some action details are missing.")
            for key, value in args.items():
                schema = spec["parameters_json_schema"]["properties"][key]
                kinds = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
                valid = (("null" in kinds and value is None) or ("integer" in kinds and type(value) is int)
                         or ("string" in kinds and isinstance(value, str)) or ("boolean" in kinds and type(value) is bool))
                if not valid or ("enum" in schema and value not in schema["enum"]):
                    raise ValueError("Invalid action details. Please clarify your request.")
            result = self._execute(name, args, utterance, turn)
            try:
                result["current_context"] = self.context()
            except (sqlite3.Error, OSError):
                result["context_refresh_failed"] = True
            return result
        except (ValueError, TypeError, KeyError) as error:
            return {"ok": False, "error": str(error)}
        except (sqlite3.Error, OSError):
            if name == "save_task" and self.state.get("proposal"):
                self.state["proposal"]["turn"] = turn
            return {"ok": False, "error": "Local storage is unavailable. Nothing new was confirmed; try again."}

    def _execute(self, name, args, utterance, turn):
        if name == "get_context":
            return {"ok": True, "context": self.context()}
        if name == "list_owners":
            self.state["route"] = {"page": "User"}
            return {"ok": True, "owners": [{"owner_id": p.owner_id, "name": p.name, "pets": p.pet_count}
                                           for p in self.root.list_profiles()]}
        if name == "find_pets":
            query = args["query"].strip().casefold()
            if not query or len(query) > 80:
                raise ValueError("Give a pet name to search for.")
            matches = [{"owner_id": o.owner_id, "owner": o.name, "pet_id": p.pet_id,
                        "pet": p.name, "species": p.species}
                       for o in self.owners() for p in o.pets if query in p.name.casefold()]
            if len(matches) == 1:
                m = matches[0]
                self.route(self.owner(m["owner_id"]), "Pets", m["pet_id"])
            return {"ok": True, "matches": matches, "clarify": len(matches) > 1}
        if name == "find_tasks":
            query = args["query"].strip().casefold()
            if not query or len(query) > 120:
                raise ValueError("Give a task title to search for.")
            matches = []
            for owner in self.owners():
                if args.get("owner_id") is not None and owner.owner_id != args["owner_id"]:
                    continue
                with using_timezone(owner.timezone):
                    for task in owner.get_all_tasks():
                        if query not in task.title.casefold() or (args.get("pet_id") is not None and task.assigned_pet_id != args["pet_id"]):
                            continue
                        matches.append({"owner_id": owner.owner_id, "owner": owner.name,
                            "pet_id": task.assigned_pet_id, "pet": owner.get_pet(task.assigned_pet_id).name,
                            "task_id": task.task_id, "title": task.title, "date": task.due_date.isoformat() if task.due_date else self.today(owner),
                            "time": task.time_of_day.strftime("%H:%M") if task.time_of_day else "Anytime",
                            "repeat": task.schedule.schedule_type.value if task.schedule else "NONE",
                            "interval_days": task.schedule.interval if task.schedule else None,
                            "status": task.status})
            if len(matches) == 1:
                m = matches[0]
                self.route(self.owner(m["owner_id"]), "Calendar", m["pet_id"], m["date"])
            return {"ok": True, "matches": matches, "clarify": len(matches) > 1}
        if name == "save_task":
            pending = self.state.get("proposal")
            proposal_id = args["proposal_id"]
            receipt = self.state["receipts"].get(proposal_id)
            if receipt:
                return receipt
            if not pending or pending["id"] != proposal_id:
                raise ValueError("That preview is no longer current. Prepare a new preview.")
            if turn != pending["turn"] + 1 or not confirmed(utterance, bool(pending["conflicts"])):
                raise ValueError("Confirm the displayed details first. For a time conflict, say save anyway.")
            owner = self.owner(pending["owner_id"])
            draft = pending["draft"].validate(owner)
            existing = next((t for t in owner.get_all_tasks() if t.creation_request_id == draft.request_id), None)
            with using_timezone(owner.timezone):
                current_conflicts = draft_conflicts(owner, draft) if existing is None else pending["conflicts"]
            if current_conflicts != pending["conflicts"]:
                self.state.pop("proposal", None)
                raise ValueError("The schedule changed. Prepare and confirm a new preview.")
            store = PlannerStore(self.root.path, owner.owner_id)
            task = existing or store.create_task(draft, allow_conflicts=bool(current_conflicts))
            saved = next((t for t in store.load().get_all_tasks() if t.creation_request_id == draft.request_id), None)
            if saved is None:
                raise ValueError("Could not verify the saved task. Check the calendar before retrying.")
            self.route(owner, "Calendar", draft.pet_id, draft.due_date.isoformat())
            result = {"ok": True, "saved": True, "task_id": task.task_id, "summary": pending["summary"]}
            self.state["receipts"][proposal_id] = result
            self.state.pop("proposal", None)
            return result
        owner = self.owner(args["owner_id"])
        pet_id = args.get("pet_id")
        if pet_id is not None and (type(pet_id) is not int or owner.find_pet(pet_id) is None):
            raise ValueError("That pet does not belong to this owner. Search again.")
        if name == "show_pets":
            self.route(owner, "Pets")
            return {"ok": True, "owner": owner.name, "pets": [
                {"pet_id": p.pet_id, "name": p.name, "species": p.species, "age": p.age} for p in owner.pets]}
        if name == "show_calendar":
            day = date.fromisoformat(args["day"])
            with using_timezone(owner.timezone):
                entries = entries_for_day(owner, day)
                tasks = [{"task_id": e.task.task_id, "pet": owner.get_pet(e.task.assigned_pet_id).name,
                          "title": e.task.title, "time": str(e.task.time_of_day) if e.task.time_of_day else "Anytime",
                          "status": e.status, "estimated_repeat": e.projected}
                         for e in entries if pet_id is None or e.task.assigned_pet_id == pet_id]
            self.route(owner, "Calendar", pet_id, day.isoformat())
            return {"ok": True, "owner": owner.name, "day": day.isoformat(), "timezone": owner.timezone, "tasks": tasks}
        if name == "preview_task":
            if _ambiguous_time(utterance):
                raise ValueError("Do you mean AM or PM? Please clarify before creating the preview.")
            # A change request invalidates any earlier confirmation, including invalid replacements.
            self.state.pop("proposal", None)
            if args["time_of_day"] is None and not args.get("anytime_confirmed", False):
                return {"ok": False, "needs_time": True, "error": MISSING_TIME_MESSAGE}
            draft = TaskDraft(pet_id, args["title"], date.fromisoformat(args["due_date"]),
                              time_of_day=time.fromisoformat(args["time_of_day"]) if args["time_of_day"] else None,
                              repeat=args.get("repeat", "NONE"), interval_days=args.get("interval_days", 1),
                              description=args.get("description", ""), location=args.get("location", "")).validate(owner)
            with using_timezone(owner.timezone):
                conflicts = draft_conflicts(owner, draft)
            summary = {"owner": owner.name, "pet": owner.get_pet(pet_id).name,
                       "title": draft.title, "date": draft.due_date.isoformat(),
                       "time": draft.time_of_day.strftime("%H:%M") if draft.time_of_day else "Anytime",
                       "timezone": owner.timezone, "repeat": draft.repeat,
                       "interval_days": draft.interval_days, "location": draft.location, "description": draft.description}
            pending = {"id": str(uuid4()), "owner_id": owner.owner_id, "draft": draft,
                       "turn": turn, "summary": summary, "conflicts": conflicts}
            self.state["proposal"] = pending
            self.route(owner, "Calendar", pet_id, draft.due_date.isoformat())
            return {"ok": True, "proposal_id": pending["id"], "summary": summary,
                    "conflicts": conflicts, "confirmation_required": True}
        raise ValueError("That action is not supported.")
