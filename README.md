# System Design Interview Coach

Speak System Design Interview Coach is a real-time voice AI system design interview coach built with LiveKit. It runs a mock interview out loud, pushing the student through requirements, architecture tradeoffs, bottlenecks, and follow-up questions.

## Run locally

Prerequisites:

- Docker and Docker Compose
- A LiveKit Cloud project
- An OpenAI API key with Realtime API access

On macOS, Docker Desktop works. If you prefer a lighter CLI-only setup, this project has also been verified with Homebrew Docker, Compose, and Colima:

```bash
brew install docker docker-compose colima
mkdir -p ~/.docker ~/.colima
colima start --cpu 4 --memory 6 --disk 40
docker info
docker compose version
```

Setup:

```bash
cp .env.example .env
# Fill in LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, and OPENAI_API_KEY.
docker compose up --build
```

Open the web app at `http://localhost:8080`.

Quick verification:

```bash
curl http://localhost:8000/health
docker compose ps
docker compose logs -f agent
```

Local development without Docker:

```bash
# Requires Python 3.10+.
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.server:app --reload --port 8000

# In another terminal
cd backend
source .venv/bin/activate
python agent.py dev

# In another terminal
cd frontend
npm install
npm run dev
```

The Vite app runs at `http://localhost:5173` in local development.

## Environment

All secrets and configuration are read from the project root `.env`.

- `LIVEKIT_URL`: LiveKit WebSocket URL, for example `wss://project.livekit.cloud`
- `LIVEKIT_API_KEY`: LiveKit API key
- `LIVEKIT_API_SECRET`: LiveKit API secret
- `OPENAI_API_KEY`: OpenAI key used by the LiveKit OpenAI Realtime plugin
- `AGENT_NAME`: Optional LiveKit agent dispatch name, default `system-design-coach`
- `OPENAI_REALTIME_VOICE`: Optional voice, default `coral`
- `OPENAI_TRANSCRIPTION_MODEL`: Optional input audio transcription model, default `gpt-4o-transcribe`
- `DATABASE_PATH`: Optional SQLite path, default `data/tutor.db`
- `CORS_ORIGINS`: Optional comma-separated API CORS origins
- `VITE_API_BASE`: Optional frontend API URL used at build time

## Architecture

```text
                 +------------------------------+
                 |        React web app          |
                 |  mic, text fallback, history  |
                 +--------------+---------------+
                                | HTTPS
                                v
                 +------------------------------+
                 |      FastAPI session API      |
                 | sessions, tokens, transcripts |
                 +-------+--------------+-------+
                         |              |
                         | SQLite       | signed room token
                         v              v
                 +-------------+  +----------------------+
                 | tutor.db     |  |   LiveKit Cloud room  |
                 +-------------+  +----------+-----------+
                                             | agent dispatch
                                             v
                                  +----------------------+
                                  | Python Agent worker   |
                                  | prompt + persistence  |
                                  +----------+-----------+
                                             | realtime audio/text
                                             v
                                  +----------------------+
                                  | OpenAI Realtime model |
                                  +----------------------+
```

The code is split around three responsibilities. The FastAPI service owns session management: creating sessions, resuming past sessions, signing scoped LiveKit room tokens, and storing transcripts. The React app owns the user experience: starting a voice room, showing live and saved conversation history, and providing text fallback. The LiveKit agent worker owns the voice/AI layer: joining dispatched rooms, applying the tutor instructions, streaming realtime audio/text through OpenAI, and persisting agent/user turns.

## Design decisions and tradeoffs

- **System design interview coach as the subject.** I chose system design because it benefits from live back-and-forth: the tutor can interrupt vague answers, ask for tradeoffs, and move through requirements, APIs, data model, capacity, bottlenecks, and failure modes. The tradeoff is that this is narrower than a general tutor, but the narrower scope makes the agent's behavior easier to evaluate in a short demo.
- **LiveKit Agents plus OpenAI Realtime.** The agent uses LiveKit's agent dispatch and OpenAI's realtime model instead of manually composing STT, LLM, and TTS services. This keeps latency low and reduces integration code. The tradeoff is more dependence on provider-specific realtime APIs; in production I would hide this behind a provider interface so the tutor can fall back to another realtime stack.
- **Backend-owned session and token management.** The browser never receives LiveKit API secrets. It asks FastAPI for a scoped participant token, and the token includes the room and agent dispatch metadata. This adds a small backend requirement, but it keeps credentials and room authorization centralized.
- **SQLite for persistence.** SQLite keeps the project easy to clone and run with Docker, while still showing real session and transcript boundaries. The tradeoff is write concurrency and operational visibility; it is appropriate for a two-hour take-home, not for high concurrent production traffic.
- **Simple web UI with text fallback and history.** Voice is the main interaction, but text fallback keeps the demo usable if microphone permissions, audio devices, or realtime audio fail. Saved sessions can be reviewed and resumed, which makes the tutor feel more like a learning product than a one-off chat room.
- **Device-scoped history.** The browser stores a local device token and sends it with session API calls, so saved sessions are only listed and resumed from the same local browser profile. This is not full authentication, but it prevents another local/Cognito browser session from seeing unrelated practice history in the demo.
- **Single Docker Compose stack.** API, agent worker, frontend, and the shared data volume run from one compose file. That optimizes for reviewer setup speed. The tradeoff is that local compose is not the deployment architecture I would use for autoscaling or fault isolation.

## Scaling to 10,000 concurrent sessions

- **API layer.** Keep FastAPI stateless behind a load balancer. Move session lookup, auth, and token generation to horizontally scaled API containers. Add per-user and per-tenant rate limits so session creation and resume flows cannot overload downstream media or model providers.
- **Persistence.** Replace SQLite with Postgres for sessions, transcript metadata, and summaries. Store high-volume event logs or raw turn telemetry in an append-friendly store. Use Redis for short-lived room state, idempotency keys, and fast resume/session lookup.
- **Agent workers.** Run agent workers as autoscaled containers across multiple availability zones. Scale on active rooms, CPU, memory, and realtime model latency. Keep workers stateless aside from room-local context so failed workers can be replaced quickly.
- **Realtime media.** Use LiveKit Cloud for managed scale, or run a dedicated LiveKit cluster with regional routing if lower latency, data residency, or cost control requires it. Keep users on the closest media region and dispatch agents near the room whenever possible.
- **Model provider resilience.** Put model selection behind a provider abstraction. Add timeouts, circuit breakers, and fallback providers or degraded modes, such as text-only tutoring, so one realtime model outage does not take down every session.
- **Async post-session work.** Move summary generation, analytics, and transcript cleanup to a queue. The live voice path should stay focused on low latency; expensive post-processing can run asynchronously.
- **Observability and operations.** Add structured traces for session creation, room join, agent dispatch, model turns, transcription latency, and disconnects. Track cost per session, realtime token/audio usage, error rates, and reconnect rates.
- **Security and isolation.** Keep short-lived scoped LiveKit tokens, rotate API keys through a secret manager, and enforce tenant boundaries in storage and metrics. Audit transcript access because conversation history may contain sensitive interview or user data.

## Useful commands

```bash
docker compose up --build
docker compose logs -f agent
docker compose logs -f api
```
