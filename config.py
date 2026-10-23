# Discord-IDs und Einstellungen des Bots.
# IDs kopieren: Entwicklermodus an -> Rechtsklick auf Kanal/Rolle -> "ID kopieren".


# Counting
COUNTING_CHANNEL_ID = 1509590687010783233
# Rolle für den, der die Zählung zuletzt ruiniert hat.
COUNTING_ROLE_ID = 1509590685140127833

# Reaktionen: Unicode-Emoji oder Custom-Emoji als "name:id" (nicht ":name~123:").
COUNTING_CORRECT_EMOJI = "<:lunaRpalace:1532899609351819344>"
COUNTING_WRONG_EMOJI = "<:lunaRpalace:1544143111335182446>"


# Bump-Reminder (0 = nicht konfiguriert, Modul wird dann übersprungen)
BUMP_CHANNEL_ID = 1525576923517026454
BUMP_PING_ROLE_ID = 1534664883138723912
DISBOARD_BOT_ID = 302050872383242240
# Wartezeit nach einem erfolgreichen Bump bis zum Ping.
BUMP_INTERVAL_SECONDS = 2 * 60 * 60


# Verifizierung
# Rolle, die User nach dem Klick auf den Button bekommen.
VERIFIED_ROLE_ID = 1525983950839742546
UNVERIFIED_ROLE_ID = 1525983635897978981
# Emoji im Titel des Verifizierungs-Embeds (Custom-Emoji immer mit ID: "<a:name:id>").


# Giveaway
# Emoji im Titel des Giveaway-Embeds.
GIVEAWAY_EMOJI = "<a:lunaRpalace:1533125760884281355>"
# Emoji auf dem Teilnehmen-Button.
GIVEAWAY_BUTTON_EMOJI = "<:lunaRpalace:1532897908901285970>"
# Emoji in der Gewinner-Nachricht.
GIVEAWAY_WINNER_EMOJI = "<a:lunaRpalace:1532899555715055616>"
# Wie oft nach abgelaufenen Giveaways geschaut wird.
GIVEAWAY_CHECK_SECONDS = 15

LIVE_COUNTER_CHANNEL_ID = 1560983965081276446
# Rolle, deren Mitglieder gezählt werden (0 = alle Servermitglieder).
LIVE_COUNTER_ROLE_ID = 1509590685106438234


# TempVoice (Creator-Kanal 0 = nicht konfiguriert, Modul wird dann übersprungen)
# Sprachkanal, dessen Betreten einen eigenen Kanal erstellt.
TEMPVOICE_CREATOR_CHANNEL_ID = 1556053383511679016
# Kategorie für neue Kanäle (0 = Kategorie des Creator-Kanals).
TEMPVOICE_CATEGORY_ID = 1556053265353805907
# Nutzerlimit neuer Kanäle (0 = unbegrenzt).
TEMPVOICE_DEFAULT_LIMIT = 0
# Notfall-Button: Rolle, die gepingt wird, und Kanal für die Meldungen.
TEMPVOICE_STAFF_ROLE_ID = 1550585300974178356
TEMPVOICE_ALERT_CHANNEL_ID = 1552772759564714016
# Textkanal, in den alle TempVoice-Ereignisse geloggt werden (0 = kein Log).
TEMPVOICE_LOG_CHANNEL_ID = 1552772622436012196
# Wartezeit, bevor derselbe User erneut einen Kanal erstellen kann (Sekunden).
# Wer währenddessen im Creator-Kanal bleibt, bekommt den Kanal nach Ablauf.
TEMPVOICE_CREATE_COOLDOWN = 15
# Emoji im Titel des Interface-Embeds.
TEMPVOICE_EMOJI = "<a:a_lunaRpalace:1533125760884281355>"
# Emojis der Interface-Buttons (Custom-Emoji immer mit ID: "<:name:id>").
TEMPVOICE_OPEN_EMOJI = "<:a_lunaRpalace:1557076954388373585>"
TEMPVOICE_CLOSE_EMOJI = "<:a_lunaRpalace:1556771278742888508>"
TEMPVOICE_RENAME_EMOJI = "<:a_lunaRpalace:1556771351438819379>"
TEMPVOICE_LIMIT_EMOJI = "<:a_lunaRpalace:1541149690760921139>"
TEMPVOICE_EMERGENCY_EMOJI = "<:a_lunaRpalace:1562223249083867226>"
# Pfeil vor jeder Zeile der Button-Liste im Embed.
TEMPVOICE_ARROW_EMOJI = "❯"
