import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
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


GIVEAWAY_SCHEMA = """
CREATE TABLE IF NOT EXISTS giveaways (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER UNIQUE,
    host_id INTEGER NOT NULL,
    prize TEXT NOT NULL,
    booster_only INTEGER NOT NULL DEFAULT 0,
    ends_at INTEGER NOT NULL,
    ended INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS giveaway_entries (
    giveaway_id INTEGER NOT NULL REFERENCES giveaways(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (giveaway_id, user_id)
);
CREATE TABLE IF NOT EXISTS giveaway_winners (
    giveaway_id INTEGER NOT NULL REFERENCES giveaways(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (giveaway_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_giveaways_open ON giveaways (ended, ends_at);
"""

GIVEAWAY_COLUMNS = (
    "id, guild_id, channel_id, message_id, host_id, prize, booster_only, ends_at, ended"
)


@dataclass(frozen=True, slots=True)
class GiveawayRecord:
    id: int
    guild_id: int
    channel_id: int
    message_id: int | None
    host_id: int
    prize: str
    booster_only: bool
    ends_at: int
    ended: bool


def _to_giveaway(row) -> GiveawayRecord | None:
    if row is None:
        return None
    return GiveawayRecord(*row[:6], bool(row[6]), row[7], bool(row[8]))


@contextmanager
def _giveaway_connection():
    """Verbindung mit angelegten Giveaway-Tabellen; committet beim Verlassen."""
    connection = sqlite3.connect(DATABASE_PATH)
    try:
        # Pro Verbindung nötig, sonst greift ON DELETE CASCADE nicht.
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(GIVEAWAY_SCHEMA)
        with connection:
            yield connection
    finally:
        connection.close()


def create_giveaway(
    guild_id: int,
    channel_id: int,
    host_id: int,
    prize: str,
    booster_only: bool,
    ends_at: int,
) -> int:
    with _giveaway_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO giveaways (
                guild_id, channel_id, host_id, prize, booster_only, ends_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (guild_id, channel_id, host_id, prize, booster_only, ends_at),
        )
        return cursor.lastrowid


def delete_giveaway(giveaway_id: int):
    with _giveaway_connection() as connection:
        connection.execute("DELETE FROM giveaways WHERE id = ?", (giveaway_id,))


def set_giveaway_message(giveaway_id: int, message_id: int):
    with _giveaway_connection() as connection:
        connection.execute(
            "UPDATE giveaways SET message_id = ? WHERE id = ?",
            (message_id, giveaway_id),
        )


def set_giveaway_end(giveaway_id: int, ends_at: int):
    with _giveaway_connection() as connection:
        connection.execute(
            "UPDATE giveaways SET ends_at = ? WHERE id = ?",
            (ends_at, giveaway_id),
        )


def mark_giveaway_ended(giveaway_id: int) -> bool:
    """Gibt nur beim ersten Aufruf True zurück (verhindert Doppel-Auslosung)."""
    with _giveaway_connection() as connection:
        cursor = connection.execute(
            "UPDATE giveaways SET ended = 1 WHERE id = ? AND ended = 0",
            (giveaway_id,),
        )
        return cursor.rowcount > 0


def load_giveaway(giveaway_id: int) -> GiveawayRecord | None:
    with _giveaway_connection() as connection:
        return _to_giveaway(connection.execute(
            f"SELECT {GIVEAWAY_COLUMNS} FROM giveaways WHERE id = ?",
            (giveaway_id,),
        ).fetchone())


def load_giveaway_by_message(guild_id: int, message_id: int) -> GiveawayRecord | None:
    with _giveaway_connection() as connection:
        return _to_giveaway(connection.execute(
            f"""
            SELECT {GIVEAWAY_COLUMNS} FROM giveaways
            WHERE message_id = ? AND guild_id = ?
            """,
            (message_id, guild_id),
        ).fetchone())


def load_due_giveaway_ids() -> list[int]:
    with _giveaway_connection() as connection:
        rows = connection.execute(
            "SELECT id FROM giveaways WHERE ended = 0 AND ends_at <= ?",
            (int(time.time()),),
        ).fetchall()
        return [row[0] for row in rows]


def search_giveaways(guild_id: int, ended: bool, query: str) -> list[GiveawayRecord]:
    """Höchstens 25 Treffer, so viele zeigt Discord im Autocomplete an."""
    with _giveaway_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT {GIVEAWAY_COLUMNS} FROM giveaways
            WHERE guild_id = ? AND ended = ? AND message_id IS NOT NULL
                AND prize LIKE ?
            ORDER BY ends_at DESC LIMIT 25
            """,
            (guild_id, ended, f"%{query}%"),
        ).fetchall()
        return [_to_giveaway(row) for row in rows]


def add_giveaway_entry(giveaway_id: int, user_id: int) -> bool:
    """Gibt True zurück, wenn der User neu eingetragen wurde."""
    with _giveaway_connection() as connection:
        cursor = connection.execute(
            "INSERT OR IGNORE INTO giveaway_entries VALUES (?, ?)",
            (giveaway_id, user_id),
        )
        return cursor.rowcount > 0


def count_giveaway_entries(giveaway_id: int) -> int:
    with _giveaway_connection() as connection:
        return connection.execute(
            "SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id = ?",
            (giveaway_id,),
        ).fetchone()[0]


def load_giveaway_candidates(giveaway_id: int) -> list[int]:
    """Teilnehmer, die bei diesem Giveaway noch nicht gewonnen haben."""
    with _giveaway_connection() as connection:
        rows = connection.execute(
            """
            SELECT user_id FROM giveaway_entries WHERE giveaway_id = ?
                AND user_id NOT IN (
                    SELECT user_id FROM giveaway_winners WHERE giveaway_id = ?
                )
            """,
            (giveaway_id, giveaway_id),
        ).fetchall()
        return [row[0] for row in rows]


def add_giveaway_winner(giveaway_id: int, user_id: int):
    with _giveaway_connection() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO giveaway_winners VALUES (?, ?)",
            (giveaway_id, user_id),
        )
