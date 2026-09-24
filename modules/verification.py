from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

# ID der Rolle, die Usere nach dem Klick bekommen (Rechtsklick auf Rolle -> "ID kopieren")
VERIFIED_ROLE_ID: int = 1525983950839742546

# Fester custom_id, damit der Button auch nach einem Bot-Neustart funktioniert
VERIFY_BUTTON_ID = "verification:verify_button"


class VerifyView(discord.ui.View):
    """Persistente View mit dem Verifizieren-Button."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verifizieren",
        style=discord.ButtonStyle.success,
        emoji="✅",
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
            await member.add_roles(role, reason="Verifizierung per Button")
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
            "✅ Du bist jetzt verifiziert – viel Spaß auf dem Server!", ephemeral=True
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
            title="Verifizierung",
            description=(
                "Willkommen auf dem Server! 👋\n\n"
                "Klicke auf den Button unten, um dich zu verifizieren "
                "und Zugriff auf alle Channels zu bekommen."
            ),
            color=discord.Color.green(),
        )

        await interaction.channel.send(embed=embed, view=VerifyView())
        await interaction.response.send_message("Verifizierungs-Embed wurde gepostet.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Verification(bot))