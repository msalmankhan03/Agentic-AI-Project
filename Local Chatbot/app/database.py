import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = os.getenv("DB_PATH", "./data/conversations.db")
DB_FILE = Path(DB_PATH).resolve()
DB_FILE.parent.mkdir(parents=True, exist_ok=True)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    system_prompt TEXT NOT NULL DEFAULT 'You are a helpful assistant',
    model TEXT NOT NULL DEFAULT 'llama3.2',
    temperature REAL NOT NULL DEFAULT 0.7,
    max_tokens INTEGER NOT NULL DEFAULT 512,
    top_p REAL NOT NULL DEFAULT 0.9,
    top_k INTEGER NOT NULL DEFAULT 40
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata TEXT,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn=conn)
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    if conn is None:
        with sqlite3.connect(DB_FILE) as local_conn:
            local_conn.execute("PRAGMA foreign_keys = ON")
            local_conn.executescript(SCHEMA_SQL)
            local_conn.commit()
        return

    conn.executescript(SCHEMA_SQL)
    conn.commit()


def create_conversation(title: str, system_prompt: str, model: str, temperature: float, max_tokens: int, top_p: float, top_k: int) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO conversations (title, created_at, updated_at, system_prompt, model, temperature, max_tokens, top_p, top_k)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (title, now, now, system_prompt, model, temperature, max_tokens, top_p, top_k),
        )
        return int(cursor.lastrowid)


def get_conversations() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, created_at, updated_at, system_prompt, model, temperature, max_tokens, top_p, top_k
            FROM conversations
            ORDER BY updated_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]


def get_conversation(conversation_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, title, created_at, updated_at, system_prompt, model, temperature, max_tokens, top_p, top_k FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        return dict(row) if row else None


def update_conversation(conversation_id: int, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = [fields[key] for key in fields]
    values.append(conversation_id)
    with get_connection() as conn:
        conn.execute(f"UPDATE conversations SET {assignments} WHERE id = ?", values)


def delete_conversation(conversation_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))


def search_conversations(query: str) -> list[dict[str, Any]]:
    like_query = f"%{query}%"
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.title, c.created_at, c.updated_at, c.system_prompt, c.model, c.temperature, c.max_tokens, c.top_p, c.top_k
            FROM conversations c
            LEFT JOIN messages m ON m.conversation_id = c.id
            WHERE c.title LIKE ? OR m.content LIKE ?
            GROUP BY c.id
            ORDER BY c.updated_at DESC
            """,
            (like_query, like_query),
        ).fetchall()
        return [dict(row) for row in rows]


def add_message(conversation_id: int, role: str, content: str, metadata: dict[str, Any] | None = None) -> int:
    now = datetime.now(timezone.utc).isoformat()
    metadata_json = json.dumps(metadata) if metadata else None
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at, metadata) VALUES (?, ?, ?, ?, ?)",
            (conversation_id, role, content, now, metadata_json),
        )
        return int(cursor.lastrowid)


def update_message(message_id: int, content: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE messages SET content = ? WHERE id = ?", (content, message_id))


def touch_message_conversation(message_id: int) -> None:
    """Refresh a conversation after one of its messages changes."""
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE conversations
            SET updated_at = ?
            WHERE id = (SELECT conversation_id FROM messages WHERE id = ?)
            """,
            (datetime.now(timezone.utc).isoformat(), message_id),
        )


def get_messages(conversation_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, conversation_id, role, content, created_at, metadata FROM messages WHERE conversation_id = ? ORDER BY created_at ASC, id ASC",
            (conversation_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_message(message_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT id, conversation_id, role, content, created_at, metadata FROM messages WHERE id = ?", (message_id,)).fetchone()
        return dict(row) if row else None


def delete_message(message_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))


def update_conversation_timestamp(conversation_id: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))
