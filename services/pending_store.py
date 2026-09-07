import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(os.getenv("BOT_STATE_DB", "bot_state.db"))
PENDING_TTL_MINUTES = 30


def _connect():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_actions (
            user_id TEXT PRIMARY KEY,
            action_json TEXT NOT NULL,
            options_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    return connection


def save_pending(user_id: str, action: dict, options: list[dict]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO pending_actions(user_id, action_json, options_json, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                action_json = excluded.action_json,
                options_json = excluded.options_json,
                created_at = excluded.created_at
            """,
            (
                user_id,
                json.dumps(action, ensure_ascii=False),
                json.dumps(options, ensure_ascii=False),
                now,
            ),
        )


def get_pending(user_id: str) -> dict | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT action_json, options_json, created_at FROM pending_actions WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    if not row:
        return None

    created_at = datetime.fromisoformat(row["created_at"])
    if datetime.now(timezone.utc) - created_at > timedelta(minutes=PENDING_TTL_MINUTES):
        clear_pending(user_id)
        return None

    return {
        "action": json.loads(row["action_json"]),
        "options": json.loads(row["options_json"]),
    }


def clear_pending(user_id: str) -> None:
    with _connect() as connection:
        connection.execute(
            "DELETE FROM pending_actions WHERE user_id = ?",
            (user_id,),
        )
