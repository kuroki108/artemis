import asyncio
import logging

import discord
from discord.ext import commands, tasks

from config import VOICE_PRESENCE_CHANNEL_ID

log = logging.getLogger(__name__)


class VoicePresence(commands.Cog):
    """Hält den Bot dauerhaft in VOICE_PRESENCE_CHANNEL_ID."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.warned = False
        self.keep_connected.start()

    async def cog_unload(self) -> None:
        self.keep_connected.cancel()
        for vc in self.bot.voice_clients:
            await vc.disconnect(force=True)

    # Prüft regelmäßig, ob der Bot noch im Kanal ist (nach Kick, Verschieben,
    # Verbindungsabbruch), und holt ihn sonst zurück.
    @tasks.loop(seconds=30)
    async def keep_connected(self) -> None:
        channel = self.bot.get_channel(VOICE_PRESENCE_CHANNEL_ID)
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            if not self.warned:
                log.warning("Sprachkanal %s nicht gefunden", VOICE_PRESENCE_CHANNEL_ID)
                self.warned = True
            return

        vc = channel.guild.voice_client
        try:
            if vc is None:
                # self_deaf: der Bot hört nichts mit, spart Bandbreite.
                await channel.connect(self_deaf=True)
                log.info("Sprachkanal %s betreten", channel.name)
            elif vc.channel != channel:
                await vc.move_to(channel)
                log.info("Zurück in Sprachkanal %s verschoben", channel.name)
            self.warned = False
        # ClientException/TimeoutError würden die Schleife sonst dauerhaft stoppen.
        except (discord.HTTPException, discord.ClientException, asyncio.TimeoutError) as e:
            if not self.warned:
                log.warning("Sprachkanal %s konnte nicht betreten werden: %s", channel.name, e)
                self.warned = True

    @keep_connected.before_loop
    async def before_keep_connected(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    if not VOICE_PRESENCE_CHANNEL_ID:
        log.warning("VOICE_PRESENCE_CHANNEL_ID ist nicht gesetzt, Voice-Presence wird übersprungen")
        return
    # Ohne PyNaCl/davey wirft connect() einen RuntimeError, der die Schleife stoppen würde.
    from discord.voice_client import has_nacl
    from discord.voice_state import has_dave
    if not (has_nacl and has_dave):
        log.error("PyNaCl oder davey fehlt bzw. lässt sich nicht laden, Voice-Presence wird übersprungen")
        return
    await bot.add_cog(VoicePresence(bot))
