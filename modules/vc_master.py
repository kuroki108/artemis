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

# Discord-Activities (Name -> Application-ID)
ACTIVITIES: dict[str, int] = {
    "Watch Together": 880218394199220334,
    "Poker Night": 755827207812677713,
    "Chess in the Park": 832012774040141894,
    "Checkers in the Park": 832013003968348200,
    "Sketch Heads": 902271654783242291,
    "Letter League": 879863686565621790,
    "SpellCast": 852509694341283871,
    "Blazing 8s": 832025144389533716,
    "Land-io": 903769130790969345,
    "Putt Party": 945737671223947305,
    "Bobble League": 947957217959759964,
    "Know What I Meme": 950505761862189096,
}

# Einträge im Interface-Embed (links / rechts), genau wie die Buttons
LEFT_COLUMN = [
    ("lock", "the voice channel"),
    ("unlock", "the voice channel"),
    ("ghost", "the voice channel"),
    ("reveal", "the voice channel"),
    ("claim", "the voice channel"),
]
RIGHT_COLUMN = [
    ("disconnect", "a member"),
    ("start", "an activity"),
    ("view", "channel information"),
    ("increase", "the user limit"),
    ("decrease", "the user limit"),
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


async def set_limit(interaction: discord.Interaction, delta: int) -> None:
    channel = await get_vc(interaction)
    if channel is None:
        return

    current = channel.user_limit
    if delta > 0:
        if current == 0:
            await reply(interaction, "Das Limit ist bereits unbegrenzt.")
            return
        new_limit = min(current + 1, MAX_LIMIT)
    else:
        # Ohne Limit startet „decrease“ bei der aktuellen Personenzahl
        new_limit = max((current or len(channel.members)) - 1, 1)
    await channel.edit(user_limit=new_limit)
    await reply(interaction, f"{channel.mention} hat jetzt ein Limit von **{new_limit}**.")


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


class ActivitySelect(discord.ui.Select):
    def __init__(self, channel: discord.VoiceChannel) -> None:
        super().__init__(
            placeholder="Wähle eine Activity …",
            options=[discord.SelectOption(label=n, value=str(i)) for n, i in ACTIVITIES.items()],
        )
        self.channel = channel

    async def callback(self, interaction: discord.Interaction) -> None:
        app_id = int(self.values[0])
        name = next(n for n, i in ACTIVITIES.items() if i == app_id)
        try:
            invite = await self.channel.create_invite(
                max_age=3600,
                target_type=discord.InviteTarget.embedded_application,
                target_application_id=app_id,
                reason=f"Activity gestartet von {interaction.user}",
            )
        except discord.HTTPException as e:
            await interaction.response.edit_message(
                embed=reply_embed(f"Die Activity konnte nicht gestartet werden: {e.text}"), view=None
            )
            return
        await interaction.response.edit_message(
            embed=reply_embed(f"**{name}** – klick auf den Link zum Starten:\n{invite.url}"), view=None
        )


class PickerView(discord.ui.View):
    """Kurzlebige View mit einem einzelnen Auswahlmenü."""

    def __init__(self, select: discord.ui.Item) -> None:
        super().__init__(timeout=120)
        self.add_item(select)


class VoiceInterface(discord.ui.View):
    """Persistente Buttons (feste custom_ids), zwei Reihen à fünf."""

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

    @discord.ui.button(emoji="👻", style=discord.ButtonStyle.secondary, custom_id="vcmaster:ghost", row=0)
    async def ghost(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        channel = await get_vc(interaction)
        if channel is None:
            return
        everyone = channel.overwrites_for(interaction.guild.default_role)
        everyone.view_channel = False
        await channel.set_permissions(interaction.guild.default_role, overwrite=everyone)
        owner = channel.overwrites_for(interaction.user)
        owner.view_channel = True
        await channel.set_permissions(interaction.user, overwrite=owner)
        await reply(interaction, f"{channel.mention} ist jetzt versteckt.")

    @discord.ui.button(emoji="👁️", style=discord.ButtonStyle.secondary, custom_id="vcmaster:reveal", row=0)
    async def reveal(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        channel = await get_vc(interaction)
        if channel is None:
            return
        everyone = channel.overwrites_for(interaction.guild.default_role)
        everyone.view_channel = None
        await channel.set_permissions(interaction.guild.default_role, overwrite=everyone)
        await reply(interaction, f"{channel.mention} ist wieder sichtbar.")

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

    @discord.ui.button(emoji="🎮", style=discord.ButtonStyle.secondary, custom_id="vcmaster:start", row=1)
    async def start(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        channel = await get_vc(interaction)
        if channel is None:
            return
        await interaction.response.send_message(
            view=PickerView(ActivitySelect(channel)), ephemeral=True
        )

    @discord.ui.button(emoji="ℹ️", style=discord.ButtonStyle.secondary, custom_id="vcmaster:view", row=1)
    async def view(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        channel = await get_vc(interaction, owner_only=False)
        if channel is None:
            return
        everyone = channel.overwrites_for(interaction.guild.default_role)
        embed = discord.Embed(title=channel.name, color=EMBED_COLOR)
        embed.add_field(name="Besitzer", value=f"<@{database.load_vc_owner(channel.id)}>")
        embed.add_field(name="Mitglieder", value=str(len(channel.members)))
        embed.add_field(name="Limit", value=str(channel.user_limit) if channel.user_limit else "unbegrenzt")
        embed.add_field(name="Gesperrt", value="ja" if everyone.connect is False else "nein")
        embed.add_field(name="Versteckt", value="ja" if everyone.view_channel is False else "nein")
        embed.add_field(name="Erstellt", value=discord.utils.format_dt(channel.created_at, "R"))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(emoji="➕", style=discord.ButtonStyle.secondary, custom_id="vcmaster:increase", row=1)
    async def increase(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await set_limit(interaction, +1)

    @discord.ui.button(emoji="➖", style=discord.ButtonStyle.secondary, custom_id="vcmaster:decrease", row=1)
    async def decrease(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await set_limit(interaction, -1)


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
