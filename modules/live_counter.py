import logging

import discord
from discord.ext import commands, tasks

from config import LIVE_COUNTER_CHANNEL_ID

log = logging.getLogger(__name__)

# Kanalname; {count} wird zur Mitgliederzahl.
CHANNEL_NAME = "⊹ angels: {count}"


class LiveCounter(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.update.start()

    async def cog_unload(self) -> None:
        self.update.cancel()
        
    @tasks.loop(minutes=5)
    async def update(self) -> None:
        channel = self.bot.get_channel(LIVE_COUNTER_CHANNEL_ID)
        if channel is None:
            log.warning("Live-Counter-Kanal %s nicht gefunden", LIVE_COUNTER_CHANNEL_ID)
            return
        name = CHANNEL_NAME.format(count=channel.guild.member_count)
        if channel.name == name:
            return
        try:
            await channel.edit(name=name)
        except discord.HTTPException as e:
            log.warning("Live-Counter konnte nicht umbenannt werden: %s", e)

    @update.before_loop
    async def before_update(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    if not LIVE_COUNTER_CHANNEL_ID:
        log.warning("LIVE_COUNTER_CHANNEL_ID ist nicht gesetzt, Live-Counter wird übersprungen")
        return
    await bot.add_cog(LiveCounter(bot))
