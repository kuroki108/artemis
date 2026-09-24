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