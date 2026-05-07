import React, { FormEvent, useEffect, useRef, useState } from 'react';
import ReactDOM from 'react-dom/client';
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useConnectionState,
  useLocalParticipant,
  useRemoteParticipants,
  useRoomContext,
  useTranscriptions,
} from '@livekit/components-react';
import '@livekit/components-styles';
import {
  BookOpen,
  DoorOpen,
  Loader2,
  MessageSquareText,
  Mic,
  MicOff,
  RefreshCw,
  Send,
  Signal,
  SignalZero,
  Sparkles,
  ArrowLeft,
} from 'lucide-react';
import { ConnectionState as LiveKitConnectionState, Track } from 'livekit-client';
import './styles.css';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';
const DEVICE_TOKEN_KEY = 'speak-coach-device-token';

function getDeviceToken() {
  const existing = window.localStorage.getItem(DEVICE_TOKEN_KEY);
  if (existing) return existing;

  const token = window.crypto?.randomUUID?.() ?? `device-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  window.localStorage.setItem(DEVICE_TOKEN_KEY, token);
  return token;
}

function apiFetch(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  headers.set('X-Device-Token', getDeviceToken());
  return fetch(`${API_BASE}${path}`, { ...init, headers });
}

type SessionResponse = {
  session_id: string;
  room_name: string;
  participant_identity: string;
  participant_name: string;
  token: string;
  livekit_url: string;
  topic: string;
};

type ConversationLine = {
  id: string;
  text: string;
  identity: string;
  role: 'user' | 'assistant';
};

type SessionRecord = {
  id: string;
  room_name: string;
  participant_identity: string;
  participant_name: string;
  topic: string;
  created_at: string;
  ended_at: string | null;
};

type MessageRecord = {
  id: number;
  session_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  is_final: number;
  created_at: string;
};

type SessionDetail = {
  session: SessionRecord;
  messages: MessageRecord[];
};

function App() {
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [initialConversation, setInitialConversation] = useState<ConversationLine[]>([]);
  const [view, setView] = useState<'start' | 'history'>('start');
  const [participantName, setParticipantName] = useState('Student');
  const [topic, setTopic] = useState('Design a URL shortener');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [selectedHistory, setSelectedHistory] = useState<SessionDetail | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState('');
  const [resumeLoading, setResumeLoading] = useState(false);

  useEffect(() => {
    if (view === 'history') {
      void loadSessions();
    }
  }, [view]);

  async function loadSessions() {
    setHistoryError('');
    setHistoryLoading(true);
    try {
      const response = await apiFetch('/api/sessions');
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = (await response.json()) as { sessions: SessionRecord[] };
      setSessions(payload.sessions);
      if (payload.sessions.length > 0) {
        await loadSessionDetail(payload.sessions[0].id);
      } else {
        setSelectedHistory(null);
      }
    } catch (err) {
      setHistoryError(err instanceof Error ? err.message : 'Unable to load past conversations');
    } finally {
      setHistoryLoading(false);
    }
  }

  async function loadSessionDetail(sessionId: string) {
    setHistoryError('');
    try {
      setSelectedHistory(await fetchSessionDetail(sessionId));
    } catch (err) {
      setHistoryError(err instanceof Error ? err.message : 'Unable to load conversation');
    }
  }

  async function fetchSessionDetail(sessionId: string) {
    const response = await apiFetch(`/api/sessions/${sessionId}`);
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return (await response.json()) as SessionDetail;
  }

  async function startSession(event: FormEvent) {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      const response = await apiFetch('/api/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ participant_name: participantName, topic }),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      setInitialConversation([]);
      setSession(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to start session');
    } finally {
      setLoading(false);
    }
  }

  async function resumeSession(detail: SessionDetail) {
    setHistoryError('');
    setResumeLoading(true);
    try {
      const freshDetail = await fetchSessionDetail(detail.session.id);
      const response = await apiFetch(`/api/sessions/resume/${detail.session.id}`, {
        method: 'POST',
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      setSelectedHistory(freshDetail);
      setInitialConversation(conversationLinesFromMessages(freshDetail));
      setSession((await response.json()) as SessionResponse);
    } catch (err) {
      setHistoryError(err instanceof Error ? err.message : 'Unable to resume session');
    } finally {
      setResumeLoading(false);
    }
  }

  if (session) {
    return (
      <LiveKitRoom
        key={session.room_name}
        token={session.token}
        serverUrl={session.livekit_url}
        connect
        audio
        video={false}
        className="room-shell"
        onError={(err) => setError(err.message)}
      >
        <TutorRoom
          session={session}
          initialConversation={initialConversation}
          onLeave={() => {
            setSession(null);
            void loadSessions();
          }}
        />
        <RoomAudioRenderer />
      </LiveKitRoom>
    );
  }

  if (view === 'history') {
    return (
      <HistoryPage
        sessions={sessions}
        selectedHistory={selectedHistory}
        loading={historyLoading}
        error={historyError}
        onRefresh={loadSessions}
        onSelect={loadSessionDetail}
        onResume={resumeSession}
        resumeLoading={resumeLoading}
        onBack={() => setView('start')}
      />
    );
  }

  return (
    <main className="app">
      <section className="intro">
        <div className="brand">
          <Sparkles size={28} />
          <span>Speak Coach</span>
        </div>
        <h1>
          Ace your next
          <span>System Design Interview.</span>
        </h1>
        <p>
          A LiveKit-powered interview coach for requirements, architecture tradeoffs,
          bottlenecks, and follow-up questions.
        </p>
      </section>

      <div className="start-column">
        <form className="start-panel" onSubmit={startSession}>
          <label>
            Your name
            <input
              value={participantName}
              onChange={(event) => setParticipantName(event.target.value)}
              placeholder="Student"
            />
          </label>
          <label>
            Mock interview question
            <input value={topic} onChange={(event) => setTopic(event.target.value)} />
          </label>
          <button type="submit" disabled={loading}>
            <Mic size={18} />
            {loading ? 'Starting...' : 'Start voice session'}
          </button>
          {error && <p className="error">{error}</p>}
        </form>
        <button className="history-entry-button" type="button" onClick={() => setView('history')}>
          <MessageSquareText size={18} />
          Resume past sessions
        </button>
      </div>
    </main>
  );
}

function HistoryPage({
  sessions,
  selectedHistory,
  loading,
  error,
  onRefresh,
  onSelect,
  onResume,
  resumeLoading,
  onBack,
}: {
  sessions: SessionRecord[];
  selectedHistory: SessionDetail | null;
  loading: boolean;
  error: string;
  onRefresh: () => Promise<void>;
  onSelect: (sessionId: string) => Promise<void>;
  onResume: (detail: SessionDetail) => Promise<void>;
  resumeLoading: boolean;
  onBack: () => void;
}) {
  return (
    <main className="history-page">
      <header className="history-header">
        <button className="secondary-button" type="button" onClick={onBack}>
          <ArrowLeft size={18} />
          Back
        </button>
        <div>
          <div className="eyebrow">Saved practice</div>
          <h1>Past sessions</h1>
        </div>
        <button className="secondary-button" type="button" onClick={() => void onRefresh()} disabled={loading}>
          <RefreshCw size={18} />
          Refresh
        </button>
      </header>

      {error && <p className="error">{error}</p>}
      <section className="history-page-layout">
        <aside className="history-session-pane">
          {sessions.length === 0 ? (
            <div className="empty history-empty">{loading ? 'Loading sessions...' : 'No saved conversations yet.'}</div>
          ) : (
            sessions.map((item) => (
              <div
                className={`session-list-item ${selectedHistory?.session.id === item.id ? 'session-list-item-active' : ''}`}
                key={item.id}
              >
                <button className="session-row" type="button" onClick={() => void onSelect(item.id)}>
                  <span>{item.topic}</span>
                  <small>
                    {item.participant_name} · {formatDate(item.created_at)}
                  </small>
                </button>
                {selectedHistory?.session.id === item.id && selectedHistory && (
                  <button
                    className="session-row-resume"
                    type="button"
                    onClick={() => void onResume(selectedHistory)}
                    disabled={resumeLoading}
                  >
                    <Mic size={16} />
                    {resumeLoading ? 'Resuming...' : 'Resume'}
                  </button>
                )}
              </div>
            ))
          )}
        </aside>

        <section className="history-detail-pane">
          {!selectedHistory ? (
            <div className="empty history-empty">Select a conversation.</div>
          ) : (
            <>
              <div className="history-detail-title">
                <div>
                  <h2>{selectedHistory.session.topic}</h2>
                  <span>
                    {selectedHistory.session.participant_name} · {formatDate(selectedHistory.session.created_at)}
                  </span>
                </div>
              </div>
              <div className="history-transcript">
                {selectedHistory.messages.length === 0 ? (
                  <div className="empty history-empty">No messages were captured for this session.</div>
                ) : (
                  selectedHistory.messages.map((message) => (
                    <article
                      className={`history-line ${
                        message.role === 'user' ? 'history-user-line' : 'history-assistant-line'
                      }`}
                      key={message.id}
                    >
                      <div className="speaker">{message.role === 'user' ? 'Student' : 'Coach'}</div>
                      <p>{message.content}</p>
                    </article>
                  ))
                )}
              </div>
            </>
          )}
        </section>
      </section>
    </main>
  );
}

function TutorRoom({
  session,
  initialConversation,
  onLeave,
}: {
  session: SessionResponse;
  initialConversation: ConversationLine[];
  onLeave: () => void;
}) {
  const { localParticipant, isMicrophoneEnabled } = useLocalParticipant();
  const [pauseChanging, setPauseChanging] = useState(false);
  const paused = !isMicrophoneEnabled;

  async function togglePause() {
    setPauseChanging(true);
    try {
      const microphone = localParticipant.getTrackPublication(Track.Source.Microphone);
      if (microphone) {
        if (microphone.isMuted) {
          await microphone.unmute();
        } else {
          await microphone.mute();
        }
      } else {
        await localParticipant.setMicrophoneEnabled(true);
      }
    } finally {
      setPauseChanging(false);
    }
  }

  return (
    <main className="room">
      <header className="room-header">
        <div>
          <div className="eyebrow">Mock Interview Room</div>
          <h1>{session.topic}</h1>
        </div>
        <ConnectionStatusPill />
      </header>

      <section className="lesson-grid">
        <TranscriptPanel
          key={session.room_name}
          session={session}
          initialConversation={initialConversation}
        />
        <aside className="side-column">
          <section className="coach-panel">
            <BookOpen size={22} />
            <h2>Interview tips</h2>
            <ul className="tips-list">
              <li>Start by clarifying users, core use cases, and success metrics.</li>
              <li>Separate functional requirements from scale and reliability goals.</li>
              <li>Define APIs and data model before drawing the architecture.</li>
              <li>Estimate rough QPS, storage, and bandwidth to justify choices.</li>
              <li>Call out bottlenecks, failure modes, and operational tradeoffs.</li>
              <li>Prefer simple designs first, then evolve them as constraints grow.</li>
            </ul>
          </section>
          <div className="session-actions">
            <button className={paused ? 'resume' : 'pause'} onClick={togglePause} disabled={pauseChanging}>
              {paused ? <MicOff size={18} /> : <Mic size={18} />}
              {paused ? 'Unmute' : 'Mute'}
            </button>
            <button className="leave" onClick={onLeave}>
              <DoorOpen size={18} />
              Leave Interview Room
            </button>
          </div>
        </aside>
      </section>
    </main>
  );
}

function ConnectionStatusPill() {
  const state = useConnectionState();
  const remoteParticipants = useRemoteParticipants();
  const coachConnected = remoteParticipants.some(isCoachParticipant);
  const status = connectionStatusForState(state, coachConnected);
  const Icon = status.icon;

  return (
    <div className={`status ${status.className}`}>
      <Icon size={16} />
      <span>{status.label}</span>
    </div>
  );
}

function connectionStatusForState(state: LiveKitConnectionState, coachConnected: boolean) {
  switch (state) {
    case LiveKitConnectionState.Connected:
      return coachConnected
        ? { label: 'Coach connected', className: 'status-connected', icon: Signal }
        : { label: 'Waiting for coach', className: 'status-connecting', icon: Loader2 };
    case LiveKitConnectionState.Connecting:
      return { label: 'Connecting', className: 'status-connecting', icon: Loader2 };
    case LiveKitConnectionState.Reconnecting:
    case LiveKitConnectionState.SignalReconnecting:
      return { label: 'Reconnecting', className: 'status-connecting', icon: Loader2 };
    default:
      return { label: 'Disconnected', className: 'status-disconnected', icon: SignalZero };
  }
}

function isCoachParticipant(participant: { identity: string; name?: string }) {
  return (
    participant.identity.startsWith('agent-') ||
    participant.identity.includes('agent') ||
    participant.name === 'system-design-coach' ||
    participant.name === 'Interview Coach'
  );
}

function TranscriptPanel({
  session,
  initialConversation,
}: {
  session: SessionResponse;
  initialConversation: ConversationLine[];
}) {
  const room = useRoomContext();
  const transcriptions = useTranscriptions();
  const [lines, setLines] = useState<ConversationLine[]>(initialConversation);
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const transcriptionSaveTimers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const persistedTranscriptions = useRef(new Set<string>());

  useEffect(() => {
    setLines(initialConversation);
    persistedTranscriptions.current.clear();
  }, [initialConversation, session.room_name]);

  useEffect(() => {
    return () => {
      for (const timer of transcriptionSaveTimers.current.values()) {
        clearTimeout(timer);
      }
      transcriptionSaveTimers.current.clear();
    };
  }, [session.room_name]);

  useEffect(() => {
    const incomingLines: ConversationLine[] = [];

    for (const [index, item] of transcriptions.entries()) {
      const text = item.text.trim();
      if (!text) continue;

      const participantIdentity = item.participantInfo.identity ?? 'speaker';
      const id = `live-${item.streamInfo.id ?? index}`;
      const line: ConversationLine = {
        id,
        text,
        identity: displayNameForParticipant(participantIdentity, session),
        role: roleForParticipant(participantIdentity, session),
      };
      incomingLines.push(line);
      scheduleUserTranscriptionPersist(line, session.session_id);
    }

    setLines((current) => {
      let next = current;

      for (const line of incomingLines) {
        const existingIndex = next.findIndex((entry) => entry.id === line.id);
        if (existingIndex >= 0) {
          if (next[existingIndex].text === line.text && next[existingIndex].identity === line.identity) {
            continue;
          }
          next = next.map((entry, entryIndex) => (entryIndex === existingIndex ? line : entry));
        } else {
          next = [...next, line];
        }
      }

      return next;
    });
  }, [session, transcriptions]);

  function scheduleUserTranscriptionPersist(line: ConversationLine, sessionId: string) {
    if (line.role !== 'user') return;

    const timerKey = line.id;
    const persistedKey = `${line.id}:${line.text}`;
    if (persistedTranscriptions.current.has(persistedKey)) return;

    const existingTimer = transcriptionSaveTimers.current.get(timerKey);
    if (existingTimer) {
      clearTimeout(existingTimer);
    }

    const timer = setTimeout(() => {
      persistedTranscriptions.current.add(persistedKey);
      transcriptionSaveTimers.current.delete(timerKey);
      void apiFetch(`/api/sessions/${sessionId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: 'user', content: line.text }),
      }).catch(() => {
        persistedTranscriptions.current.delete(persistedKey);
      });
    }, 1200);

    transcriptionSaveTimers.current.set(timerKey, timer);
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    const text = message.trim();
    if (!text) return;

    const localLine: ConversationLine = {
      id: `manual-${Date.now()}`,
      text,
      identity: session.participant_name,
      role: 'user',
    };

    setLines((current) => [...current, localLine]);
    setMessage('');
    setSending(true);
    try {
      await room.localParticipant.sendText(text, { topic: 'lk.chat' });
      await apiFetch(`/api/sessions/${session.session_id}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: 'user', content: text }),
      });
    } finally {
      setSending(false);
    }
  }

  return (
    <section className="transcript">
      <div className="section-title">
        <h2>Conversation</h2>
        <span>{lines.length} messages</span>
      </div>
      <div className="transcript-list">
        {lines.length === 0 ? (
          <div className="empty">Waiting for speech or text...</div>
        ) : (
          lines.map((line) => (
            <article className={`line ${line.role === 'user' ? 'user-line' : 'assistant-line'}`} key={line.id}>
              <div className="speaker">{line.identity}</div>
              <p>{line.text}</p>
            </article>
          ))
        )}
      </div>
      <form className="chat-composer" onSubmit={sendMessage}>
        <input
          id="chat"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="Type a response or follow-up question"
        />
        <button type="submit" disabled={sending || !message.trim()} aria-label="Send text">
          <Send size={18} />
        </button>
      </form>
    </section>
  );
}

function displayNameForParticipant(identity: string, session: SessionResponse) {
  if (identity === session.participant_identity) return session.participant_name;
  if (identity.startsWith('agent-') || identity.includes('agent')) return 'Interview Coach';
  return identity;
}

function roleForParticipant(identity: string, session: SessionResponse): ConversationLine['role'] {
  return identity === session.participant_identity ? 'user' : 'assistant';
}

function conversationLinesFromMessages(detail: SessionDetail): ConversationLine[] {
  return detail.messages
    .filter((message) => message.role !== 'system')
    .map((message) => ({
      id: `saved-${message.id}`,
      text: message.content,
      identity: message.role === 'user' ? detail.session.participant_name : 'Interview Coach',
      role: message.role === 'user' ? 'user' : 'assistant',
    }));
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date);
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
