# Artemis – Discord-Bot

Discord-Bot (discord.py 2.7) für den Server „lunaR palace“. Features: Zähl-Kanal (Counting-Game) mit „Schande-Rolle“, DISBOARD-Bump-Reminder, Button-Verifizierung, Giveaways per Button, temporäre Sprachkanäle (TempVoice).

## Setup & Start

- Python 3.13, venv liegt in `env/` (nicht `.venv`).
- Abhängigkeiten: `env/Scripts/python.exe -m pip install -r requirements.txt`
- Token: `.env` mit `DISCORD_TOKEN=...` (Vorlage `.env.example`; `.env` gitignored, nie committen, nie ausgeben).
- Start: `env/Scripts/python.exe bot.py` (Pfade sind über `__file__` aufgelöst, CWD egal).
- Im Developer-Portal müssen die privilegierten Intents *Message Content* und *Server Members* aktiv sein, sonst startet der Bot nicht.
- Es gibt keine Tests und keinen Linter. Verifiziert wird per Python-Snippet mit `unittest.mock` (MagicMock-Bot/-Channel, `Loop.coro(cog)` direkt aufrufen) und temporärem `database.DATABASE_PATH`.

## Struktur

- `bot.py` – Einstiegspunkt, Intents, lädt Extensions und ruft `bot.tree.sync()` (global) in `setup_hook`; `bot.run(..., root_logger=True)`, damit `logging.getLogger(__name__)` der Module in der Konsole landet. Kein `print`.
- `config.py` – alle Discord-IDs und Einstellungen (Counting inkl. Reaktions-Emojis, Bump, Verifizierung).
- `database.py` – der gesamte DB-Zugriff (synchrones `sqlite3`, eine Verbindung pro Aufruf); Tabellen `counting_state` und `bump_reminder` (je eine Zeile pro Kanal-ID) sowie `giveaways`, `giveaway_entries`, `giveaway_winners` (über `_giveaway_connection()`, liefert `GiveawayRecord`) und `tempvoice_channels` (über `_tempvoice_connection()`, liefert `TempVoiceRecord`; eine alte Spalte `allowed` in bestehenden DBs wird ignoriert). Module greifen nie direkt auf SQLite zu.
- `modules/counting.py` – Cog `Counting`: Zustand im Speicher, nach jeder Änderung in SQLite gespiegelt; `asyncio.Lock` serialisiert Nachrichten; Reaktionen über `react()`, das HTTP-Fehler nur loggt.
- `modules/bump_reminder.py` – Cog `BumpReminder`: erkennt erfolgreiche DISBOARD-Bumps (Embed-Text), dankt dem Bumper (`THANKS_MESSAGE`, einmal pro Bump dank Rückgabewert von `save_bump`) und pingt nach `BUMP_INTERVAL_SECONDS` einmal die Rolle (nächster Ping erst nach dem nächsten Bump); `tasks.loop` alle 15 s, Fehler werden nur einmal geloggt. Nächster Ping-Zeitpunkt wird in `self.due` gecacht (DB nur beim Start gelesen, nur bei Änderung geschrieben); Edits fremder Autoren werden ohne API-Call verworfen. Texte in `THANKS_MESSAGE`/`REMINDER_MESSAGE`. Wird übersprungen, solange die IDs in `config.py` `0` sind.
- `modules/verification.py` – Cog `Verification`: persistente View (`custom_id` fest) mit Button, der `VERIFIED_ROLE_ID` vergibt; `/verify-setup` (nur Admins) postet das Embed.
- `modules/giveaway.py` – Cog `Giveaway`: `/giveaway start|beenden|reroll` (nur „Server verwalten“); persistenter `JoinButton` (`DynamicItem`, Giveaway-ID in der `custom_id`); `tasks.loop` lost fällige Giveaways aus, `mark_giveaway_ended` verhindert Doppel-Auslosung. Embed im Stil der Verifizierung, Texte in `WIN_MESSAGE` usw.; optionales Bild `assets/giveaway.gif`.
- `modules/selfroles.py` – Cog `SelfRoles`: sechs persistente Select-Menüs (`RoleView01`: Über mich/Alter/DM-Status, `RoleView02`: Interessen/Spiele/Pings), Rollen-IDs direkt in den Optionen (`value`); Einzelauswahl wechselt/entfernt die Rolle, Mehrfachauswahl (`MultiRoleSelect`) schaltet jede gewählte Rolle um (vorhanden → entfernt, fehlt → vergeben), andere bleiben. `.selfrole-setup` (Prefix-Befehl, nur Admins) postet beide Nachrichten. `ABT ME` und `彡` in den Texten sind Absicht.
- `modules/live_counter.py` – Cog `LiveCounter`: benennt `LIVE_COUNTER_CHANNEL_ID` in `CHANNEL_NAME` mit der Mitgliederzahl (bzw. Anzahl der Mitglieder von `LIVE_COUNTER_ROLE_ID`, falls nicht `0`) um; `tasks.loop` alle 5 min, nur bei Änderung (Discord-Limit: 2 Umbenennungen pro 10 min). Wird übersprungen, solange die ID `0` ist.
- `modules/tempvoice.py` – Cog `TempVoice`: Betreten von `TEMPVOICE_CREATOR_CHANNEL_ID` erstellt einen eigenen Sprachkanal (Overwrites der Kategorie + Besitzer; pro User höchstens einer alle `TEMPVOICE_CREATE_COOLDOWN` s, wer im Creator-Kanal wartet, bekommt ihn nach Ablauf), leerer Kanal wird gelöscht, verlässt der Besitzer, geht der Besitz an den nächsten Menschen. Zustand in `self.channels`, nach jeder Änderung in SQLite gespiegelt; `_startup_cleanup` räumt nach einem Neustart auf. Persistente `InterfaceView` mit 5 Emoji-Buttons ohne Label in einer Reihe (lock/unlock/limit/rename nur Besitzer oder „Kanäle verwalten“; lock sperrt nur „Verbinden“ für @everyone, wer drin ist, bleibt, wer geht, kommt nicht wieder rein, auch der alte Besitzer verliert beim Besitzerwechsel seinen Overwrite; Notfall ganz rechts, pingt `TEMPVOICE_STAFF_ROLE_ID` in `TEMPVOICE_ALERT_CHANNEL_ID`); Aktionen laufen über `respond()`, `TVError` geht als Text an den Nutzer. Keine Unicode-Emojis im Code, Button-Emojis kommen aus `TEMPVOICE_*_EMOJI`. `.tempvoice-setup` (Prefix-Befehl, nur Admins) postet das Interface; in die erstellten Kanäle schickt der Bot bewusst gar nichts. Jedes Ereignis (erstellt, gelöscht, Besitzerwechsel, lock/unlock, rename, limit, Notfall, Interface gepostet) geht über `log_event()` als weißes Embed (`light_embed`) in `TEMPVOICE_LOG_CHANNEL_ID` (`0` = kein Log). Embed nach Vorlage des VoiceMaster-Interface (Titel, englische Befehlszeilen untereinander in der Beschreibung und gemischte Sprache sind Absicht); `assets/vc-interface.jpg` ist die Trennlinie über dem Footer. Wird übersprungen, solange die Creator-ID `0` ist.
- `data/counting_quotes.json` – Sprüche bei falscher Zahl (`wrong_number`).

## Konventionen

- Nutzersichtbare Texte und Code-Kommentare auf Deutsch, Bezeichner auf Englisch. Bot-Nachrichten im Server-Stil (klein, ästhetisch, Custom-Emojis wie `<a:lunaRpalace:ID>`).
- Neue Features als Cog unter `modules/` und in `setup_hook` in `bot.py` laden.
- Discord-IDs und Emojis gehören nach `config.py`, Secrets nach `.env`.
- `requirements.txt` enthält nur direkte Abhängigkeiten (gepinnt).
- Der User editiert selbst parallel. Geänderte Dateien vor dem Bearbeiten neu lesen; Änderungen des Users nicht zurückdrehen, sondern Probleme melden.

## Bekannte Stolperfallen

- Custom-Emojis brauchen immer die ID: `<a:name:id>` bzw. `name:id` für `add_reaction`. Der Client-Name `:name~191:` funktioniert nicht (400 Unknown Emoji).
- `channel.send()` nimmt nur einen Positions-Parameter; Mehrzeiliges als ein String mit `\n`.
- Unbehandelte Exceptions (nicht `HTTPException`) in `tasks.loop` stoppen die Schleife dauerhaft.
- Die DB liegt in `data/master.db` (`DATABASE_PATH` in `database.py`); `*.db` ist gitignored, nie committen.
- Offene Review-Befunde: `.claude/reviews/` (neueste Datei).
