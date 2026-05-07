import asyncio
import json
import re
import uuid
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from livekit import api
from pydantic import BaseModel, Field

from . import db
from .config import Settings, get_settings


settings = get_settings()
conn = db.connect(settings.database_path)
db.initialize(conn)

app = FastAPI(title="Speak Homework Voice Tutor API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateSessionRequest(BaseModel):
    participant_name: str = Field(default="Student", min_length=1, max_length=40)
    topic: str = Field(default="system design interview practice", min_length=1, max_length=80)


class CreateSessionResponse(BaseModel):
    session_id: str
    room_name: str
    participant_identity: str
    participant_name: str
    token: str
    livekit_url: str
    topic: str


class MessageRequest(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=4000)


def get_db():
    return conn


def get_device_token(x_device_token: str = Header(..., min_length=12, max_length=128)) -> str:
    return x_device_token.strip()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/sessions")
def sessions(database=Depends(get_db), device_token: str = Depends(get_device_token)):
    return {"sessions": db.list_sessions(database, device_token)}


@app.post("/api/sessions/resume/{session_id}", response_model=CreateSessionResponse)
def resume_session_by_path(
    session_id: str,
    database=Depends(get_db),
    device_token: str = Depends(get_device_token),
):
    return _resume_session_response(session_id, database, device_token)


@app.post("/api/sessions", response_model=CreateSessionResponse)
def create_session(
    payload: CreateSessionRequest,
    database=Depends(get_db),
    device_token: str = Depends(get_device_token),
):
    session_id = str(uuid.uuid4())
    room_name = f"system-design-coach-{session_id[:8]}"
    participant_identity = _identity(payload.participant_name, session_id)

    db.insert_session(
        database,
        session_id=session_id,
        device_token=device_token,
        room_name=room_name,
        participant_identity=participant_identity,
        participant_name=payload.participant_name,
        topic=payload.topic,
    )
    print(
        (
            "session_created "
            f"session_id={session_id} room={room_name} "
            f"participant={participant_identity} topic_length={len(payload.topic)}"
        ),
        flush=True,
    )

    return _session_response(
        session_id=session_id,
        room_name=room_name,
        participant_identity=participant_identity,
        participant_name=payload.participant_name,
        topic=payload.topic,
    )


@app.get("/api/sessions/{session_id}")
def get_session(
    session_id: str,
    database=Depends(get_db),
    device_token: str = Depends(get_device_token),
):
    session = db.get_session(database, session_id, device_token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": session, "messages": db.list_messages(database, session_id)}


@app.post("/api/sessions/{session_id}/resume", response_model=CreateSessionResponse)
def resume_session(
    session_id: str,
    database=Depends(get_db),
    device_token: str = Depends(get_device_token),
):
    return _resume_session_response(session_id, database, device_token)


def _resume_session_response(session_id: str, database, device_token: str) -> CreateSessionResponse:
    session = db.get_session(database, session_id, device_token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    room_name = f"{session['room_name']}-resume-{uuid.uuid4().hex[:8]}"
    print(
        (
            "session_resumed "
            f"session_id={session['id']} original_room={session['room_name']} "
            f"resume_room={room_name} message_count={len(db.list_messages(database, session_id))}"
        ),
        flush=True,
    )
    return _session_response(
        session_id=session["id"],
        room_name=room_name,
        participant_identity=session["participant_identity"],
        participant_name=session["participant_name"],
        topic=session["topic"],
        is_resume=True,
    )


@app.get("/api/sessions/{session_id}/messages")
def messages(
    session_id: str,
    database=Depends(get_db),
    device_token: str = Depends(get_device_token),
):
    if not db.get_session(database, session_id, device_token):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"messages": db.list_messages(database, session_id)}


@app.post("/api/sessions/{session_id}/messages", status_code=201)
def add_message(
    session_id: str,
    payload: MessageRequest,
    database=Depends(get_db),
    device_token: str = Depends(get_device_token),
):
    if not db.get_session(database, session_id, device_token):
        raise HTTPException(status_code=404, detail="Session not found")
    db.insert_message(database, session_id=session_id, role=payload.role, content=payload.content)
    print(
        f"message_created session_id={session_id} role={payload.role} text_length={len(payload.content)}",
        flush=True,
    )
    return {"status": "created"}


@app.post("/api/sessions/{session_id}/summary")
def summarize(
    session_id: str,
    database=Depends(get_db),
    device_token: str = Depends(get_device_token),
):
    session = db.get_session(database, session_id, device_token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = db.list_messages(database, session_id)
    assistant_points = [m["content"] for m in messages if m["role"] == "assistant"][-3:]
    user_points = [m["content"] for m in messages if m["role"] == "user"][-3:]
    if not messages:
        summary = "No conversation has been captured yet."
    else:
        summary = (
            f"Topic: {session['topic']}. "
            f"Recent student questions: {_join(user_points)} "
            f"Recent tutor guidance: {_join(assistant_points)}"
        )
    return {"summary": summary}


def _identity(name: str, session_id: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.lower()).strip("-") or "student"
    return f"{slug}-{session_id[:8]}"


def _session_response(
    *,
    session_id: str,
    room_name: str,
    participant_identity: str,
    participant_name: str,
    topic: str,
    is_resume: bool = False,
) -> CreateSessionResponse:
    metadata = json.dumps({"session_id": session_id, "topic": topic, "resume": is_resume})
    _dispatch_agent(room_name, metadata)
    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(participant_identity)
        .with_name(participant_name)
        .with_grants(
            api.VideoGrants(
                room_create=True,
                room_join=True,
                room=room_name,
                can_publish=True,
                can_publish_data=True,
                can_subscribe=True,
            )
        )
        .to_jwt()
    )
    return CreateSessionResponse(
        session_id=session_id,
        room_name=room_name,
        participant_identity=participant_identity,
        participant_name=participant_name,
        token=token,
        livekit_url=settings.livekit_url,
        topic=topic,
    )


def _dispatch_agent(room_name: str, metadata: str) -> None:
    async def dispatch() -> None:
        client = api.LiveKitAPI(settings.livekit_url, settings.livekit_api_key, settings.livekit_api_secret)
        try:
            dispatch_info = await client.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    room=room_name,
                    agent_name=settings.agent_name,
                    metadata=metadata,
                )
            )
            print(
                f"agent_dispatched room={room_name} agent={settings.agent_name} dispatch_id={dispatch_info.id}",
                flush=True,
            )
        finally:
            await client.aclose()

    asyncio.run(dispatch())


def _join(items: list[str]) -> str:
    if not items:
        return "None yet."
    return " / ".join(items)
