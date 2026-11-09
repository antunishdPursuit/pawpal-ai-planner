"""Bind save authorization to a closed audio utterance, independent of Live transcripts."""
import base64
from hashlib import sha256
from io import BytesIO
from uuid import uuid4
import wave
from gemini_planner import PlannerError, logger
from voice_completion import confirmed
from confirmation_intent import classify_confirmation
from voice_planner import transcribe


def failure(message):
    return {"result": {"ok": False, "error": message}}


def require_new_preview(actions, message):
    actions.state.pop("proposal", None)
    return {"result": {"ok": False, "requires_preview": True,
                       "error": message + " Call preview_task with the user's current details, read the preview, then wait for a new spoken confirmation. Do not call save_task again for the old preview."}}


def stage_save(event, actions, session):
    state = actions.state
    call = event["call"]
    proposal = state.get("proposal")
    local_turn = event.get("audio_turn")
    if (type(local_turn) is not int or local_turn < 1 or event.get("turn") != local_turn
            or session.get("audio_turn") != local_turn or not session.get("audio_closed")):
        return failure("Wait for a complete spoken confirmation before saving.")
    turn = session["base_turn"] + local_turn
    automatic = event.get("app_confirmation") is True
    current_preview = (proposal and event.get("preview_id") == proposal["id"]
                       and call.get("args") == {"proposal_id": proposal["id"]})
    valid_turn = proposal and (turn > proposal["turn"] if automatic else turn == proposal["turn"] + 1)
    if not current_preview or not valid_turn:
        if proposal and event.get("preview_id") == proposal["id"] and turn > proposal["turn"]:
            return require_new_preview(actions, "This confirmation arrived after the preview's confirmation turn. Nothing was saved.")
        return failure("Prepare a current preview, then confirm it on the next spoken turn.")
    staged = state.setdefault("live_verifications", {})
    previous = staged.get(call["id"])
    if previous and (previous["session_id"], previous["audio_turn"], previous["proposal_id"]) == (session["id"], local_turn, proposal["id"]):
        return {"verification_id": previous["id"]}
    audio = event.get("audio")
    try:
        if not isinstance(audio, str) or not audio or len(audio) > 4_200_000:
            raise ValueError()
        raw = base64.b64decode(audio, validate=True)
        with wave.open(BytesIO(raw)) as recording:
            if (recording.getnchannels() != 1 or recording.getsampwidth() != 2
                    or not 8000 <= recording.getframerate() <= 48000
                    or not 0 < recording.getnframes()/recording.getframerate() <= 30):
                raise ValueError()
    except (ValueError, wave.Error, EOFError):
        return failure("Confirmation audio is incomplete or too long. Please prepare a fresh preview and try again.")
    key = (session["id"], local_turn, sha256(raw).hexdigest())
    transcripts = state.setdefault("confirmation_transcripts", {})
    if key not in transcripts:
        try:
            owner = actions.owner(proposal["owner_id"])
            transcripts[key] = transcribe(audio, [p.name for p in owner.pets])
        except (PlannerError, ValueError):
            transcripts[key] = None
    text = transcripts[key]
    if text is None:
        return {"result": {"ok": False, "decision": "unclear", "error": "I didn't catch your reply. The task preview is unchanged. Please repeat your reply."}}
    if automatic:
        try:
            intent = classify_confirmation(text, proposal["summary"], proposal["conflicts"])
        except PlannerError:
            logger.warning("planner_event=confirmation decision=unclear reason=provider_failure")
            return {"result": {"ok": False, "decision": "unclear", "transcript": text,
                               "error": "I couldn't interpret your reply. Nothing was saved; the preview is unchanged."}}
        logger.info("planner_event=confirmation decision=%s", intent.decision)
        if intent.decision in {"change", "cancel"}:
            state.pop("proposal", None)
            return {"result": {"ok": True, "decision": intent.decision, "transcript": text}}
        if intent.decision != "confirm" or (proposal["conflicts"] and not intent.accepts_conflict):
            return {"result": {"ok": False, "decision": "unclear", "transcript": text,
                               "error": "Do you accept the displayed time conflict?" if proposal["conflicts"] else "Do you want me to save the displayed task, or change it?"}}
        # Only this server-side interpretation grants approval. Never trust a
        # client-supplied transcript or decision at the commit boundary.
        text = "save anyway" if proposal["conflicts"] else "yes"
    elif not confirmed(text, bool(proposal["conflicts"])):
        return require_new_preview(actions, "The spoken request did not confirm these details. Nothing was saved. If the user cancelled, acknowledge cancellation instead of asking again.")
    verification = {"id": str(uuid4()), "session_id": session["id"], "audio_turn": local_turn,
                    "proposal_id": proposal["id"], "turn": turn, "utterance": text,
                    "args": {"proposal_id": proposal["id"]}, "automatic": automatic,
                    "transcript": transcripts[key]}
    staged[call["id"]] = verification
    return {"verification_id": verification["id"]}


def commit_save(event, actions, session):
    call = event.get("call", {})
    staged = actions.state.get("live_verifications", {}).get(call.get("id"))
    proposal = actions.state.get("proposal")
    if (not staged or event.get("verification_id") != staged["id"]
            or session.get("id") != staged["session_id"]
            or event.get("audio_turn") != staged["audio_turn"]
            or session.get("audio_turn") != staged["audio_turn"] or not session.get("audio_closed")
            or not proposal or proposal["id"] != staged["proposal_id"]):
        return {"ok": False, "error": "The voice request or preview changed before saving. Prepare a new preview."}
    # Retry a transient storage failure once with the same bound approval and
    # idempotency key. The calendar is read back before reporting success.
    for _ in range(2):
        proposal = actions.state.get("proposal")
        if not proposal or proposal["id"] != staged["proposal_id"]:
            return {"ok": False, "error": "The preview changed. Nothing new was saved."}
        turn = proposal["turn"] + 1 if staged.get("automatic") else staged["turn"]
        result = actions.execute("save_task", staged["args"], staged["utterance"], turn)
        if not staged.get("automatic") or not result.get("retryable"):
            break
        logger.warning("planner_event=confirmation_save reason=storage_retry")
    if staged.get("automatic"):
        result.update(decision="confirm", transcript=staged["transcript"])
    return result
