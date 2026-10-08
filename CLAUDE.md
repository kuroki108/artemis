# Artemis – Discord-Bot

Discord-Bot (discord.py 2.7) für den Server „lunaR palace“. Features: Zähl-Kanal (Counting-Game) mit „Schande-Rolle“, DISBOARD-Bump-Reminder, Button-Verifizierung, Giveaways per Button.

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
- `database.py` – der gesamte DB-Zugriff (synchrones `sqlite3`, eine Verbindung pro Aufruf); Tabellen `counting_state` und `bump_reminder` (je eine Zeile pro Kanal-ID) sowie `giveaways`, `giveaway_entries`, `giveaway_winners` (über `_giveaway_connection()`, liefert `GiveawayRecord`). Module greifen nie direkt auf SQLite zu.
- `modules/counting.py` – Cog `Counting`: Zustand im Speicher, nach jeder Änderung in SQLite gespiegelt; `asyncio.Lock` serialisiert Nachrichten; Reaktionen über `react()`, das HTTP-Fehler nur loggt.
- `modules/bump_reminder.py` – Cog `BumpReminder`: erkennt erfolgreiche DISBOARD-Bumps (Embed-Text), dankt dem Bumper (`THANKS_MESSAGE`, einmal pro Bump dank Rückgabewert von `save_bump`) und pingt nach `BUMP_INTERVAL_SECONDS` einmal die Rolle (nächster Ping erst nach dem nächsten Bump); `tasks.loop` alle 15 s, Fehler werden nur einmal geloggt. Nächster Ping-Zeitpunkt wird in `self.due` gecacht (DB nur beim Start gelesen, nur bei Änderung geschrieben); Edits fremder Autoren werden ohne API-Call verworfen. Texte in `THANKS_MESSAGE`/`REMINDER_MESSAGE`. Wird übersprungen, solange die IDs in `config.py` `0` sind.
- `modules/verification.py` – Cog `Verification`: persistente View (`custom_id` fest) mit Button, der `VERIFIED_ROLE_ID` vergibt; `/verify-setup` (nur Admins) postet das Embed.
- `modules/giveaway.py` – Cog `Giveaway`: `/giveaway start|beenden|reroll` (nur „Server verwalten“); persistenter `JoinButton` (`DynamicItem`, Giveaway-ID in der `custom_id`); `tasks.loop` lost fällige Giveaways aus, `mark_giveaway_ended` verhindert Doppel-Auslosung. Embed im Stil der Verifizierung, Texte in `WIN_MESSAGE` usw.; optionales Bild `assets/giveaway.gif`.
- `modules/selfroles.py` – Cog `SelfRoles`: sechs persistente Select-Menüs (`RoleView01`: Über mich/Alter/DM-Status, `RoleView02`: Interessen/Spiele/Pings), Rollen-IDs direkt in den Optionen (`value`); Einzelauswahl wechselt/entfernt die Rolle, Mehrfachauswahl (`MultiRoleSelect`) schaltet jede gewählte Rolle um (vorhanden → entfernt, fehlt → vergeben), andere bleiben. `.selfrole-setup` (Prefix-Befehl, nur Admins) postet beide Nachrichten. `ABT ME` und `彡` in den Texten sind Absicht.
- `modules/vc_master.py` – Cog `VcMaster` (Join-to-Create): Beitritt zu `VC_MASTER_CREATE_CHANNEL_ID` erstellt einen eigenen Sprachkanal (Tabelle `vc_master_channels`: Kanal → Besitzer). Schutz: Cooldown pro Nutzer, ein Kanal pro Nutzer (vorhandener wird wiederverwendet), `create_lock`, Rate-Limit-Sperre (`blocked_until`); abgelehnte Nutzer werden still getrennt (keine DMs). `tasks.loop` `sweep` gleicht die DB mit Discord ab: löscht Kanäle nach `VC_MASTER_EMPTY_DELETE_SECONDS` Leerlauf und übergibt Kanäle nach `VC_MASTER_OWNER_GRACE_SECONDS` ohne Besitzer (`transfer_ownership`). Persistente Buttons (`VoiceInterface`: lock/unlock/disconnect/limit/rename) prüfen den Besitzer bei Klick und beim Absenden (`check_owner`), Discord-Fehler laufen über `safe()`. `.vc-setup` (Prefix-Befehl, nur Admins) postet das Interface.
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
