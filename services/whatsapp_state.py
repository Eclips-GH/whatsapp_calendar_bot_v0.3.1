import os
import sqlite3
import time
from pathlib import Path

STATE_DB = Path(os.getenv("WHATSAPP_STATE_DB", "whatsapp_state.db"))
RETENTION_SECONDS = 7 * 24 * 60 * 60


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(STATE_DB)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS processed_messages (
            message_id TEXT PRIMARY KEY,
            processed_at INTEGER NOT NULL
        )
        """
    )
    return conn


def claim_message(message_id: str | None) -> bool:
    """
    Retourne True si le message n'avait jamais été traité.
    Retourne False si Meta renvoie le même webhook une seconde fois.
    """
    if not message_id:
        # Un message sans ID ne peut pas être dédupliqué.
        return True

    now = int(time.time())
    cutoff = now - RETENTION_SECONDS

    with _connect() as conn:
        conn.execute(
            "DELETE FROM processed_messages WHERE processed_at < ?",
            (cutoff,),
        )
        cursor = conn.execute(
            "INSERT OR IGNORE INTO processed_messages(message_id, processed_at) VALUES (?, ?)",
            (message_id, now),
        )
        return cursor.rowcount == 1
