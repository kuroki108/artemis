import asyncio
import json
import logging
import os
import time
from pathlib import Path

import discord
from discord.ext import commands

from config import BUMP_INTERVAL_SECONDS, BUMP_PING_ROLE_ID, DISBOARD_BOT_ID

log = logging.getLogger(__name__)

BUMP_TEXTS = ("bump erfolgreich!", "bump done")

# Dank an den Bumper; {user} wird zur Erwähnung, {due} zum Unix-Timestamp des nächsten Bumps.
THANKS_MESSAGE = (
    "**tysm  ,  {user}**  <a:lunaRpalace:1532899555715055616>\n"
    "**next bump in  <t:{due}:R>  (ᴗ͈ˬᴗ͈)ഒ**"
)

STATE_FILE = Path(__file__).resolve().parent.parent / "data" / "reminders.json"


def load_pending() -> dict[str, dict]:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    # Altes Format (nur Timestamp) in das neue (Timestamp + Bumper) überführen
    return {
        channel_id: entry if isinstance(entry, dict) else {"due": entry, "user": None}
        for channel_id, entry in data.items()
    }


def is_bump_success(message: discord.Message) -> bool:
    if message.author.id != DISBOARD_BOT_ID:
        return False
    return any(
        any(t in (embed.description or "").lower() for t in BUMP_TEXTS)
        for embed in message.embeds
    )


class BumpReminder(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.timers: dict[int, asyncio.Task] = {}   # channel_id -> laufender Timer
        self.pending: dict[str, dict] = {}          # channel_id (str) -> {"due": Unix-Timestamp, "user": Bumper-ID}
        self.restored = False                       # on_ready kann bei Reconnects mehrfach feuern

    async def cog_unload(self) -> None:
        for task in self.timers.values():
            task.cancel()

    def save_pending(self) -> None:
        # Atomar schreiben: erst in Temp-Datei, dann ersetzen -> keine halbe Datei bei Absturz
        tmp = STATE_FILE.with_name(STATE_FILE.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.pending, f)
        os.replace(tmp, STATE_FILE)

    async def remind(self, channel_id: int, due: float, user_id: int | None) -> None:
        await asyncio.sleep(max(0, due - time.time()))
        try:
            channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
            # Ohne bekannten Bumper (alter Timer-Stand) bleibt nur die Anrede
            user = f"<@{user_id}>" if user_id else "there"
            await channel.send(
                f"-# ||<@&{BUMP_PING_ROLE_ID}>||\n"
                f"**hii  {user}  ,  can  u  </bump:947088344167366698>  the  server  ?  **"
                "<a:lunaRpalace:1532899201590235347>",
                allowed_mentions=discord.AllowedMentions(roles=True, users=True),
            )
        except discord.HTTPException as e:
            log.warning("Reminder für Channel %s fehlgeschlagen: %s", channel_id, e)
        finally:
            self.timers.pop(channel_id, None)
            self.pending.pop(str(channel_id), None)
            self.save_pending()

    def schedule(self, channel_id: int, due: float, user_id: int | None = None) -> None:
        old = self.timers.pop(channel_id, None)
        if old:
            old.cancel()
        self.pending[str(channel_id)] = {"due": due, "user": user_id}
        self.save_pending()
        self.timers[channel_id] = asyncio.create_task(self.remind(channel_id, due, user_id))

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self.restored:
            return
        self.restored = True
        for channel_id, entry in load_pending().items():
            self.schedule(int(channel_id), entry["due"], entry["user"])
            log.info("Timer wiederhergestellt: Channel %s", channel_id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not is_bump_success(message):
            return
        due = time.time() + BUMP_INTERVAL_SECONDS
        # Wer /bump ausgeführt hat, steht in den Interaction-Daten der Disboard-Antwort
        metadata = message.interaction_metadata
        self.schedule(message.channel.id, due, metadata.user.id if metadata else None)
        log.info("Timer gestartet für Channel %s", message.channel.id)

        if metadata is None:
            return
        try:
            await message.channel.send(
                THANKS_MESSAGE.format(user=metadata.user.mention, due=int(due)),
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        except discord.HTTPException as e:
            log.warning("Dank-Nachricht in Channel %s fehlgeschlagen: %s", message.channel.id, e)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BumpReminder(bot))
