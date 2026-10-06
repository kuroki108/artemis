from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord.ext import commands

import database
from config import (
    VC_MASTER,
    VC_MASTER_ALWAYS_ROLE_IDS,
    VC_MASTER_CATEGORY_ID,
    VC_MASTER_CREATE_CHANNEL_ID,
    VC_MASTER_DISCONNECT_EMOJI,
    VC_MASTER_LIMIT_EMOJI,
    VC_MASTER_LOCK_EMOJI,
    VC_MASTER_LOG_CHANNEL_ID,
    VC_MASTER_RENAME_EMOJI,
    VC_MASTER_UNLOCK_EMOJI,
)

log = logging.getLogger(__name__)

EMBED_COLOR = 0xFFFFFF
SEPARATOR_PATH = Path(__file__).resolve().parent.parent / "assets" / "vc-interface.jpg"
MAX_LIMIT = 99


# Einträge im Interface-Embed (Emoji, Name, Text), untereinander, in der Reihenfolge der Buttons
ENTRIES = [
    (VC_MASTER_LOCK_EMOJI, "lock", "the voice channel"),
    (VC_MASTER_UNLOCK_EMOJI, "unlock", "the voice channel"),
    (VC_MASTER_DISCONNECT_EMOJI, "disconnect", "a member"),
    (VC_MASTER_LIMIT_EMOJI, "change", "user limit"),
    (VC_MASTER_RENAME_EMOJI, "rename", "the voice channel"),
]


def _column(entries: list[tuple[str, str, str]]) -> str:
    return "\n".join(f"{emoji} `{name}` {text}" for emoji, name, text in entries)


def interface_embed(guild: discord.Guild) -> discord.Embed:
    link = f"https://discord.com/channels/{guild.id}/{VC_MASTER_CREATE_CHANNEL_ID}"
    embed = discord.Embed(
        description=(
            f"# {VC_MASTER} __VoiceMaster Interface__\n"
            f"<:lunaRpalace:1536504134457499648> Klick [hier]({link}) um einen VC zu erstellen."
        ),
        color=EMBED_COLOR,
    )
    embed.add_field(name="​", value=_column(ENTRIES), inline=False)
    embed.set_image(url=f"attachment://{SEPARATOR_PATH.name}")
    embed.set_footer(text="Nutze die Buttons unten, um deinen Sprachkanal zu verwalten.")
    return embed


def reply_embed(text: str) -> discord.Embed:
    return discord.Embed(description=text, color=EMBED_COLOR)


async def vc_log(client: discord.Client, text: str) -> None:
    if not VC_MASTER_LOG_CHANNEL_ID:
        return
    try:
        channel = client.get_channel(VC_MASTER_LOG_CHANNEL_ID) or await client.fetch_channel(VC_MASTER_LOG_CHANNEL_ID)
        await channel.send(text, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException as e:
        log.warning("VoiceMaster-Log fehlgeschlagen: %s", e)


async def reply(interaction: discord.Interaction, text: str) -> None:
    await interaction.response.send_message(embed=reply_embed(text), ephemeral=True)


async def get_vc(interaction: discord.Interaction) -> discord.VoiceChannel | None:
    member = interaction.user
    voice = member.voice if isinstance(member, discord.Member) else None
    if voice is None or not isinstance(voice.channel, discord.VoiceChannel):
        await reply(interaction, "Du bist in keinem Sprachkanal.")
        return None

    channel = voice.channel
    owner_id = database.load_vc_owner(channel.id)
    if owner_id is None:
        await reply(interaction, "Dieser Kanal wird nicht vom VoiceMaster verwaltet.")
        return None
    if owner_id != member.id:
        await reply(interaction, f"Nur <@{owner_id}> kann diesen Kanal verwalten.")
        return None
    return channel


class LimitModal(discord.ui.Modal, title="User-Limit ändern"):
    limit = discord.ui.TextInput(
        label=f"Neues Limit (0 = unbegrenzt, max. {MAX_LIMIT})", min_length=1, max_length=2, placeholder="z. B. 5"
    )

    def __init__(self, channel: discord.VoiceChannel) -> None:
        super().__init__()
        self.channel = channel
        self.limit.default = str(channel.user_limit)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        value = self.limit.value.strip()
        if not value.isdigit() or not 0 <= int(value) <= MAX_LIMIT:
            await reply(interaction, f"Bitte gib eine Zahl zwischen 0 und {MAX_LIMIT} ein.")
            return
        new_limit = int(value)
        await self.channel.edit(user_limit=new_limit)
        text = "unbegrenzt" if new_limit == 0 else str(new_limit)
        await reply(interaction, f"{self.channel.mention} hat jetzt ein Limit von **{text}**.")
        await vc_log(interaction.client, f"{interaction.user.mention} hat das Limit von {self.channel.mention} auf **{text}** gesetzt.")


class RenameModal(discord.ui.Modal, title="Kanal umbenennen"):
    name = discord.ui.TextInput(label="Neuer Name", min_length=1, max_length=100)

    def __init__(self, channel: discord.VoiceChannel) -> None:
        super().__init__()
        self.channel = channel
        self.name.default = channel.name

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        old_name = self.channel.name
        new_name = self.name.value.strip()
        try:
            await self.channel.edit(name=new_name)
        except discord.RateLimited as e:
            # Discord erlaubt nur 2 Umbenennungen pro 10 Minuten
            await interaction.followup.send(
                embed=reply_embed(
                    f"Zu viele Umbenennungen. Versuch es in {int(e.retry_after // 60) + 1} Minute(n) nochmal."
                ),
                ephemeral=True,
            )
            return
        except discord.HTTPException as e:
            await interaction.followup.send(
                embed=reply_embed(f"Umbenennen fehlgeschlagen: {e.text}"), ephemeral=True
            )
            return
        await interaction.followup.send(
            embed=reply_embed(f"Kanal umbenannt in **{new_name}**."), ephemeral=True
        )
        await vc_log(interaction.client, f"{interaction.user.mention} hat **{old_name}** in {self.channel.mention} (**{new_name}**) umbenannt.")


class DisconnectSelect(discord.ui.UserSelect):
    def __init__(self, channel: discord.VoiceChannel) -> None:
        super().__init__(placeholder="Wähle ein Mitglied …")
        self.channel = channel

    async def callback(self, interaction: discord.Interaction) -> None:
        target = interaction.guild.get_member(self.values[0].id)
        if target is None or target not in self.channel.members:
            await interaction.response.edit_message(
                embed=reply_embed("Das Mitglied ist nicht in deinem Kanal."), view=None
            )
        elif target.id == interaction.user.id:
            await interaction.response.edit_message(
                embed=reply_embed("Du kannst dich nicht selbst rauswerfen."), view=None
            )
        else:
            await target.move_to(None, reason=f"Getrennt von {interaction.user}")
            await interaction.response.edit_message(
                embed=reply_embed(f"{target.mention} wurde getrennt."), view=None
            )
            await vc_log(interaction.client, f"{interaction.user.mention} hat {target.mention} aus {self.channel.mention} getrennt.")


class PickerView(discord.ui.View):
    """Kurzlebige View mit einem einzelnen Auswahlmenü."""

    def __init__(self, select: discord.ui.Item) -> None:
        super().__init__(timeout=120)
        self.add_item(select)


class VoiceInterface(discord.ui.View):
    """Persistente Buttons (feste custom_ids), eine Reihe."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(emoji=VC_MASTER_LOCK_EMOJI, style=discord.ButtonStyle.secondary, custom_id="vcmaster:lock")
    async def lock(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        channel = await get_vc(interaction)
        if channel is None:
            return
        everyone = channel.overwrites_for(interaction.guild.default_role)
        everyone.connect = False
        await channel.set_permissions(interaction.guild.default_role, overwrite=everyone)
        # Der Besitzer darf immer wieder rein
        owner = channel.overwrites_for(interaction.user)
        owner.connect = True
        await channel.set_permissions(interaction.user, overwrite=owner)
        await reply(interaction, f"{channel.mention} wurde gesperrt.")
        await vc_log(interaction.client, f"{interaction.user.mention} hat {channel.mention} gesperrt.")

    @discord.ui.button(emoji=VC_MASTER_UNLOCK_EMOJI, style=discord.ButtonStyle.secondary, custom_id="vcmaster:unlock")
    async def unlock(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        channel = await get_vc(interaction)
        if channel is None:
            return
        everyone = channel.overwrites_for(interaction.guild.default_role)
        everyone.connect = None
        await channel.set_permissions(interaction.guild.default_role, overwrite=everyone)
        await reply(interaction, f"{channel.mention} wurde entsperrt.")
        await vc_log(interaction.client, f"{interaction.user.mention} hat {channel.mention} entsperrt.")

    @discord.ui.button(emoji=VC_MASTER_DISCONNECT_EMOJI, style=discord.ButtonStyle.secondary, custom_id="vcmaster:disconnect")
    async def disconnect(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        channel = await get_vc(interaction)
        if channel is None:
            return
        await interaction.response.send_message(
            view=PickerView(DisconnectSelect(channel)), ephemeral=True
        )

    @discord.ui.button(emoji=VC_MASTER_LIMIT_EMOJI, style=discord.ButtonStyle.secondary, custom_id="vcmaster:limit")
    async def limit(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        channel = await get_vc(interaction)
        if channel is None:
            return
        await interaction.response.send_modal(LimitModal(channel))

    @discord.ui.button(emoji=VC_MASTER_RENAME_EMOJI, style=discord.ButtonStyle.secondary, custom_id="vcmaster:rename")
    async def rename(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        channel = await get_vc(interaction)
        if channel is None:
            return
        await interaction.response.send_modal(RenameModal(channel))


class VcMaster(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.cleaned_up = False

    async def cog_load(self) -> None:
        # Registriert die View beim Start, damit alte Buttons weiter reagieren
        self.bot.add_view(VoiceInterface())

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        # Kanäle, die geleert oder gelöscht wurden, während der Bot offline war
        if self.cleaned_up:
            return
        self.cleaned_up = True
        for channel_id in database.load_vc_channel_ids():
            channel = self.bot.get_channel(channel_id)
            try:
                if channel is None:
                    database.delete_vc_channel(channel_id)
                elif isinstance(channel, discord.VoiceChannel) and not channel.members:
                    await channel.delete(reason="VoiceMaster: Kanal leer")
                    database.delete_vc_channel(channel_id)
            except discord.HTTPException:
                log.exception("Aufräumen von %s fehlgeschlagen", channel_id)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        if before.channel == after.channel:
            return

        if VC_MASTER_CREATE_CHANNEL_ID and after.channel and after.channel.id == VC_MASTER_CREATE_CHANNEL_ID:
            await self.create_channel(member, after.channel)

        if before.channel and not before.channel.members:
            if database.load_vc_owner(before.channel.id) is not None:
                try:
                    await before.channel.delete(reason="VoiceMaster: Kanal leer")
                except discord.NotFound:
                    pass
                except (discord.HTTPException, discord.RateLimited):
                    # Eintrag bleibt, damit das Aufräumen beim nächsten Start es erneut versucht
                    log.exception("Löschen von %s fehlgeschlagen", before.channel.id)
                    return
                database.delete_vc_channel(before.channel.id)
                await vc_log(self.bot, f"**{before.channel.name}** wurde gelöscht, weil alle den Kanal verlassen haben.")

    async def create_channel(self, member: discord.Member, trigger: discord.VoiceChannel) -> None:
        log.info("Erstelle Kanal für %s", member)
        category = (
            member.guild.get_channel(VC_MASTER_CATEGORY_ID) if VC_MASTER_CATEGORY_ID else trigger.category
        )
        # Explizite Overwrites ersetzen die der Kategorie, daher werden sie hier übernommen
        overwrites = dict(category.overwrites) if category else {}
        for role_id in VC_MASTER_ALWAYS_ROLE_IDS:
            if (role := member.guild.get_role(role_id)) is not None:
                overwrites[role] = discord.PermissionOverwrite(connect=True, view_channel=True)
        # Der Ersteller muss seinen Kanal immer sehen und betreten dürfen, sonst scheitert das Verschieben
        overwrites[member] = discord.PermissionOverwrite(connect=True, view_channel=True)
        try:
            channel = await member.guild.create_voice_channel(
                name=f"⊹ {member.display_name}'s vc",
                category=category,
                overwrites=overwrites,
                reason=f"VoiceMaster: Kanal für {member}",
            )
        except discord.RateLimited as e:
            # Discord begrenzt das Erstellen von Kanälen pro Tag; discord.py wirft hier sofort statt zu warten
            log.warning("Kanal für %s nicht erstellt: Rate-Limit, nächster Versuch in %d Min.", member, e.retry_after // 60)
            await vc_log(self.bot, f"Kanal für {member.mention} nicht erstellt: Discord-Limit für neue Kanäle erreicht (wieder möglich in ca. {int(e.retry_after // 3600) + 1} Std.).")
            return
        except discord.HTTPException:
            log.exception("Kanal für %s konnte nicht erstellt werden", member)
            return
        database.save_vc_channel(channel.id, member.id)
        await vc_log(self.bot, f"{member.mention} hat {channel.mention} erstellt.")
        try:
            await member.move_to(channel)
        except discord.HTTPException:
            # Meist ist der User schon wieder weg, sonst fehlen dem Bot Rechte (z. B. "Mitglieder verschieben")
            log.exception("%s konnte nicht in den neuen Kanal verschoben werden", member)
            try:
                await channel.delete(reason="VoiceMaster: User nicht verschiebbar")
            except (discord.HTTPException, discord.RateLimited):
                log.exception("Löschen von %s fehlgeschlagen", channel.id)
            database.delete_vc_channel(channel.id)

    @commands.command(name="vc-setup")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def vc_setup(self, ctx: commands.Context) -> None:
        """Postet das VoiceMaster-Interface (.vc-setup) in diesen Channel."""
        if not VC_MASTER_CREATE_CHANNEL_ID:
            await ctx.send("`VC_MASTER_CREATE_CHANNEL_ID` ist in der config.py noch nicht gesetzt.")
            return
        await ctx.send(
            embed=interface_embed(ctx.guild),
            file=discord.File(SEPARATOR_PATH),
            view=VoiceInterface(),
        )
        # Der Aufruf selbst wird entfernt, damit nur das Interface stehen bleibt
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VcMaster(bot))
