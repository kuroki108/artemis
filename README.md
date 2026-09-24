# artemis

Discord-Bot für den Server **lunaR palace**, gebaut mit [discord.py](https://discordpy.readthedocs.io/).

## Features

- **Counting**: Zähl-Kanal. Jede richtige Zahl bekommt eine Reaktion. Bei einer falschen Zahl oder wenn jemand zweimal hintereinander zählt, wird zurückgesetzt. Wer sich verzählt, bekommt die Counting-Rolle und einen passenden Spruch.
- **Bump-Reminder**: Erkennt erfolgreiche DISBOARD-Bumps, bedankt sich beim Bumper und pingt nach 2 Stunden einmal die Bump-Rolle.
- **Verifizierung**: `/verify-setup` postet ein Embed mit Button, der die Verifiziert-Rolle vergibt.

## Setup

1. Python 3.13 installieren und eine virtuelle Umgebung anlegen:
   ```sh
   python -m venv env
   env/Scripts/python.exe -m pip install -r requirements.txt
   ```
2. `.env.example` nach `.env` kopieren und den Bot-Token eintragen.
3. Im [Developer Portal](https://discord.com/developers/applications) unter *Bot* die Intents **Server Members** und **Message Content** aktivieren.
4. IDs von Kanälen, Rollen und Emojis in `config.py` eintragen.
5. Bot-Rechte auf dem Server: Rollen verwalten (Bot-Rolle über den vergebenen Rollen), Nachrichten senden/löschen, Reaktionen hinzufügen.

## Starten

```sh
env/Scripts/python.exe bot.py
```

Der Spielstand liegt in `data/master.db` (SQLite, wird automatisch angelegt).

## Projektstruktur

| Datei | Inhalt |
| --- | --- |
| `bot.py` | Einstiegspunkt, lädt die Module |
| `config.py` | IDs und Einstellungen |
| `database.py` | Gesamter Datenbankzugriff |
| `modules/` | Ein Cog pro Feature |
| `data/counting_quotes.json` | Sprüche für falsche Zahlen |
