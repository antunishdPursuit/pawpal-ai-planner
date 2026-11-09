"""Bind save authorization to a closed audio utterance, independent of Live transcripts."""
import base64
from hashlib import sha256
from io import BytesIO
from uuid import uuid4
import wave
from gemini_planner import PlannerError
from voice_completion import confirmed
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
    if (not proposal or event.get("preview_id") != proposal["id"]
            or call.get("args") != {"proposal_id": proposal["id"]} or turn != proposal["turn"] + 1):
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
        return require_new_preview(actions, "Could not verify the spoken confirmation. Nothing was saved.")
    if not confirmed(text, bool(proposal["conflicts"])):
        return require_new_preview(actions, "The spoken request did not confirm these details. Nothing was saved. If the user cancelled, acknowledge cancellation instead of asking again.")
    verification = {"id": str(uuid4()), "session_id": session["id"], "audio_turn": local_turn,
                    "proposal_id": proposal["id"], "turn": turn, "utterance": text,
                    "args": {"proposal_id": proposal["id"]}}
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
    return actions.execute("save_task", staged["args"], staged["utterance"], staged["turn"])
