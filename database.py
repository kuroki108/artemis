import sqlite3
from pathlib import Path


# Die Datei wird automatisch in data/ neben database.py angelegt.
DATABASE_PATH = Path(__file__).parent / "data" / "master.db"


def load_counting_state(channel_id: int):
    connection = sqlite3.connect(DATABASE_PATH)
    try:
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS counting_state (
                    channel_id INTEGER PRIMARY KEY,
                    count INTEGER NOT NULL DEFAULT 0,
                    last_user_id INTEGER,
                    counting_role_user_id INTEGER
                )
                """
            )
            row = connection.execute(
                """
                SELECT count, last_user_id, counting_role_user_id
                FROM counting_state WHERE channel_id = ?
                """,
                (channel_id,),
            ).fetchone()
        return row if row is not None else (0, None, None)
    finally:
        connection.close()


def save_counting_state(
    channel_id: int,
    count: int,
    last_user_id: int | None,
    counting_role_user_id: int | None,
):
    connection = sqlite3.connect(DATABASE_PATH)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO counting_state (
                    channel_id, count, last_user_id, counting_role_user_id
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    count = excluded.count,
                    last_user_id = excluded.last_user_id,
                    counting_role_user_id = excluded.counting_role_user_id
                """,
                (channel_id, count, last_user_id, counting_role_user_id),
            )
    finally:
        connection.close()


def _create_bump_table(connection: sqlite3.Connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS bump_reminder (
            channel_id INTEGER PRIMARY KEY,
            message_id INTEGER,
            due REAL
        )
        """
    )


def save_bump(channel_id: int, message_id: int, due: float) -> bool:
    """Gibt True zurück, wenn der Bump neu war (Timer wurde gestartet)."""
    connection = sqlite3.connect(DATABASE_PATH)
    try:
        with connection:
            _create_bump_table(connection)
            # Nur neuere Bump-Nachrichten starten den Timer neu, damit doppelte
            # Events und spätere Embed-Edits einen fertigen Timer nicht resetten.
            cursor = connection.execute(
                """
                INSERT INTO bump_reminder (channel_id, message_id, due)
                VALUES (?, ?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    message_id = excluded.message_id,
                    due = excluded.due
                WHERE excluded.message_id > bump_reminder.message_id
                """,
                (channel_id, message_id, due),
            )
        return cursor.rowcount > 0
    finally:
        connection.close()


def load_bump_due(channel_id: int) -> float | None:
    connection = sqlite3.connect(DATABASE_PATH)
    try:
        with connection:
            _create_bump_table(connection)
            row = connection.execute(
                "SELECT due FROM bump_reminder WHERE channel_id = ?",
                (channel_id,),
            ).fetchone()
        return row[0] if row is not None else None
    finally:
        connection.close()


def set_bump_due(channel_id: int, due: float | None):
    connection = sqlite3.connect(DATABASE_PATH)
    try:
        with connection:
            _create_bump_table(connection)
            connection.execute(
                "UPDATE bump_reminder SET due = ? WHERE channel_id = ?",
                (due, channel_id),
            )
    finally:
        connection.close()