from __future__ import annotations

from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from config import VERIFIED_ROLE_ID, UNVERIFIED_ROLE_ID

# Über __file__ aufgelöst, damit der Pfad unabhängig vom CWD stimmt
VERIFY_GIF_PATH = Path(__file__).resolve().parent.parent / "assets" / "gif.gif"

# Fester custom_id, damit der Button auch nach einem Bot-Neustart funktioniert
VERIFY_BUTTON_ID = "verification:verify_button"


class VerifyView(discord.ui.View):
    """Persistente View mit dem Verifizieren-Button."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verifizieren",
        style=discord.ButtonStyle.secondary,
        emoji="<:lunaRpalace:1532897908901285970>",
        custom_id=VERIFY_BUTTON_ID,
    )
    async def verify(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        guild = interaction.guild
        member = interaction.user

        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message("Das geht nur auf dem Server.", ephemeral=True)
            return

        role = guild.get_role(VERIFIED_ROLE_ID)
        if role is None:
            await interaction.response.send_message(
                "Die Verifizierungsrolle ist nicht eingerichtet. Bitte melde dich beim Team.",
                ephemeral=True,
            )
            return

        # Fallback: Falls jemand den Channel trotzdem noch sieht
        if role in member.roles:
            await interaction.response.send_message("Du bist bereits verifiziert.", ephemeral=True)
            return

        try:
            await member.add_roles(role)
            # remove_roles braucht ein Objekt mit .id, eine nackte int-ID crasht
            await member.remove_roles(discord.Object(id=UNVERIFIED_ROLE_ID))
        except discord.Forbidden:
            await interaction.response.send_message(
                "Ich darf dir die Rolle nicht geben (fehlende Rechte). Bitte melde dich beim Team.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                "Da ist etwas schiefgelaufen. Versuch es gleich nochmal.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "<a:lunaRpalace:1532899609351819344> Du bist jetzt verifiziert – viel Spaß auf dem Server!", ephemeral=True
        )


class Verification(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        # Registriert die View beim Start, damit alte Buttons weiter reagieren
        self.bot.add_view(VerifyView())

    @app_commands.command(name="verify-setup", description="Postet das Verifizierungs-Embed in diesen Channel.")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def verify_setup(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Nur in Text-Channels möglich.", ephemeral=True)
            return

        embed = discord.Embed(
            description=("# <a:lunaRpalace:1533125760884281355> __VERIFIZIERUNG__\n"
            "### Willkommen auf __lunaR palace!__\n\n"
            "-# Dieser Server erfordert, dass du dich verifizierst, "
            "um Zugriff auf die anderen Kanäle zu erhalten.\n\n"
            "-# Du kannst dich ganz einfach verifizieren, indem du auf den "
            "„Verifizieren“-Button unten klickst."
        ),
            color=discord.Color.light_embed(),)
        file = discord.File(VERIFY_GIF_PATH, filename="verify.gif")
        embed.set_image(url="attachment://verify.gif")

        await interaction.channel.send(embed=embed, file=file, view=VerifyView())
        await interaction.response.send_message("Verifizierungs-Embed wurde gepostet.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Verification(bot))