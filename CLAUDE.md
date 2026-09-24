# Artemis – Discord-Bot

Discord-Bot (discord.py 2.7) für den Server „lunaR palace“. Aktuell einziges Feature: ein Zähl-Kanal (Counting-Game) mit „Schande-Rolle“ für den, der die Serie zuletzt ruiniert hat.

## Setup & Start

- Python 3.13, venv liegt in `env/` (nicht `.venv`).
- Abhängigkeiten: `env/Scripts/python.exe -m pip install -r requirements.txt`
- Token: `.env` mit `DISCORD_TOKEN=...` (gitignored, nie committen, nie ausgeben).
- Start: `env/Scripts/python.exe bot.py` (Pfade sind über `__file__` aufgelöst, CWD egal).
- Im Developer-Portal müssen die privilegierten Intents *Message Content* und *Server Members* aktiv sein, sonst startet der Bot nicht.
- Es gibt keine Tests und keinen Linter.

## Struktur

- `bot.py` – Einstiegspunkt, Intents, lädt Extensions in `setup_hook`.
- `config.py` – hartkodierte Discord-IDs (Kanal, Rolle, Admin-Rollen).
- `database.py` – der gesamte DB-Zugriff (synchrones `sqlite3`, eine Verbindung pro Aufruf); Tabellen `counting_state` und `bump_reminder`, je eine Zeile pro Kanal-ID. Module greifen nie direkt auf SQLite zu.
- `modules/counting.py` – Cog `Counting`: Zustand im Speicher, nach jeder Änderung in SQLite gespiegelt; `asyncio.Lock` serialisiert Nachrichten.
- `modules/bump_reminder.py` – Cog `BumpReminder`: erkennt erfolgreiche DISBOARD-Bumps (Embed-Text) und dankt dem Bumper (`THANKS_MESSAGE`, einmal pro Bump dank Rückgabewert von `save_bump`) und pingt nach `BUMP_INTERVAL_SECONDS` einmal die Rolle (nächster Ping erst nach dem nächsten Bump); `tasks.loop` alle 15 s, Fehler werden nur einmal geloggt, Zustand in Tabelle `bump_reminder`. Wird übersprungen, solange die IDs in `config.py` `0` sind.
- `data/counting_quotes.json` – Sprüche bei falscher Zahl (`wrong_number`).

## Konventionen

- Nutzersichtbare Texte und Code-Kommentare auf Deutsch, Bezeichner auf Englisch.
- Neue Features als Cog unter `modules/` und in `setup_hook` in `bot.py` laden.
- Discord-IDs gehören nach `config.py`, Secrets nach `.env`.

## Bekannte Stolperfallen

- Die DB liegt in `data/master.db` (`DATABASE_PATH` in `database.py`).
- `*.db` ist gitignored; die DB nie wieder committen.
- Offene Review-Befunde: `.claude/reviews/2026-09-24-review.md`.
