import sqlite3
from pathlib import Path
from typing import Any


def connect(database_path: str) -> sqlite3.Connection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
          id TEXT PRIMARY KEY,
          device_token TEXT,
          room_name TEXT NOT NULL UNIQUE,
          participant_identity TEXT NOT NULL,
          participant_name TEXT NOT NULL,
          topic TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          ended_at TEXT
        );

        CREATE TABLE IF NOT EXISTS messages (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id TEXT NOT NULL,
          role TEXT NOT NULL,
          content TEXT NOT NULL,
          is_final INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
        """
    )
    _ensure_column(conn, "sessions", "device_token", "TEXT")
    conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
    columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def insert_session(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    device_token: str,
    room_name: str,
    participant_identity: str,
    participant_name: str,
    topic: str,
) -> None:
    conn.execute(
        """
        INSERT INTO sessions (id, device_token, room_name, participant_identity, participant_name, topic)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session_id, device_token, room_name, participant_identity, participant_name, topic),
    )
    conn.commit()


def get_session(conn: sqlite3.Connection, session_id: str, device_token: str | None = None) -> dict[str, Any] | None:
    if device_token is None:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ? AND device_token = ?",
            (session_id, device_token),
        ).fetchone()
    return dict(row) if row else None


def get_session_by_room(conn: sqlite3.Connection, room_name: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM sessions WHERE room_name = ?", (room_name,)).fetchone()
    return dict(row) if row else None


def list_sessions(conn: sqlite3.Connection, device_token: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT sessions.*
        FROM sessions
        LEFT JOIN (
          SELECT session_id, MAX(created_at) AS last_message_at
          FROM messages
          GROUP BY session_id
        ) recent_messages ON recent_messages.session_id = sessions.id
        WHERE device_token = ?
        ORDER BY COALESCE(recent_messages.last_message_at, sessions.created_at) DESC
        LIMIT 25
        """,
        (device_token,),
    ).fetchall()
    return [dict(row) for row in rows]


def insert_message(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    role: str,
    content: str,
    is_final: bool = True,
) -> None:
    clean = content.strip()
    if not clean:
        return
    duplicate = conn.execute(
        """
        SELECT id
        FROM messages
        WHERE session_id = ?
          AND role = ?
          AND content = ?
          AND created_at >= datetime('now', '-10 seconds')
        ORDER BY id DESC
        LIMIT 1
        """,
        (session_id, role, clean),
    ).fetchone()
    if duplicate:
        return

    conn.execute(
        """
        INSERT INTO messages (session_id, role, content, is_final)
        VALUES (?, ?, ?, ?)
        """,
        (session_id, role, clean, int(is_final)),
    )
    conn.commit()


def list_messages(conn: sqlite3.Connection, session_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, session_id, role, content, is_final, created_at
        FROM messages
        WHERE session_id = ?
        ORDER BY id ASC
        """,
        (session_id,),
    ).fetchall()
    return [dict(row) for row in rows]
