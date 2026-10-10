from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord.ext import commands

log = logging.getLogger(__name__)

# Über __file__ aufgelöst, damit der Pfad unabhängig vom CWD stimmt
EMBED_GIF_PATH = Path(__file__).resolve().parent.parent / "assets" / "gif.gif"
EMBED_IMAGE_URL = "attachment://gif.gif"
EMBED_COLOR = color=discord.Color.light_embed()
EMBED_DESC = (
    "# <:lunaRpalace:1556779035256950856> __SELF-ROLES__\n\n"
    "_ _"
    "Hier kannst du dir mit einem Klick deine Rollen auswählen! \n\n" 
    "Wähle z.B. dein Alter, deine Lieblingsspiele oder Ping-Rollen, damit andere Mitglieder gleich sehen können, was zu dir passt.\n\n" 
    "-# Keine Sorge, du kannst deine Rollen jederzeit ändern oder entfernen.\n"
    "_ _"
)

ERROR_MESSAGE = "Da ist etwas schiefgelaufen. Versuch es gleich nochmal."
FORBIDDEN_MESSAGE = "Ich darf dir die Rolle nicht geben (fehlende Rechte). Bitte melde dich beim Team."
MISSING_ROLE_MESSAGE = (
    "Oh! Deine Rolle wurde nicht gefunden.\n"
    "Bitte melde uns dies über unser Ticketsystem.\nDankeschön!"
)


def build_selfroles_embed() -> discord.Embed:
    embed = discord.Embed(description=EMBED_DESC, color=EMBED_COLOR)
    embed.set_image(url=EMBED_IMAGE_URL)
    return embed


class RoleSelect(discord.ui.Select):

    multi: bool = False

    def __init__(self, *, custom_id: str, placeholder: str, options: list[discord.SelectOption]) -> None:
        super().__init__(
            custom_id=custom_id,
            placeholder=placeholder,
            min_values=0,
            max_values=len(options) if self.multi else 1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        # Interaction sofort bestätigen, damit sie nicht mit 10062 abläuft.
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            await interaction.followup.send("Das geht nur auf dem Server.", ephemeral=True)
            return

        # Rollen per ID suchen statt per Name
        group_roles = [r for o in self.options if (r := guild.get_role(int(o.value)))]
        selected = [guild.get_role(int(v)) for v in self.values]
        if any(r is None for r in selected):
            await interaction.followup.send(MISSING_ROLE_MESSAGE, ephemeral=True)
            return

        if self.multi:
            # Das Menü kennt den Stand des Nutzers nicht, daher pro Rolle umschalten
            to_add = [r for r in selected if r not in member.roles]
            to_remove = [r for r in selected if r in member.roles]
            wanted = to_add
        else:
            if selected and selected[0] not in member.roles:
                wanted = selected
            else:
                # Nichts gewählt oder bereits vorhandene Rolle erneut gewählt -> entfernen
                wanted = []
            # Nur Unterschiede ändern, statt alles zu entfernen und neu zu vergeben
            to_remove = [r for r in group_roles if r in member.roles and r not in wanted]
            to_add = [r for r in wanted if r not in member.roles]

        try:
            if to_remove:
                await member.remove_roles(*to_remove)
            if to_add:
                await member.add_roles(*to_add)
        except discord.Forbidden:
            await interaction.followup.send(FORBIDDEN_MESSAGE, ephemeral=True)
            return
        except discord.HTTPException:
            log.exception("Rollen von %s konnten nicht geändert werden", member.id)
            await interaction.followup.send(ERROR_MESSAGE, ephemeral=True)
            return

        if self.multi:
            lines = []
            if to_add:
                lines.append("Du hast bekommen: " + ", ".join(f"**{r.name}**" for r in to_add))
            if to_remove:
                lines.append("Du hast entfernt: " + ", ".join(f"**{r.name}**" for r in to_remove))
            text = "\n".join(lines) or "Es wurde nichts geändert."
        elif wanted:
            text = f"Du hast die Rolle **{wanted[0].name}** bekommen!"
        elif selected:
            text = f"Du hast die Rolle **{selected[0].name}** entfernt."
        elif to_remove:
            text = "Deine Rolle in dieser Kategorie wurde entfernt."
        else:
            text = "Du hast in dieser Kategorie aktuell keine Rolle."

        await interaction.followup.send(text, ephemeral=True)


class MultiRoleSelect(RoleSelect):
    multi = True


class GenderRoles(RoleSelect):
    def __init__(self) -> None:
        super().__init__(
            custom_id="select_gender",
            placeholder="ㅤㅤㅤ ࿐ ˖ ⊹ㅤㅤ ABOUT ME",
            options=[
                discord.SelectOption(label="彡 girl",           value="1509590685106438232"),
                discord.SelectOption(label="彡 boy",          value="1509590685106438231"),
                discord.SelectOption(label="彡 various",            value="1509590685106438230"),
                discord.SelectOption(label="彡 other/ask",            value="1509590685106438229"),
            ],
        )


class AgeRoles(RoleSelect):
    def __init__(self) -> None:
        super().__init__(
            custom_id="select_age",
            placeholder="ㅤㅤㅤ ࿐ ˖ ⊹ㅤㅤ AGE",
            options=[
                discord.SelectOption(label="彡 age 16-18",          value="1509590685106438227"),
                discord.SelectOption(label="彡 age 19-21",          value="1509590685106438226"),
                discord.SelectOption(label="彡 age 22+",          value="1509590685106438225"),
            ],
        )


class DM_StatusRoles(RoleSelect):
    def __init__(self) -> None:
        super().__init__(
            custom_id="select_dm_status",
            placeholder="ㅤㅤㅤ ࿐ ˖ ⊹ㅤㅤ DM STATUS",
            options=[
                discord.SelectOption(label="彡 dm‘s open",               value="1526108378991165460"),
                discord.SelectOption(label="彡 dm‘s closed",             value="1526108432736981112"),
                discord.SelectOption(label="彡 ask to dm",               value="1526108482183499786"),
            ],
        )


class InterestsRoles(MultiRoleSelect):
    def __init__(self) -> None:
        super().__init__(
            custom_id="select_interests",
            placeholder="ㅤㅤㅤ ࿐ ˖ ⊹ㅤㅤ INTERESTS",
            options=[
                discord.SelectOption(label="彡 music",                   value="1526108953820528751"),
                discord.SelectOption(label="彡 food",                  value="1526108990017110117"),
                discord.SelectOption(label="彡 anime",                   value="1526109026926989382"),
                discord.SelectOption(label="彡 art/drawing",                  value="1526109065200009237"),
                discord.SelectOption(label="彡 gaming",             value="1526109142941569084"),
                discord.SelectOption(label="彡 technology",              value="1526109191922651238"),
                discord.SelectOption(label="彡 sport",                  value="1526109694949589044"),
                discord.SelectOption(label="彡 sing",                    value="1526109831503675422"),
                discord.SelectOption(label="彡 movies/series",                     value="1526110056712765450"),
                discord.SelectOption(label="彡 animals/pets",                 value="1526110349311475824"),
                discord.SelectOption(label="彡 photography",                  value="1526110878720589865"),
                discord.SelectOption(label="彡 traveling",               value="1526111110611341312"),
                discord.SelectOption(label="彡 fashion",                value="1526111166705700885"),
                discord.SelectOption(label="彡 spending time with friends",                 value="1526111315922522132"),
                discord.SelectOption(label="彡 self-care",                value="1526111717573005322"),
            ],
        )


class GamesRoles(MultiRoleSelect):
    def __init__(self) -> None:
        super().__init__(
            custom_id="select_games",
            placeholder="ㅤㅤㅤ ࿐ ˖ ⊹ㅤㅤ MY GAMES",
            options=[
                discord.SelectOption(label="彡 valo",                  value="1534258800083603466"),
                discord.SelectOption(label="彡 roblox",                     value="1534258932514820307"),
                discord.SelectOption(label="彡 fortnite",              value="1534259119807271064"),
                discord.SelectOption(label="彡 LOL",                      value="1534259357355610274"),
                discord.SelectOption(label="彡 minecraft",                  value="1534259419414532126"),
                discord.SelectOption(label="彡 tekken",                      value="1534260054100807790"),
                discord.SelectOption(label="彡 among us",                 value="1534260357898698833"),
                discord.SelectOption(label="彡 overwatch",                value="1534260527591854312"),
                discord.SelectOption(label="彡 rocket league",          value="1534260622014021803"),
                discord.SelectOption(label="彡 gta",                    value="1534260832895238154"),
                discord.SelectOption(label="彡 osu",                     value="1534260986914144389"),
                discord.SelectOption(label="彡 dbd",                     value="1534261977680187493"),
                discord.SelectOption(label="彡 counter-strike",                           value="1534262204046643200"),
                discord.SelectOption(label="彡 tft",                        value="1534262717966450869"),
                discord.SelectOption(label="彡 genshin",             value="1534270180408950794"),
            ],
        )


class PingRoles(MultiRoleSelect):
    def __init__(self) -> None:
        super().__init__(
            custom_id="select_ping",
            placeholder="ㅤㅤㅤ ࿐ ˖ ⊹ㅤㅤ PINGS",
            options=[
                discord.SelectOption(label="彡 member shouts",                              value="1509590685089796166"),
                discord.SelectOption(label="彡 chat sanitäter",                          value="1509590685089796165"),
                discord.SelectOption(label="彡 wake up !!",         value="1509590685089796164"),
                discord.SelectOption(label="彡 spielersuche",                         value="1509590685089796163"),
                discord.SelectOption(label="彡 giveaway",                            value="1526304866287222977"),
                discord.SelectOption(label="彡 event",                         value="1526305384137101435"),
                discord.SelectOption(label="彡 bump",                        value="1534664883138723912"),
            ],
        )


class RoleView01(discord.ui.View):
    """Erste Nachricht (mit Embed): Über mich, Alter, DM-Status."""

    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(GenderRoles())
        self.add_item(AgeRoles())
        self.add_item(DM_StatusRoles())


class RoleView02(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(InterestsRoles())
        self.add_item(GamesRoles())
        self.add_item(PingRoles())


class SelfRoles(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        # Registriert die Views beim Start, damit alte Nachrichten weiter reagieren
        self.bot.add_view(RoleView01())
        self.bot.add_view(RoleView02())

    @commands.command(name="selfrole-setup")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def selfrole_setup(self, ctx: commands.Context) -> None:
        file = discord.File(EMBED_GIF_PATH, filename="gif.gif")
        await ctx.channel.send(embed=build_selfroles_embed(), file=file, view=RoleView01())
        await ctx.channel.send(view=RoleView02())
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SelfRoles(bot))
