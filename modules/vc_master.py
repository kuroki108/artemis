from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable
from pathlib import Path
from typing import Any

import discord
from discord.ext import commands, tasks

import database
from config import (
    VC_MASTER,
    VC_MASTER_ALWAYS_ROLE_IDS,
    VC_MASTER_CATEGORY_ID,
    VC_MASTER_CHECK_SECONDS,
    VC_MASTER_COOLDOWN_SECONDS,
    VC_MASTER_CREATE_CHANNEL_ID,
    VC_MASTER_EMPTY_DELETE_SECONDS,
    VC_MASTER_DISCONNECT_EMOJI,
    VC_MASTER_LIMIT_EMOJI,
    VC_MASTER_LOCK_EMOJI,
    VC_MASTER_LOG_CHANNEL_ID,
    VC_MASTER_OWNER_GRACE_SECONDS,
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
    if interaction.response.is_done():
        await interaction.followup.send(embed=reply_embed(text), ephemeral=True)
    else:
        await interaction.response.send_message(embed=reply_embed(text), ephemeral=True)


async def safe(interaction: discord.Interaction, action: Awaitable[Any]) -> bool:
    """Führt eine Discord-Aktion aus; bei einem Fehler bekommt der Nutzer eine Meldung statt "Interaktion fehlgeschlagen"."""
    try:
        await action
    except discord.RateLimited as e:
        text = f"Zu viele Änderungen. Versuch es in {int(e.retry_after // 60) + 1} Minute(n) nochmal."
    except discord.NotFound:
        text = "Der Kanal existiert nicht mehr."
    except discord.HTTPException as e:
        log.warning("VoiceMaster-Aktion fehlgeschlagen: %s", e)
        text = "Das hat nicht geklappt. Versuch es später nochmal."
    else:
        return True
    await reply(interaction, text)
    return False


async def check_owner(interaction: discord.Interaction, channel: discord.VoiceChannel) -> bool:
    """Prüft, dass der Nutzer jetzt noch im Kanal ist und ihn besitzt (Besitzer können wechseln, Kanäle verschwinden)."""
    member = interaction.user
    if not isinstance(member, discord.Member) or member.voice is None or member.voice.channel != channel:
        await reply(interaction, "Du bist nicht mehr in diesem Kanal.")
        return False
    owner_id = database.load_vc_owner(channel.id)
    if owner_id is None:
        await reply(interaction, "Dieser Kanal wird nicht vom VoiceMaster verwaltet.")
        return False
    if owner_id != member.id:
        await reply(interaction, f"Nur <@{owner_id}> kann diesen Kanal verwalten.")
        return False
    return True


async def get_vc(interaction: discord.Interaction) -> discord.VoiceChannel | None:
    member = interaction.user
    voice = member.voice if isinstance(member, discord.Member) else None
    if voice is None or not isinstance(voice.channel, discord.VoiceChannel):
        await reply(interaction, "Du bist in keinem Sprachkanal.")
        return None
    return voice.channel if await check_owner(interaction, voice.channel) else None


class LimitModal(discord.ui.Modal, title="User-Limit ändern"):
    limit = discord.ui.TextInput(
        label=f"Neues Limit (0 = unbegrenzt, max. {MAX_LIMIT})", min_length=1, max_length=2, placeholder="z. B. 5"
    )

    def __init__(self, channel: discord.VoiceChannel) -> None:
        super().__init__()
        self.channel = channel
        self.limit.default = str(channel.user_limit)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await check_owner(interaction, self.channel):
            return
        value = self.limit.value.strip()
        if not value.isdigit() or not 0 <= int(value) <= MAX_LIMIT:
            await reply(interaction, f"Bitte gib eine Zahl zwischen 0 und {MAX_LIMIT} ein.")
            return
        new_limit = int(value)
        if not await safe(interaction, self.channel.edit(user_limit=new_limit)):
            return
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
        if not await check_owner(interaction, self.channel):
            return
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
        if not await check_owner(interaction, self.channel):
            return
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
            if not await safe(interaction, target.move_to(None, reason=f"Getrennt von {interaction.user}")):
                return
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
        async def apply() -> None:
            everyone = channel.overwrites_for(interaction.guild.default_role)
            everyone.connect = False
            await channel.set_permissions(interaction.guild.default_role, overwrite=everyone)
            # Der Besitzer darf immer wieder rein
            owner = channel.overwrites_for(interaction.user)
            owner.connect = True
            await channel.set_permissions(interaction.user, overwrite=owner)

        if not await safe(interaction, apply()):
            return
        await reply(interaction, f"{channel.mention} wurde gesperrt.")
        await vc_log(interaction.client, f"{interaction.user.mention} hat {channel.mention} gesperrt.")

    @discord.ui.button(emoji=VC_MASTER_UNLOCK_EMOJI, style=discord.ButtonStyle.secondary, custom_id="vcmaster:unlock")
    async def unlock(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        channel = await get_vc(interaction)
        if channel is None:
            return
        everyone = channel.overwrites_for(interaction.guild.default_role)
        # Zurück auf den Wert der Kategorie (die Overwrites wurden beim Erstellen von dort übernommen), nicht auf neutral
        category = channel.category
        everyone.connect = category.overwrites_for(interaction.guild.default_role).connect if category else None
        if not await safe(interaction, channel.set_permissions(interaction.guild.default_role, overwrite=everyone)):
            return
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
        # Erstellen läuft nacheinander, damit Cooldown und "ein Kanal pro Nutzer" nicht umgangen werden können
        self.create_lock = asyncio.Lock()
        self.cooldowns: dict[int, float] = {}  # user_id -> Zeitpunkt (monotonic), ab dem wieder erlaubt
        self.blocked_until = 0.0  # Discord-Rate-Limit fürs Erstellen: bis dahin gar nicht erst versuchen
        self.empty_since: dict[int, float] = {}  # channel_id -> Zeitpunkt (monotonic), seit dem leer
        self.owner_absent_since: dict[int, float] = {}  # channel_id -> Zeitpunkt (monotonic), seit dem der Besitzer fehlt

    async def cog_load(self) -> None:
        # Registriert die View beim Start, damit alte Buttons weiter reagieren
        self.bot.add_view(VoiceInterface())
        self.sweep.start()

    async def cog_unload(self) -> None:
        self.sweep.cancel()

    @tasks.loop(seconds=VC_MASTER_CHECK_SECONDS)
    async def sweep(self) -> None:
        """Gleicht die DB mit Discord ab: löscht lange leere Kanäle, vergibt verwaiste Kanäle neu.

        Verlässt sich nicht auf Voice-Events, damit verpasste Events (Reconnect, Absturz) nichts liegen lassen.
        """
        now = time.monotonic()
        self.cooldowns = {user_id: until for user_id, until in self.cooldowns.items() if until > now}
        for channel_id, owner_id in database.load_vc_channels().items():
            try:
                await self.check_channel(channel_id, owner_id, now)
            except Exception:
                # Sonst würde die Schleife dauerhaft stoppen
                log.exception("Aufräumen von %s fehlgeschlagen", channel_id)

    async def check_channel(self, channel_id: int, owner_id: int, now: float) -> None:
        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            # Bei einer Server-Störung fehlt der Kanal im Cache, ohne gelöscht zu sein
            if channel is None and not any(guild.unavailable for guild in self.bot.guilds):
                self.forget(channel_id)
            return

        if channel.members:
            self.empty_since.pop(channel_id, None)
            if owner_id in {member.id for member in channel.members}:
                self.owner_absent_since.pop(channel_id, None)
            elif now - self.owner_absent_since.setdefault(channel_id, now) >= VC_MASTER_OWNER_GRACE_SECONDS:
                await self.transfer_ownership(channel, owner_id)
            return

        self.owner_absent_since.pop(channel_id, None)
        since = self.empty_since.setdefault(channel_id, now)
        if now - since < VC_MASTER_EMPTY_DELETE_SECONDS:
            return
        try:
            await channel.delete(reason="VoiceMaster: Kanal leer")
        except discord.NotFound:
            pass
        except (discord.HTTPException, discord.RateLimited):
            # Eintrag bleibt, der nächste Durchlauf versucht es erneut
            log.exception("Löschen von %s fehlgeschlagen", channel_id)
            return
        else:
            await vc_log(self.bot, f"**{channel.name}** wurde gelöscht, weil er leer war.")
        self.forget(channel_id)

    def forget(self, channel_id: int) -> None:
        self.empty_since.pop(channel_id, None)
        self.owner_absent_since.pop(channel_id, None)
        database.delete_vc_channel(channel_id)

    async def transfer_ownership(self, channel: discord.VoiceChannel, old_owner_id: int) -> None:
        """Gibt einen Kanal, dessen Besitzer ihn verlassen hat, an ein anderes Mitglied weiter."""
        # Nicht an jemanden, der schon einen eigenen Kanal hat (ein Kanal pro Nutzer)
        new_owner = next(
            (m for m in channel.members if not m.bot and not database.load_vc_channel_ids_by_owner(m.id)), None
        )
        # Der Besitzer kann inzwischen schon gewechselt haben (Event und Sweep können sich überschneiden)
        if new_owner is None or database.load_vc_owner(channel.id) != old_owner_id:
            return
        # Der Besitzer kann inzwischen zurück sein (z. B. kurz in den Erstellen-Kanal gewechselt und wieder verschoben worden)
        if any(member.id == old_owner_id for member in channel.members):
            return
        database.save_vc_channel(channel.id, new_owner.id)
        self.owner_absent_since.pop(channel.id, None)
        try:
            # Der neue Besitzer muss auch einen gesperrten Kanal wieder betreten können, der alte nicht mehr
            overwrite = channel.overwrites_for(new_owner)
            overwrite.connect = True
            overwrite.view_channel = True
            await channel.set_permissions(new_owner, overwrite=overwrite)
            # set_permissions akzeptiert nur Member/Role, kein discord.Object
            if (old_owner := channel.guild.get_member(old_owner_id)) is not None:
                await channel.set_permissions(old_owner, overwrite=None)
        except (discord.HTTPException, discord.RateLimited):
            log.exception("Rechte in %s nach Besitzer-Wechsel nicht angepasst", channel.id)
        try:
            await channel.send(f"{new_owner.mention} ist jetzt Besitzer dieses Kanals.")
        except discord.HTTPException:
            pass
        await vc_log(self.bot, f"{channel.mention} gehört jetzt {new_owner.mention} (vorher <@{old_owner_id}>).")

    @sweep.before_loop
    async def before_sweep(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        if before.channel == after.channel:
            return

        if after.channel:
            # Jemand ist (wieder) im Kanal, das Löschen wird abgebrochen
            self.empty_since.pop(after.channel.id, None)
            if after.channel.id in self.owner_absent_since and database.load_vc_owner(after.channel.id) == member.id:
                self.owner_absent_since.pop(after.channel.id, None)

        if VC_MASTER_CREATE_CHANNEL_ID and after.channel and after.channel.id == VC_MASTER_CREATE_CHANNEL_ID:
            await self.create_channel(member, after.channel)

        if before.channel and not before.channel.members:
            if database.load_vc_owner(before.channel.id) is not None:
                # Gelöscht wird erst nach VC_MASTER_EMPTY_DELETE_SECONDS in `sweep`
                self.empty_since.setdefault(before.channel.id, time.monotonic())
        elif before.channel and database.load_vc_owner(before.channel.id) == member.id:
            # Übergabe erst nach VC_MASTER_OWNER_GRACE_SECONDS in `sweep`, falls der Besitzer zurückkommt
            self.owner_absent_since.setdefault(before.channel.id, time.monotonic())

    async def deny(self, member: discord.Member) -> None:
        """Wirft den Nutzer aus dem Erstellen-Kanal (ohne Nachricht, der Bot schreibt keine DMs)."""
        try:
            await member.move_to(None, reason="VoiceMaster: Erstellen nicht möglich")
        except (discord.HTTPException, discord.RateLimited):
            log.warning("%s konnte nicht aus dem Erstellen-Kanal getrennt werden", member)

    async def create_channel(self, member: discord.Member, trigger: discord.VoiceChannel) -> None:
        async with self.create_lock:
            # Der Nutzer kann inzwischen schon wieder weg sein (z. B. mehrfach schnell beigetreten)
            if member.voice is None or member.voice.channel != trigger:
                return

            # Nur ein Kanal pro Nutzer: vorhandenen wiederverwenden statt einen zweiten anzulegen
            for channel_id in database.load_vc_channel_ids_by_owner(member.id):
                existing = member.guild.get_channel(channel_id)
                if isinstance(existing, discord.VoiceChannel):
                    try:
                        await member.move_to(existing)
                    except (discord.HTTPException, discord.RateLimited):
                        log.exception("%s konnte nicht in den vorhandenen Kanal verschoben werden", member)
                    return
                database.delete_vc_channel(channel_id)  # Kanal existiert nicht mehr

            now = time.monotonic()
            until = self.cooldowns.get(member.id, 0.0)
            if until > now:
                await self.deny(member)
                return
            if self.blocked_until > now:
                await self.deny(member)
                return

            self.cooldowns[member.id] = now + VC_MASTER_COOLDOWN_SECONDS
            await self._create(member, trigger)

    async def _create(self, member: discord.Member, trigger: discord.VoiceChannel) -> None:
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
            # Bis dahin versucht der Bot es gar nicht erst, andere Nutzer laufen sonst ins gleiche Limit
            self.blocked_until = time.monotonic() + e.retry_after
            self.cooldowns.pop(member.id, None)
            await vc_log(self.bot, f"Kanal für {member.mention} nicht erstellt: Discord-Limit für neue Kanäle erreicht (wieder möglich in ca. {int(e.retry_after // 3600) + 1} Std.).")
            await self.deny(member)
            return
        except discord.HTTPException:
            log.exception("Kanal für %s konnte nicht erstellt werden", member)
            self.cooldowns.pop(member.id, None)
            return
        database.save_vc_channel(channel.id, member.id)
        await vc_log(self.bot, f"{member.mention} hat {channel.mention} erstellt.")
        try:
            await member.move_to(channel)
        except (discord.HTTPException, discord.RateLimited):
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
