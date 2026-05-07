import json
import os

from dotenv import load_dotenv
from livekit import agents, rtc
from livekit.agents import Agent, AgentServer, AgentSession, room_io
from livekit.plugins import noise_cancellation, openai
from openai.types import realtime

from app import db
from app.config import ROOT_DIR, get_settings


load_dotenv(ROOT_DIR / ".env")
settings = get_settings()
conn = db.connect(settings.database_path)
db.initialize(conn)


class SystemDesignCoach(Agent):
    def __init__(self, topic: str, conversation_context: str = "") -> None:
        opening_instruction = (
            "- Continue from the previous conversation context. Do not restart the interview."
            if conversation_context
            else "- Start by asking what system they want to design, or offer one concrete prompt."
        )
        resume_instructions = (
            f"\n\nPrevious conversation context:\n{conversation_context}\n\n"
            "Continue from this point. Do not restart the interview or ask the student to repeat "
            "answers already present in the context. Briefly acknowledge that you are continuing, "
            "then ask the next useful follow-up question."
            if conversation_context
            else ""
        )
        super().__init__(
            instructions=f"""
You are Speak, a real-time system design interview coach. Coach the student on
{topic} through an interactive mock interview.

Your coaching style:
{opening_instruction}
- Run the conversation like a senior interviewer: requirements, APIs, data model,
  capacity estimates, architecture, bottlenecks, tradeoffs, and failure modes.
- Keep spoken replies concise, usually under 20 seconds.
- Ask one focused follow-up question at a time.
- When the student gives an answer, evaluate it briefly, name the tradeoff, then
  push them to the next design decision.
- If the student gets stuck, give a small hint instead of solving the whole design.
- Prefer practical production concerns: latency, availability, consistency,
  scale, observability, cost, and operational simplicity.
- Avoid markdown, tables, emojis, and long lists because this is spoken aloud.
{resume_instructions}
""".strip()
        )


server = AgentServer()


@server.rtc_session(agent_name=settings.agent_name)
async def tutor_session(ctx: agents.JobContext):
    metadata = _metadata(ctx)
    topic = metadata.get("topic", "system design interview practice")
    session_id = metadata.get("session_id") or _session_id_from_room(ctx.room.name)
    conversation_context = _conversation_context(session_id)
    print(
        (
            "agent_session_start "
            f"session_id={session_id} room={ctx.room.name} "
            f"metadata_present={bool(metadata)} history_context={bool(conversation_context)}"
        ),
        flush=True,
    )

    session = AgentSession(
        llm=openai.realtime.RealtimeModel(
            voice=os.getenv("OPENAI_REALTIME_VOICE", "coral"),
            input_audio_transcription=realtime.AudioTranscription(
                model=os.getenv("OPENAI_TRANSCRIPTION_MODEL", "gpt-4o-transcribe"),
            ),
            input_audio_noise_reduction="near_field",
            turn_detection=realtime.realtime_audio_input_turn_detection.SemanticVad(
                type="semantic_vad",
                create_response=True,
                eagerness="auto",
                interrupt_response=True,
            ),
        )
    )

    _wire_transcript_persistence(session, session_id)

    await session.start(
        room=ctx.room,
        agent=SystemDesignCoach(topic, conversation_context),
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: noise_cancellation.BVCTelephony()
                if params.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                else noise_cancellation.BVC(),
            ),
            text_input=True,
            text_output=True,
        ),
    )

    if conversation_context:
        await session.generate_reply(
            instructions=(
                "You are resuming an earlier mock interview. Use this exact prior context:\n"
                f"{conversation_context}\n\n"
                "Briefly say you have the prior context, then continue with the next focused "
                "system design follow-up question. Do not restart the interview."
            )
        )
    else:
        await session.generate_reply(
            instructions=(
                "Greet the student by introducing yourself as Speak, their system design interview coach. "
                "Ask what system they want to design today, and offer a sample prompt if they are undecided."
            )
        )


def _metadata(ctx: agents.JobContext) -> dict[str, str]:
    raw = getattr(getattr(ctx, "job", None), "metadata", None) or ""
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _session_id_from_room(room_name: str) -> str:
    row = db.get_session_by_room(conn, room_name)
    if row:
        return row["id"]

    if "-resume-" in room_name:
        base_room_name = room_name.split("-resume-", 1)[0]
        row = db.get_session_by_room(conn, base_room_name)
        if row:
            return row["id"]

    return room_name


def _conversation_context(session_id: str) -> str:
    messages = [message for message in db.list_messages(conn, session_id) if message["role"] != "system"]
    if not messages:
        return ""

    recent_messages = messages[-10:]
    lines = []
    for message in recent_messages:
        role = "Student" if message["role"] == "user" else "Coach"
        content = str(message["content"]).strip()
        if content:
            lines.append(f"{role}: {content[:700]}")
    return "\n".join(lines)


def _wire_transcript_persistence(session: AgentSession, session_id: str) -> None:
    @session.on("conversation_item_added")
    def on_conversation_item_added(event):
        item = getattr(event, "item", event)
        role = getattr(item, "role", None) or getattr(event, "role", None) or "assistant"
        text = _extract_text(item) or _extract_text(event)
        if text:
            normalized_role = _normalize_role(role)
            db.insert_message(conn, session_id=session_id, role=normalized_role, content=text)
            print(
                f"agent_message_created session_id={session_id} role={normalized_role} text_length={len(text)}",
                flush=True,
            )
        else:
            print(f"agent_message_skipped session_id={session_id} reason=empty_text", flush=True)


def _extract_text(obj) -> str:
    for attr in ("text", "content", "transcript"):
        value = getattr(obj, attr, None)
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts = [getattr(part, "text", part) for part in value]
            return " ".join(str(part) for part in parts if part)
    return ""


def _normalize_role(role) -> str:
    value = str(role).lower()
    if "user" in value:
        return "user"
    if "assistant" in value or "agent" in value:
        return "assistant"
    return "system"


if __name__ == "__main__":
    agents.cli.run_app(server)
