import sqlite3
from pathlib import Path
from typing import Any


DATABASE_FILE = Path(__file__).resolve().parent / "data" / "master.db"


def _connect(timeout: float = 5.0) -> sqlite3.Connection:
    return sqlite3.connect(DATABASE_FILE, timeout=timeout)


def initialize_database() -> None:
    DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS counting_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                count INTEGER NOT NULL DEFAULT 0,
                last_user_id INTEGER,
                role_holder_id INTEGER,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        existing_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(counting_state)").fetchall()
        }
        if "last_user_id" not in existing_columns:
            connection.execute(
                "ALTER TABLE counting_state ADD COLUMN last_user_id INTEGER"
            )
        if "role_holder_id" not in existing_columns:
            connection.execute(
                "ALTER TABLE counting_state ADD COLUMN role_holder_id INTEGER"
            )
        connection.execute(
            """
            INSERT OR IGNORE INTO counting_state
                (id, count, last_user_id, role_holder_id)
            VALUES (1, 0, NULL, NULL)
            """
        )
        connection.commit()


def load_state() -> dict[str, Any]:
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT count, last_user_id, role_holder_id
            FROM counting_state
            WHERE id = 1
            """
        ).fetchone()

    if row is None:
        return {"count": 0, "last_user_id": None, "role_holder_id": None}

    count, last_user_id, role_holder_id = row
    return {
        "count": int(count),
        "last_user_id": None if last_user_id is None else int(last_user_id),
        "role_holder_id": None if role_holder_id is None else int(role_holder_id),
    }


def load_count() -> int:
    return load_state()["count"]


def save_state(state: dict[str, Any]) -> None:
    with _connect(timeout=10.0) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            UPDATE counting_state
            SET count = ?,
                last_user_id = ?,
                role_holder_id = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """,
            (
                int(state.get("count", 0)),
                state.get("last_user_id"),
                state.get("role_holder_id"),
            ),
        )
        if connection.execute("SELECT changes()").fetchone()[0] == 0:
            connection.execute(
                """
                INSERT INTO counting_state
                    (id, count, last_user_id, role_holder_id)
                VALUES (1, ?, ?, ?)
                """,
                (
                    int(state.get("count", 0)),
                    state.get("last_user_id"),
                    state.get("role_holder_id"),
                ),
            )
        connection.commit()


def save_count(count: int) -> None:
    state = load_state()
    state["count"] = int(count)
    save_state(state)
