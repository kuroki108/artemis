import asyncio
import logging
import time

import discord
from discord.ext import commands, tasks

from config import (
    BUMP_CHANNEL_ID,
    BUMP_INTERVAL_SECONDS,
    BUMP_PING_ROLE_ID,
    DISBOARD_BOT_ID,
)
from database import load_bump_due, save_bump, set_bump_due

log = logging.getLogger(__name__)

THANKS_MESSAGE = (
    "**tysm{user}**  <a:lunaRpalace:1532899555715055616>\n"
    "**next bump in  <t:{due}:R>  (ᴗ͈ˬᴗ͈)ഒ**"
)
REMINDER_MESSAGE = (
    "-# ||{role}||\n"
    "# **hii  ,  can  u  </bump:947088344167366698>  the  server  ?**  "
    "<a:lunaRpalace:1532899201590235347>"
)


def is_success(message: discord.Message) -> bool:
    if (message.guild is None or message.channel.id != BUMP_CHANNEL_ID
            or message.author.id != DISBOARD_BOT_ID):
        return False
    for embed in message.embeds:
        text = "\n".join(filter(None, [embed.title, embed.description]))
        text += "\n" + "\n".join(f"{f.name}\n{f.value}" for f in embed.fields)
        if any(s in text.casefold() for s in ("bump erfolgreich!", "bump done!")):
            return True
    return False


class BumpReminder(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.lock = asyncio.Lock()
        # Fehler im Reminder nur einmal loggen statt alle 15 s.
        self.error_logged = False
        # Zeitpunkt des nächsten Pings im Speicher, die DB nur bei Änderungen.
        self.due = load_bump_due(BUMP_CHANNEL_ID)

    def log_error_once(self, text: str, exc_info: bool = False):
        if not self.error_logged:
            log.error(text, exc_info=exc_info)
            self.error_logged = True

    async def cog_load(self):
        self.remind.start()

    async def cog_unload(self):
        task = self.remind.get_task()
        self.remind.cancel()
        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def register_bump(self, message: discord.Message):
        if not is_success(message):
            return
        due = message.created_at.timestamp() + BUMP_INTERVAL_SECONDS
        async with self.lock:
            is_new = save_bump(BUMP_CHANNEL_ID, message.id, due)
            if is_new:
                self.due = due
        # Nur einmal pro Bump danken, auch wenn Send- und Edit-Event kommen.
        if is_new:
            await self.send_thanks(message, due)

    async def send_thanks(self, message: discord.Message, due: float):
        # DISBOARD antwortet auf /bump, darüber kennen wir den Bumper.
        metadata = message.interaction_metadata
        user = metadata.user if metadata is not None else None
        try:
            await message.channel.send(
                THANKS_MESSAGE.format(
                    user=f"  ,  {user.mention}" if user is not None else "",
                    due=int(due)),
                allowed_mentions=discord.AllowedMentions(
                    everyone=False, roles=False,
                    users=[user] if user is not None else False),
            )
        except discord.HTTPException:
            log.exception("Danke-Nachricht konnte nicht gesendet werden")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        await self.register_bump(message)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        # Antworten auf Slash-Commands bekommen ihr Embed oft erst per Edit.
        if payload.channel_id != BUMP_CHANNEL_ID or "embeds" not in payload.data:
            return
        # Nur DISBOARD-Nachrichten nachladen, nicht jede Edit im Kanal.
        author_id = payload.data.get("author", {}).get("id")
        if author_id is not None and int(author_id) != DISBOARD_BOT_ID:
            return
        try:
            channel = self.bot.get_channel(BUMP_CHANNEL_ID)
            if channel is None:
                channel = await self.bot.fetch_channel(BUMP_CHANNEL_ID)
            await self.register_bump(await channel.fetch_message(payload.message_id))
        except discord.HTTPException:
            log.exception("DISBOARD-Nachricht konnte nicht geladen werden")

    @tasks.loop(seconds=15)
    async def remind(self):
        if not self.bot.is_ready():
            return
        async with self.lock:
            if self.due is None or self.due > time.time():
                return
            try:
                channel = self.bot.get_channel(BUMP_CHANNEL_ID)
                if channel is None:
                    channel = await self.bot.fetch_channel(BUMP_CHANNEL_ID)
                role = channel.guild.get_role(BUMP_PING_ROLE_ID)
                if role is None or role.is_default():
                    self.log_error_once(
                        "BUMP_PING_ROLE_ID muss eine existierende Rolle sein (nicht @everyone)")
                    return
                await channel.send(
                    REMINDER_MESSAGE.format(role=role.mention),
                    allowed_mentions=discord.AllowedMentions(
                        everyone=False, users=False, roles=[role], replied_user=False),
                )
            except discord.HTTPException:
                self.log_error_once(
                    "Reminder konnte nicht gesendet werden; neuer Versuch alle 15 s",
                    exc_info=True)
                return
            self.error_logged = False
            # Nur ein Ping pro Bump, der nächste Timer startet mit dem nächsten Bump.
            self.due = None
            set_bump_due(BUMP_CHANNEL_ID, None)

    @remind.before_loop
    async def before_remind(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    if BUMP_CHANNEL_ID <= 0 or BUMP_PING_ROLE_ID <= 0:
        # Nicht abbrechen, sonst startet der ganze Bot nicht.
        log.warning("Bump-Reminder deaktiviert: BUMP_CHANNEL_ID und BUMP_PING_ROLE_ID "
                    "in config.py eintragen.")
        return
    if not bot.intents.message_content:
        raise ValueError("Der Bot benötigt intents.message_content = True.")
    await bot.add_cog(BumpReminder(bot))