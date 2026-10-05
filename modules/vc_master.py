from __future__ import annotations

import logging

import discord
from discord.ext import commands

import database
from config import (
    VC_MASTER,
    VC_MASTER_ARROW,
    VC_MASTER_CATEGORY_ID,
    VC_MASTER_CREATE_CHANNEL_ID,
)

log = logging.getLogger(__name__)

EMBED_COLOR = 0x2B2D31
MAX_LIMIT = 99

# Einträge im Interface-Embed (links / rechts), genau wie die Buttons
LEFT_COLUMN = [
    ("lock", "the voice channel"),
    ("unlock", "the voice channel"),
    ("claim", "the voice channel"),
]
RIGHT_COLUMN = [
    ("disconnect", "a member"),
    ("change", "user limit"),
]


def _column(entries: list[tuple[str, str]]) -> str:
    return "\n".join(f"{VC_MASTER_ARROW} `{name}` {text}" for name, text in entries)


def interface_embed(guild: discord.Guild) -> discord.Embed:
    link = f"https://discord.com/channels/{guild.id}/{VC_MASTER_CREATE_CHANNEL_ID}"
    embed = discord.Embed(
        description=(
            f"# {VC_MASTER} __VoiceMaster Interface__\n"
            f"└ Klick [hier]({link}) um einen VC zu erstellen."
        ),
        color=EMBED_COLOR,
    )
    embed.add_field(name="​", value=_column(LEFT_COLUMN), inline=True)
    embed.add_field(name="​", value=_column(RIGHT_COLUMN), inline=True)
    embed.add_field(
        name="​",
        value="━" * 34 + "\n-# **Nutze die Buttons unten, um deinen Sprachkanal zu verwalten.**",
        inline=False,
    )
    return embed


def reply_embed(text: str) -> discord.Embed:
    return discord.Embed(description=text, color=EMBED_COLOR)


async def reply(interaction: discord.Interaction, text: str) -> None:
    await interaction.response.send_message(embed=reply_embed(text), ephemeral=True)


async def get_vc(
    interaction: discord.Interaction, *, owner_only: bool = True
) -> discord.VoiceChannel | None:
    """Sprachkanal des Users, falls vom VoiceMaster verwaltet (und ihm gehörend). Antwortet sonst selbst."""
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
    if owner_only and owner_id != member.id:
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


class PickerView(discord.ui.View):
    """Kurzlebige View mit einem einzelnen Auswahlmenü."""

    def __init__(self, select: discord.ui.Item) -> None:
        super().__init__(timeout=120)
        self.add_item(select)


class VoiceInterface(discord.ui.View):
    """Persistente Buttons (feste custom_ids), zwei Reihen."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(emoji="🔒", style=discord.ButtonStyle.secondary, custom_id="vcmaster:lock", row=0)
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

    @discord.ui.button(emoji="🔓", style=discord.ButtonStyle.secondary, custom_id="vcmaster:unlock", row=0)
    async def unlock(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        channel = await get_vc(interaction)
        if channel is None:
            return
        everyone = channel.overwrites_for(interaction.guild.default_role)
        everyone.connect = None
        await channel.set_permissions(interaction.guild.default_role, overwrite=everyone)
        await reply(interaction, f"{channel.mention} wurde entsperrt.")

    @discord.ui.button(emoji="👑", style=discord.ButtonStyle.secondary, custom_id="vcmaster:claim", row=0)
    async def claim(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        channel = await get_vc(interaction, owner_only=False)
        if channel is None:
            return
        owner_id = database.load_vc_owner(channel.id)
        if owner_id == interaction.user.id:
            await reply(interaction, "Der Kanal gehört dir bereits.")
        elif any(m.id == owner_id for m in channel.members):
            await reply(interaction, f"<@{owner_id}> ist noch im Kanal.")
        else:
            database.save_vc_channel(channel.id, interaction.user.id)
            await reply(interaction, f"{channel.mention} gehört jetzt dir.")

    @discord.ui.button(emoji="🔌", style=discord.ButtonStyle.secondary, custom_id="vcmaster:disconnect", row=1)
    async def disconnect(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        channel = await get_vc(interaction)
        if channel is None:
            return
        await interaction.response.send_message(
            view=PickerView(DisconnectSelect(channel)), ephemeral=True
        )

    @discord.ui.button(emoji="👥", style=discord.ButtonStyle.secondary, custom_id="vcmaster:limit", row=1)
    async def limit(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        channel = await get_vc(interaction)
        if channel is None:
            return
        await interaction.response.send_modal(LimitModal(channel))


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
                except discord.HTTPException:
                    log.exception("Löschen von %s fehlgeschlagen", before.channel.id)
                database.delete_vc_channel(before.channel.id)

    async def create_channel(self, member: discord.Member, trigger: discord.VoiceChannel) -> None:
        category = (
            member.guild.get_channel(VC_MASTER_CATEGORY_ID) if VC_MASTER_CATEGORY_ID else trigger.category
        )
        try:
            channel = await member.guild.create_voice_channel(
                name=f"{member.display_name}'s VC",
                category=category,
                reason=f"VoiceMaster: Kanal für {member}",
            )
        except discord.HTTPException:
            log.exception("Kanal für %s konnte nicht erstellt werden", member)
            return
        database.save_vc_channel(channel.id, member.id)
        try:
            await member.move_to(channel)
        except discord.HTTPException:
            # Der User ist schon wieder weg: leeren Kanal nicht liegen lassen
            await channel.delete(reason="VoiceMaster: User nicht verschiebbar")
            database.delete_vc_channel(channel.id)

    @commands.command(name="vc-setup")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def vc_setup(self, ctx: commands.Context) -> None:
        """Postet das VoiceMaster-Interface (.vc-setup) in diesen Channel."""
        if not VC_MASTER_CREATE_CHANNEL_ID:
            await ctx.send("`VC_MASTER_CREATE_CHANNEL_ID` ist in der config.py noch nicht gesetzt.")
            return
        await ctx.send(embed=interface_embed(ctx.guild), view=VoiceInterface())
        # Der Aufruf selbst wird entfernt, damit nur das Interface stehen bleibt
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VcMaster(bot))
