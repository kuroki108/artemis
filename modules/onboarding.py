import asyncio
import logging
import discord

from discord.ext import commands

from config import WELCOME_CHANNEL_ID, WELCOME_EMOJI, LEAVE_CHANNEL_ID
from config import ONBOARDING_ROLE_IDS as ROLE_IDS

logger = logging.getLogger("bot.onboarding")

WELCOME_MESSAGE = "Heyy {user}, willkommen auf **lunaR palace!** {emoji}"
LEAVE_MESSAGE = "hat **lunaR palace** gerade verlassen.\nSchade Marmelade :("
# Footer kann keine Custom-Emojis anzeigen, nur Unicode.
LEAVE_FOOTER = "⟣ 🪽 lunaR palace ₊ ⊹"


class Onboarding(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self._assign_roles(member)
        await self._send(
            WELCOME_CHANNEL_ID, member,
            content=WELCOME_MESSAGE.format(user=member.mention, emoji=WELCOME_EMOJI),
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = discord.Embed(
            author={member.name},
            description=LEAVE_MESSAGE,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        icon = member.guild.icon
        embed.set_footer(text=LEAVE_FOOTER, icon_url=icon.url if icon else None)
        await self._send(LEAVE_CHANNEL_ID, member, content=member.mention, embed=embed)

    async def _send(self, channel_id: int, member: discord.Member, **kwargs) -> None:
        # Für Bots gibt es weder Willkommens- noch Abschiedsnachricht.
        if not channel_id or member.bot:
            return

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            logger.error("Kanal mit ID %s existiert nicht.", channel_id)
            return

        try:
            await channel.send(**kwargs)
        except discord.HTTPException as exc:
            logger.error("Fehler beim Senden der Nachricht für %s: %s", member, exc)

    async def _assign_roles(self, member: discord.Member) -> None:
        if not ROLE_IDS:
            logger.warning(
                "ROLE_IDS ist leer - für %s wurden keine Rollen vergeben.", member
            )
            return

        roles_to_add = []
        for role_id in ROLE_IDS:
            role = member.guild.get_role(role_id)
            if role is None:
                logger.error(
                    "Rolle mit ID %s existiert nicht auf Server '%s'.",
                    role_id, member.guild.name,
                )
                continue
            roles_to_add.append(role)

        if not roles_to_add:
            return

        try:
            await member.add_roles(
                *roles_to_add, reason="Automatische Rollenvergabe beim Beitritt"
            )
        except discord.Forbidden:
            logger.error(
                "Keine Berechtigung, Rollen an %s zu vergeben. "
                "Prüfe, ob die Bot-Rolle in der Rollen-Hierarchie über "
                "den zu vergebenden Rollen steht.",
                member,
            )
        except discord.HTTPException as exc:
            logger.error("Fehler beim Vergeben der Rollen an %s: %s", member, exc)



async def setup(bot: commands.Bot):
    await bot.add_cog(Onboarding(bot))
