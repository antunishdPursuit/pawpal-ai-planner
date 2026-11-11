"""Persist one voice task only after a spoken confirmation of its details."""
from dataclasses import replace
import json
import re
from uuid import UUID, uuid5
from pawpal.domain.calendar_view import draft_conflicts
from pawpal.planning.gemini_planner import decode_proposal, PlannerError
from pawpal.domain.planner_clock import using_timezone


# Match complete affirmative clauses, never a positive substring inside a change
# request, negation, question, or conditional instruction.
AFFIRMATIVE_CLAUSE = re.compile(
    r"(?:yes|yeah|yep|okay|ok|sure|absolutely|definitely|correct|confirmed|confirm|"
    r"(?:yes )?(?:i )?confirm(?: it| that| the details| the task)?|"
    r"(?:that |it )?(?:sounds|looks) (?:good|great|right|correct)(?: to me)?|"
    r"(?:that|it) works(?: for me)?|(?:that is|thats) (?:right|correct|fine)|"
    r"go ahead|(?:lets |let us |you should |you can |please )?"
    r"(?:save|add|do) (?:it|that|the task|the event)|"
    r"keep this time anyway|(?:please )?save anyway)"
)


def _confirmation_text(text):
    text = re.sub(r"[^a-z0-9 ]", " ", text.lower().replace("'", "").replace("’", ""))
    text = " ".join(text.split())
    text = re.sub(r"^(?:(?:uh|um|erm|well) )+", "", text)
    return text[:-7] if text.endswith(" please") else text


def confirmed(text, conflict=False):
    if not isinstance(text, str) or "?" in text:
        return False
    spoken = text
    text = _confirmation_text(text)
    if conflict:
        return text in {"save anyway", "yes save anyway", "yes please save anyway", "keep this time anyway"}
    # Every clause must affirm the unchanged preview. Unknown text fails closed.
    clause_text = _confirmation_text(re.sub(r"[.!;,]+", " and ", spoken))
    clauses = re.split(r"\b(?:and|yes|yeah|yep|okay|ok|sure|please|thank you|thanks)\b", clause_text)
    clauses = [clause.strip() for clause in clauses if clause.strip()]
    return (bool(clauses) and all(AFFIRMATIVE_CLAUSE.fullmatch(c) for c in clauses)) or text in {"yes", "yeah", "yep", "okay", "ok", "sure", "yeah go ahead", "yep thats right", "correct", "confirmed", "confirm", "go ahead",
                    "yes please", "yes thats right", "thats right", "yes correct", "yeah thats correct", "yes thats correct",
                    "yes that is correct", "thats correct", "do it", "yes do it", "sounds good", "yes sounds good",
                    "that works", "looks good", "yes thats fine", "thats fine", "please save that", "yes save that",
                    "save the task", "yes save the task", "go ahead and add it",
                    "save it", "yes save it", "please save it", "yes please save it", "add it", "yes add it",
                    "go ahead and save it", "yes go ahead", "yes go ahead and save it", "save anyway", "yes save anyway"}


def save_voice_task(store, owner, proposal, utterance, session_id, proposal_id):
    if store.owner_id != owner.owner_id or not isinstance(proposal, dict):
        raise PlannerError("Choose the current user's pet.")
    if not isinstance(proposal_id, str) or not 1 <= len(proposal_id) <= 200:
        raise PlannerError("Start a new voice conversation.")
    try:
        namespace = UUID(session_id)
    except (ValueError, TypeError, AttributeError):
        raise PlannerError("Start a new voice conversation.") from None
    current = store.load()
    if current is None or current.owner_id != owner.owner_id:
        raise PlannerError("Choose a user first.")
    result = decode_proposal(json.dumps(proposal), current)
    if result.draft is None:
        raise PlannerError("A complete task is needed before saving.")
    draft = replace(result.draft, request_id=str(uuid5(namespace, proposal_id)))
    existing = next((task for task in current.get_all_tasks() if task.creation_request_id == draft.request_id), None)
    if existing:
        if not confirmed(utterance):
            raise PlannerError("Confirm the task details first.")
        return existing
    with using_timezone(current.timezone):
        conflict = bool(draft_conflicts(current, draft))
    if not confirmed(utterance, conflict):
        raise PlannerError("Say 'save anyway' for this time conflict, or confirm the details in Manual." if conflict
                           else "The task was not confirmed. Review it before saving.")
    return store.create_task(draft, allow_conflicts=conflict)
