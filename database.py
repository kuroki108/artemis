import sqlite3
from pathlib import Path


DATABASE_FILE = Path(__file__).resolve().parent / "data" / "master.db"


def initialize_database() -> None:
    DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE_FILE) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS counting_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT OR IGNORE INTO counting_state (id, count) VALUES (1, 0)"
        )


def load_count() -> int:
    with sqlite3.connect(DATABASE_FILE) as connection:
        row = connection.execute(
            "SELECT count FROM counting_state WHERE id = 1"
        ).fetchone()
    return int(row[0])


def save_count(count: int) -> None:
    with sqlite3.connect(DATABASE_FILE) as connection:
        connection.execute(
            """
            UPDATE counting_state
            SET count = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """,
            (count,),
        )
