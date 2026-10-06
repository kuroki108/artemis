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


# VoiceMaster (0 = nicht konfiguriert, Join-to-Create ist dann inaktiv)
# Emoji im Titel des Interface-Embeds.
VC_MASTER = "<a:lunaRpalace:1533125760884281355>"
# Pfeil vor den Einträgen im Interface-Embed.
VC_MASTER_ARROW = "<:lunaRpalace:1541211249797242881>"
# Emojis auf den Buttons des Interfaces (Custom-Emoji immer mit ID: "<:name:id>").
VC_MASTER_LOCK_EMOJI = "<:lunaRpalace:1556771278742888508>"
VC_MASTER_UNLOCK_EMOJI = "<:lunaRpalace:1557076954388373585>"
VC_MASTER_DISCONNECT_EMOJI = "<:lunaRpalace:1556771392056467526>"
VC_MASTER_LIMIT_EMOJI = "<:lunaRpalace:1556771437765992539>"
VC_MASTER_RENAME_EMOJI = "<:lunaRpalace:1556771351438819379>"
# Beitreten erstellt einen eigenen Sprachkanal.
VC_MASTER_CREATE_CHANNEL_ID = 1545980745644769402
# Kategorie für die erstellten Kanäle (0 = Kategorie des Create-Kanals).
VC_MASTER_CATEGORY_ID = 0

VC_MASTER_ALWAYS_ROLE_IDS: list[int] = [1509590685140127830] #Management
