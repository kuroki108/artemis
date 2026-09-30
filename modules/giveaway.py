import logging
import random
import re
import time
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import (
    GIVEAWAY_BUTTON_EMOJI,
    GIVEAWAY_CHECK_SECONDS,
    GIVEAWAY_EMOJI,
    GIVEAWAY_WINNER_EMOJI,
)
from database import (
    GiveawayRecord,
    add_giveaway_entry,
    add_giveaway_winner,
    count_giveaway_entries,
    create_giveaway,
    delete_giveaway,
    load_due_giveaway_ids,
    load_giveaway,
    load_giveaway_by_message,
    load_giveaway_candidates,
    mark_giveaway_ended,
    search_giveaways,
    set_giveaway_end,
    set_giveaway_message,
)

log = logging.getLogger(__name__)

# Optionales Bild unter dem Embed; fehlt die Datei, wird ohne Bild gepostet.
BANNER_PATH = Path(__file__).resolve().parent.parent / "assets" / "giveaway.gif"
BANNER_NAME = "giveaway.gif"

MIN_DURATION = 60
MAX_DURATION = 30 * 86400

WIN_MESSAGE = (
    "**glückwunsch  ,  {user}**  {emoji}\n"
    "**du hast  {prize}  gewonnen  (ᴗ͈ˬᴗ͈)ഒ**"
)
REROLL_MESSAGE = (
    "**neu ausgelost  ,  {user}**  {emoji}\n"
    "**du hast  {prize}  gewonnen  (ᴗ͈ˬᴗ͈)ഒ**"
)
NO_WINNER_MESSAGE = "-# Das Giveaway um **{prize}** ist beendet, es gab keinen gültigen Teilnehmer."
NO_REROLL_MESSAGE = "-# Für **{prize}** gibt es keine weiteren gültigen Teilnehmer."


def parse_duration(text: str) -> int | None:
    """'1d12h30m' -> Sekunden, None bei ungültiger Eingabe."""
    text = text.replace(" ", "").lower()
    if not re.fullmatch(r"(?:\d+[dhms])+", text):
        return None
    units = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    return sum(int(n) * units[u] for n, u in re.findall(r"(\d+)([dhms])", text))


async def reply(interaction: discord.Interaction, text: str) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True)
    else:
        await interaction.response.send_message(text, ephemeral=True)


def build_embed(gw: GiveawayRecord, winner_id: int | None = None, entries: int = 0) -> discord.Embed:
    if gw.ended:
        winner = f"<@{winner_id}>" if winner_id else "kein gültiger Teilnehmer"
        lines = [
            f"-# Beendet: <t:{gw.ends_at}:f>",
            f"-# Gewinner: {winner}",
            f"-# Teilnehmer: **{entries}**",
        ]
    else:
        audience = "nur für Server-Booster" if gw.booster_only else "offen für alle"
        lines = [
            f"-# Endet: <t:{gw.ends_at}:R>  ·  <t:{gw.ends_at}:f>",
            f"-# Teilnahme: {audience}",
        ]

    embed = discord.Embed(
        description=(
            f"# {GIVEAWAY_EMOJI} __GIVEAWAY__\n"
            f"### {discord.utils.escape_markdown(gw.prize)}\n\n"
            + "\n".join(lines)
        ),
        color=discord.Color.light_embed(),
    )
    if BANNER_PATH.is_file():
        embed.set_image(url=f"attachment://{BANNER_NAME}")
    return embed


class JoinButton(discord.ui.DynamicItem[discord.ui.Button], template=r"giveaway:join:(?P<id>\d+)"):
    """Persistenter Button; die Giveaway-ID steckt in der custom_id."""

    def __init__(self, giveaway_id: int, disabled: bool = False) -> None:
        super().__init__(discord.ui.Button(
            label="Beendet" if disabled else "Teilnehmen",
            style=discord.ButtonStyle.secondary,
            emoji=GIVEAWAY_BUTTON_EMOJI,
            custom_id=f"giveaway:join:{giveaway_id}",
            disabled=disabled,
        ))
        self.giveaway_id = giveaway_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]) -> "JoinButton":
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.client.get_cog("Giveaway").handle_join(interaction, self.giveaway_id)


def make_view(giveaway_id: int, disabled: bool = False) -> discord.ui.View:
    return discord.ui.View(timeout=None).add_item(JoinButton(giveaway_id, disabled))


class Giveaway(commands.Cog):
    group = app_commands.Group(
        name="giveaway",
        description="Giveaways verwalten",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        # Registriert den Button beim Start, damit alte Giveaways weiter reagieren
        self.bot.add_dynamic_items(JoinButton)
        self.check_loop.start()

    async def cog_unload(self) -> None:
        self.check_loop.cancel()
        self.bot.remove_dynamic_items(JoinButton)

    async def handle_join(self, interaction: discord.Interaction, giveaway_id: int) -> None:
        gw = load_giveaway(giveaway_id)
        if not gw or gw.ended or gw.ends_at <= time.time():
            return await reply(interaction, "Dieses Giveaway ist bereits beendet.")
        if gw.booster_only and interaction.user.premium_since is None:
            return await reply(interaction, "Dieses Giveaway ist nur für Server-Booster.")
        if add_giveaway_entry(gw.id, interaction.user.id):
            await reply(interaction, "Du bist dabei – viel Glück!")
        else:
            await reply(interaction, "Du nimmst bereits an diesem Giveaway teil.")

    async def draw_winner(self, gw: GiveawayRecord) -> discord.Member | None:
        """Zufälliger Teilnehmer, der noch nicht gewonnen hat, noch auf dem Server
        ist und bei Booster-Giveaways weiterhin boostet."""
        guild = self.bot.get_guild(gw.guild_id)
        candidates = load_giveaway_candidates(gw.id) if guild else []
        random.SystemRandom().shuffle(candidates)
        for user_id in candidates:
            try:
                member = guild.get_member(user_id) or await guild.fetch_member(user_id)
            except discord.HTTPException:
                # Hat den Server verlassen.
                continue
            if gw.booster_only and member.premium_since is None:
                continue
            add_giveaway_winner(gw.id, user_id)
            return member
        return None

    async def announce(self, gw: GiveawayRecord, winner: discord.Member | None, reroll: bool = False) -> None:
        channel = self.bot.get_channel(gw.channel_id)
        if channel is None:
            log.warning("Kanal für Giveaway #%s nicht gefunden", gw.id)
            return

        # Ein erfolgloser Reroll lässt das Embed unverändert.
        if winner or not reroll:
            try:
                await channel.get_partial_message(gw.message_id).edit(
                    embed=build_embed(gw, winner and winner.id, count_giveaway_entries(gw.id)),
                    view=make_view(gw.id, disabled=True),
                )
            except discord.HTTPException:
                log.exception("Embed von Giveaway #%s konnte nicht aktualisiert werden", gw.id)

        prize = discord.utils.escape_markdown(gw.prize)
        if winner:
            template = REROLL_MESSAGE if reroll else WIN_MESSAGE
            text = template.format(user=winner.mention, emoji=GIVEAWAY_WINNER_EMOJI, prize=prize)
        else:
            text = (NO_REROLL_MESSAGE if reroll else NO_WINNER_MESSAGE).format(prize=prize)

        try:
            await channel.send(
                text,
                reference=discord.MessageReference(
                    message_id=gw.message_id, channel_id=gw.channel_id, fail_if_not_exists=False),
                allowed_mentions=discord.AllowedMentions(
                    everyone=False, roles=False, replied_user=False,
                    users=[winner] if winner else False),
            )
        except discord.HTTPException:
            log.exception("Ergebnis von Giveaway #%s konnte nicht gesendet werden", gw.id)

    async def finish(self, giveaway_id: int) -> bool:
        if not mark_giveaway_ended(giveaway_id):
            return False
        gw = load_giveaway(giveaway_id)
        await self.announce(gw, await self.draw_winner(gw))
        return True

    @tasks.loop(seconds=GIVEAWAY_CHECK_SECONDS)
    async def check_loop(self) -> None:
        # Alles abfangen: eine unbehandelte Exception würde die Schleife dauerhaft stoppen.
        try:
            giveaway_ids = load_due_giveaway_ids()
        except Exception:
            log.exception("Fällige Giveaways konnten nicht geladen werden")
            return
        for giveaway_id in giveaway_ids:
            try:
                await self.finish(giveaway_id)
            except Exception:
                log.exception("Giveaway #%s konnte nicht beendet werden", giveaway_id)

    @check_loop.before_loop
    async def before_check_loop(self) -> None:
        await self.bot.wait_until_ready()

    def resolve(self, interaction: discord.Interaction, value: str) -> GiveawayRecord | None:
        # Autocomplete liefert die Nachrichten-ID des Giveaways.
        if not value.isdigit():
            return None
        return load_giveaway_by_message(interaction.guild_id, int(value))

    def autocomplete(self, interaction: discord.Interaction, current: str, ended: bool):
        return [
            app_commands.Choice(name=f"#{gw.id} · {gw.prize}"[:100], value=str(gw.message_id))
            for gw in search_giveaways(interaction.guild_id, ended, current)
        ]

    @group.command(name="start", description="Startet ein neues Giveaway.")
    @app_commands.describe(
        preis="Was verlost wird",
        dauer="z. B. 30m, 2h, 1d12h",
        nur_booster="Nur Server-Booster dürfen teilnehmen",
    )
    async def start(
        self,
        interaction: discord.Interaction,
        preis: app_commands.Range[str, 1, 200],
        dauer: str,
        nur_booster: bool = False,
    ) -> None:
        seconds = parse_duration(dauer)
        if seconds is None or not MIN_DURATION <= seconds <= MAX_DURATION:
            return await reply(
                interaction, "Ungültige Dauer: 1 Minute bis 30 Tage, z. B. `30m`, `2h`, `1d12h`.")

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return await reply(interaction, "Nur in Text-Channels möglich.")
        has_banner = BANNER_PATH.is_file()
        perms = channel.permissions_for(interaction.guild.me)
        if not (perms.send_messages and perms.embed_links and (perms.attach_files or not has_banner)):
            return await reply(
                interaction,
                f"Mir fehlen Rechte in {channel.mention}: "
                "Nachrichten senden, Links einbetten, Dateien anhängen.")

        # Der Upload kann länger dauern als die 3 s, die Discord für die Antwort lässt.
        await interaction.response.defer(ephemeral=True)
        giveaway_id = create_giveaway(
            interaction.guild_id, channel.id, interaction.user.id,
            preis, nur_booster, int(time.time()) + seconds)
        extra = {"file": discord.File(BANNER_PATH, filename=BANNER_NAME)} if has_banner else {}
        try:
            message = await channel.send(
                embed=build_embed(load_giveaway(giveaway_id)), view=make_view(giveaway_id), **extra)
        except discord.HTTPException:
            log.exception("Giveaway-Nachricht konnte nicht gesendet werden")
            delete_giveaway(giveaway_id)
            return await reply(interaction, "Die Giveaway-Nachricht konnte nicht gesendet werden.")

        set_giveaway_message(giveaway_id, message.id)
        await reply(interaction, f"Giveaway #{giveaway_id} gestartet: {message.jump_url}")

    @group.command(name="stop", description="Lost ein laufendes Giveaway sofort aus.")
    @app_commands.describe(giveaway="Laufendes Giveaway")
    async def end(self, interaction: discord.Interaction, giveaway: str) -> None:
        gw = self.resolve(interaction, giveaway)
        if not gw or gw.ended:
            return await reply(interaction, "Kein laufendes Giveaway gefunden.")
        await interaction.response.defer(ephemeral=True)
        set_giveaway_end(gw.id, int(time.time()))
        if await self.finish(gw.id):
            await reply(interaction, f"Giveaway #{gw.id} wurde beendet und ausgelost.")
        else:
            await reply(interaction, "Das Giveaway wurde gerade schon beendet.")

    @group.command(name="reroll", description="Zieht einen neuen Gewinner für ein beendetes Giveaway.")
    @app_commands.describe(giveaway="Beendetes Giveaway")
    async def reroll(self, interaction: discord.Interaction, giveaway: str) -> None:
        gw = self.resolve(interaction, giveaway)
        if not gw or not gw.ended:
            return await reply(interaction, "Kein beendetes Giveaway gefunden.")
        await interaction.response.defer(ephemeral=True)
        winner = await self.draw_winner(gw)
        await self.announce(gw, winner, reroll=True)
        if winner:
            await reply(interaction, f"Neuer Gewinner: {winner.mention}")
        else:
            await reply(interaction, "Keine weiteren gültigen Teilnehmer vorhanden.")

    @end.autocomplete("giveaway")
    async def end_autocomplete(self, interaction: discord.Interaction, current: str):
        return self.autocomplete(interaction, current, ended=False)

    @reroll.autocomplete("giveaway")
    async def reroll_autocomplete(self, interaction: discord.Interaction, current: str):
        return self.autocomplete(interaction, current, ended=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Giveaway(bot))
