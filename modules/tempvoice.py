from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Awaitable
from pathlib import Path
from typing import Any

import discord
from discord.ext import commands

from config import (
    TEMPVOICE_ALERT_CHANNEL_ID,
    TEMPVOICE_CATEGORY_ID,
    TEMPVOICE_CLOSE_EMOJI,
    TEMPVOICE_CREATE_COOLDOWN,
    TEMPVOICE_CREATOR_CHANNEL_ID,
    TEMPVOICE_DEFAULT_LIMIT,
    TEMPVOICE_EMERGENCY_EMOJI,
    TEMPVOICE_EMOJI,
    TEMPVOICE_LIMIT_EMOJI,
    TEMPVOICE_LOG_CHANNEL_ID,
    TEMPVOICE_OPEN_EMOJI,
    TEMPVOICE_RENAME_EMOJI,
    TEMPVOICE_STAFF_ROLE_ID,
)
from database import (
    TempVoiceRecord,
    delete_tempvoice_channel,
    load_tempvoice_channels,
    save_tempvoice_channel,
)

log = logging.getLogger(__name__)

# Optionales Bild unter dem Interface-Embed; fehlt die Datei, wird ohne Bild gepostet.
BANNER_PATH = Path(__file__).resolve().parent.parent / "assets" / "vc-interface.jpg"
BANNER_NAME = "vc-interface.jpg"

# Standardname neuer Kanäle; {name} wird zum Username des Besitzers.
CHANNEL_NAME = "⊹ㆍ {name}'s vc"

# Discord erlaubt nur 2 Namensänderungen pro Kanal alle 10 Minuten
RENAME_LIMIT = 2
RENAME_WINDOW = 600
# Wie oft pro Kanal das Staff-Team alarmiert werden kann (Sekunden)
EMERGENCY_COOLDOWN = 300


class TVError(Exception):
    """Fehler, dessen Nachricht direkt an den Nutzer geht."""


def default_name(member: discord.Member) -> str:
    return CHANNEL_NAME.format(name=member.name)


def owner_overwrite() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(view_channel=True, connect=True, speak=True)


def interface_message(guild: discord.Guild) -> dict[str, Any]:
    creator_url = f"https://discord.com/channels/{guild.id}/{TEMPVOICE_CREATOR_CHANNEL_ID}"
    embed = discord.Embed(
        description=(
            f"# {TEMPVOICE_EMOJI} __VoiceMaster Interface__\n"
            f"<:b9_lunaRpalace:1536504134457499648> Klick [hier]({creator_url}) um einen VC zu erstellen.\n\n"
            f"{TEMPVOICE_CLOSE_EMOJI} `lock` the voice channel\n"
            f"{TEMPVOICE_OPEN_EMOJI} `unlock` the voice channel\n"
            f"{TEMPVOICE_LIMIT_EMOJI} `change` user limit\n"
            f"{TEMPVOICE_RENAME_EMOJI} `rename` the voice channel\n"
            f"{TEMPVOICE_EMERGENCY_EMOJI} `emergency` alert the staff"
        ),
        color=discord.Color.light_embed(),
    )
    embed.set_footer(text="Nutze die Buttons unten, um deinen Sprachkanal zu verwalten.")
    # Das Bild ist die Trennlinie über dem Footer
    if not BANNER_PATH.is_file():
        return {"embed": embed}
    embed.set_image(url=f"attachment://{BANNER_NAME}")
    return {"embed": embed, "file": discord.File(BANNER_PATH, filename=BANNER_NAME)}


class RenameModal(discord.ui.Modal, title="Kanal umbenennen"):
    name = discord.ui.TextInput(
        label="Neuer Kanalname",
        placeholder="Leer lassen, um den Standardnamen zu verwenden",
        required=False,
        max_length=100,
    )

    def __init__(self, cog: TempVoice) -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.respond(interaction, self.cog.rename(interaction.user, self.name.value))


class LimitModal(discord.ui.Modal, title="Nutzerlimit ändern"):
    # max_length=2 begrenzt auf 0-99
    limit = discord.ui.TextInput(label="Nutzerlimit (0 = unbegrenzt)", placeholder="0 - 99", max_length=2)

    def __init__(self, cog: TempVoice) -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = self.limit.value.strip()
        # isdecimal statt isdigit: "²" ist eine Ziffer, aber int("²") crasht
        if not raw.isdecimal():
            await interaction.response.send_message("Bitte gib eine Zahl von 0 bis 99 ein.", ephemeral=True)
            return
        await self.cog.respond(interaction, self.cog.set_limit(interaction.user, int(raw)))


class EmergencyModal(discord.ui.Modal, title="Staff-Team alarmieren"):
    reason = discord.ui.TextInput(
        label="Was ist passiert?",
        style=discord.TextStyle.paragraph,
        placeholder="Beschreibe kurz das Problem (optional)",
        required=False,
        max_length=500,
    )

    def __init__(self, cog: TempVoice) -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.respond(interaction, self.cog.emergency(interaction.user, self.reason.value))


class InterfaceView(discord.ui.View):

    def __init__(self, cog: TempVoice) -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(emoji=TEMPVOICE_CLOSE_EMOJI, style=discord.ButtonStyle.secondary,
                        custom_id="tempvoice:close")
    async def close(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.cog.respond(interaction, self.cog.set_locked(interaction.user, True))

    @discord.ui.button(emoji=TEMPVOICE_OPEN_EMOJI, style=discord.ButtonStyle.secondary,
                       custom_id="tempvoice:open")
    async def open(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.cog.respond(interaction, self.cog.set_locked(interaction.user, False))

    @discord.ui.button(emoji=TEMPVOICE_LIMIT_EMOJI, style=discord.ButtonStyle.secondary,
                       custom_id="tempvoice:limit")
    async def limit(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.cog.open_modal(interaction, LimitModal(self.cog), owner_only=True)

    @discord.ui.button(emoji=TEMPVOICE_RENAME_EMOJI, style=discord.ButtonStyle.secondary,
                       custom_id="tempvoice:rename")
    async def rename(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.cog.open_modal(interaction, RenameModal(self.cog), owner_only=True)

    @discord.ui.button(emoji=TEMPVOICE_EMERGENCY_EMOJI, style=discord.ButtonStyle.secondary,
                       custom_id="tempvoice:emergency")
    async def emergency(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.cog.open_modal(interaction, EmergencyModal(self.cog), owner_only=False)


class TempVoice(commands.Cog):
    """Temporäre Sprachkanäle mit Interface und Notfall-Button."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.view = InterfaceView(self)
        # Zustand im Speicher, nach jeder Änderung in SQLite gespiegelt
        self.channels: dict[int, TempVoiceRecord] = {}
        self.rename_history: dict[int, deque[float]] = {}
        self.emergency_cooldowns: dict[int, float] = {}
        self.last_created: dict[int, float] = {}  # User-ID -> Zeitpunkt der letzten Kanal-Erstellung
        self.creating: set[int] = set()
        self._startup_task: asyncio.Task[None] | None = None

    async def cog_load(self) -> None:
        if not TEMPVOICE_STAFF_ROLE_ID or not TEMPVOICE_ALERT_CHANNEL_ID:
            log.warning("TEMPVOICE_STAFF_ROLE_ID/TEMPVOICE_ALERT_CHANNEL_ID sind nicht gesetzt, "
                        "der Notfall-Button funktioniert erst danach")
        if not TEMPVOICE_LOG_CHANNEL_ID:
            log.warning("TEMPVOICE_LOG_CHANNEL_ID ist nicht gesetzt, TempVoice-Ereignisse werden nicht geloggt")
        self.channels = load_tempvoice_channels()
        self.bot.add_view(self.view)
        self._startup_task = asyncio.create_task(self._startup_cleanup())

    async def cog_unload(self) -> None:
        self.view.stop()
        if self._startup_task:
            self._startup_task.cancel()

    # Hilfsfunktionen

    def current_temp(self, member: discord.Member) -> tuple[discord.VoiceChannel, TempVoiceRecord]:
        channel = member.voice.channel if member.voice else None
        data = self.channels.get(channel.id) if channel else None
        if not isinstance(channel, discord.VoiceChannel) or data is None:
            raise TVError("Du musst dich in einem temporären Sprachkanal befinden.")
        return channel, data

    def owned_temp(self, member: discord.Member) -> tuple[discord.VoiceChannel, TempVoiceRecord]:
        channel, data = self.current_temp(member)
        if data.owner_id != member.id and not member.guild_permissions.manage_channels:
            raise TVError("Nur der Besitzer dieses Kanals kann das ändern.")
        return channel, data

    async def respond(self, interaction: discord.Interaction, action: Awaitable[str]) -> None:
        """Führt eine Aktion aus und antwortet dem Nutzer ephemer mit dem Ergebnis."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            message = await action
        except TVError as error:
            message = str(error)
        except discord.HTTPException:
            log.exception("TempVoice-Aktion fehlgeschlagen")
            message = "Discord hat die Aktion abgelehnt. Fehlen dem Bot Berechtigungen?"
        await interaction.followup.send(message, ephemeral=True)

    async def open_modal(self, interaction: discord.Interaction, modal: discord.ui.Modal, *, owner_only: bool) -> None:
        try:
            (self.owned_temp if owner_only else self.current_temp)(interaction.user)  # type: ignore[arg-type]
        except TVError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        await interaction.response.send_modal(modal)

    def _rename_wait(self, channel_id: int) -> float:
        history = self.rename_history.setdefault(channel_id, deque())
        now = time.monotonic()
        while history and now - history[0] >= RENAME_WINDOW:
            history.popleft()
        return 0 if len(history) < RENAME_LIMIT else RENAME_WINDOW - (now - history[0])

    def forget(self, channel_id: int) -> None:
        """Entfernt einen Kanal aus Speicher und Datenbank."""
        self.channels.pop(channel_id, None)
        self.rename_history.pop(channel_id, None)
        self.emergency_cooldowns.pop(channel_id, None)
        delete_tempvoice_channel(channel_id)

    async def log_event(self, title: str, description: str) -> None:
        """Schreibt ein Ereignis in den Log-Kanal; Fehler landen nur in der Konsole."""
        channel = self.bot.get_channel(TEMPVOICE_LOG_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            return
        embed = discord.Embed(title=title, description=description,
                              color=discord.Color.light_embed(), timestamp=discord.utils.utcnow())
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as e:
            log.warning("TempVoice-Log konnte nicht gesendet werden: %s", e)

    # Kanal-Lebenszyklus

    async def create_temp(self, member: discord.Member, creator: discord.VoiceChannel) -> None:
        if member.id in self.creating:
            return
        self.creating.add(member.id)
        try:
            # Cooldown gegen Kanal-Spam: wer im Creator-Kanal wartet, bekommt den Kanal nach Ablauf
            last = self.last_created.get(member.id)
            if last is not None and (wait := last + TEMPVOICE_CREATE_COOLDOWN - time.monotonic()) > 0:
                await asyncio.sleep(wait)
                if member.voice is None or member.voice.channel != creator:
                    return
            self.last_created[member.id] = time.monotonic()

            guild = member.guild
            category = guild.get_channel(TEMPVOICE_CATEGORY_ID)
            if not isinstance(category, discord.CategoryChannel):
                category = creator.category

            overwrites = dict(category.overwrites) if category else {}
            overwrites[member] = owner_overwrite()
            channel = await guild.create_voice_channel(
                name=default_name(member),
                category=category,
                user_limit=TEMPVOICE_DEFAULT_LIMIT,
                overwrites=overwrites,
                reason=f"TempVoice: Kanal für {member}",
            )
            data = TempVoiceRecord(channel.id, member.id)
            self.channels[channel.id] = data
            save_tempvoice_channel(data)
            await self.log_event("Kanal erstellt", f"Kanal: {channel.mention} (`{channel.name}`)\n"
                                                   f"Besitzer: {member.mention}")

            try:
                await member.move_to(channel)
            except discord.HTTPException:
                await self.delete_temp(channel, "Besitzer hat den Sprachchat vorher verlassen")
        except discord.HTTPException:
            log.exception("Temporärer Kanal für %s konnte nicht erstellt werden", member)
        finally:
            self.creating.discard(member.id)

    async def delete_temp(self, channel: discord.VoiceChannel, reason: str = "Kanal ist leer") -> None:
        self.forget(channel.id)
        try:
            await channel.delete(reason=f"TempVoice: {reason}")
        except discord.NotFound:
            pass
        except discord.HTTPException:
            log.exception("Temporärer Kanal %s konnte nicht gelöscht werden", channel.id)
            return
        await self.log_event("Kanal gelöscht", f"Kanal: `{channel.name}`\nGrund: {reason}")

    async def transfer(self, channel: discord.VoiceChannel, data: TempVoiceRecord, new_owner: discord.Member) -> None:
        old_id = data.owner_id
        old_owner = channel.guild.get_member(old_id)
        data.owner_id = new_owner.id
        save_tempvoice_channel(data)
        try:
            # Ohne seinen Overwrite kommt der alte Besitzer in einen geschlossenen Kanal nicht zurück
            if old_owner is not None:
                await channel.set_permissions(old_owner, overwrite=None, reason="TempVoice: Besitzerwechsel")
            await channel.set_permissions(new_owner, overwrite=owner_overwrite(), reason="TempVoice: Besitzerwechsel")
        except discord.HTTPException as e:
            # Besitz im Bot ist trotzdem übertragen, nur die Kanalrechte fehlen
            log.warning("Rechte beim Besitzerwechsel in %s nicht gesetzt: %s", channel.id, e)
        await self.log_event("Besitzer gewechselt", f"Kanal: {channel.mention}\n"
                                                    f"Vorher: <@{old_id}>\nJetzt: {new_owner.mention}")

    async def _startup_cleanup(self) -> None:
        await self.bot.wait_until_ready()
        for channel_id, data in list(self.channels.items()):
            channel = self.bot.get_channel(channel_id)
            if not isinstance(channel, discord.VoiceChannel):
                self.forget(channel_id)
                continue
            humans = [m for m in channel.members if not m.bot]
            if not humans:
                await self.delete_temp(channel)
            elif data.owner_id not in {m.id for m in humans}:
                await self.transfer(channel, data, humans[0])

        # Nutzer, die während der Downtime den Creator-Kanal betreten haben
        creator = self.bot.get_channel(TEMPVOICE_CREATOR_CHANNEL_ID)
        if isinstance(creator, discord.VoiceChannel):
            for member in creator.members:
                if not member.bot:
                    await self.create_temp(member, creator)

    # Listener

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState) -> None:
        if before.channel == after.channel:
            return

        if isinstance(before.channel, discord.VoiceChannel) and (data := self.channels.get(before.channel.id)):
            humans = [m for m in before.channel.members if not m.bot]
            if not humans:
                await self.delete_temp(before.channel)
            elif data.owner_id == member.id:
                await self.transfer(before.channel, data, humans[0])

        if (not member.bot and isinstance(after.channel, discord.VoiceChannel)
                and after.channel.id == TEMPVOICE_CREATOR_CHANNEL_ID):
            await self.create_temp(member, after.channel)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if channel.id in self.channels:
            self.forget(channel.id)
            await self.log_event("Kanal manuell gelöscht", f"Kanal: `{channel.name}`")

    # Aktionen

    async def set_locked(self, member: discord.Member, locked: bool) -> str:
        channel, data = self.owned_temp(member)
        if data.locked == locked:
            return "Der Kanal ist bereits " + ("geschlossen." if locked else "offen.")

        # "Verbinden" prüft Discord nur beim Beitreten: wer drin ist, bleibt, wer geht, kommt nicht
        # wieder rein. Nur der Besitzer hat einen eigenen Overwrite, verliert ihn aber beim Rausgehen.
        everyone = channel.guild.default_role
        overwrite = channel.overwrites_for(everyone)
        overwrite.connect = False if locked else None
        await channel.set_permissions(everyone, overwrite=overwrite, reason=f"TempVoice: {member} hat den Kanal "
                                      + ("geschlossen" if locked else "geöffnet"))
        data.locked = locked
        save_tempvoice_channel(data)
        await self.log_event("Kanal geschlossen" if locked else "Kanal geöffnet",
                             f"Kanal: {channel.mention}\nVon: {member.mention}")
        if locked:
            return "Der Kanal ist jetzt geschlossen. Niemand kann mehr beitreten, auch nicht, wer ihn verlässt."
        return "Der Kanal ist jetzt offen. Jeder kann beitreten."

    async def rename(self, member: discord.Member, name: str) -> str:
        channel, data = self.owned_temp(member)
        owner = channel.guild.get_member(data.owner_id) or member
        new_name = name.strip() or default_name(owner)
        if new_name == channel.name:
            return f"Der Kanal heißt bereits **{new_name}**."
        if wait := self._rename_wait(channel.id):
            retry = int(time.time() + wait)
            raise TVError(f"Discord erlaubt nur {RENAME_LIMIT} Umbenennungen alle 10 Minuten. "
                          f"Versuche es <t:{retry}:R> erneut.")
        self.rename_history[channel.id].append(time.monotonic())
        old_name = channel.name
        await channel.edit(name=new_name, reason=f"TempVoice: umbenannt von {member}")
        await self.log_event("Kanal umbenannt", f"Kanal: {channel.mention}\nVorher: `{old_name}`\n"
                                                f"Jetzt: `{new_name}`\nVon: {member.mention}")
        return f"Der Kanal heißt jetzt **{new_name}**."

    async def set_limit(self, member: discord.Member, limit: int) -> str:
        channel, _ = self.owned_temp(member)
        await channel.edit(user_limit=limit, reason=f"TempVoice: Limit geändert von {member}")
        await self.log_event("Limit geändert", f"Kanal: {channel.mention}\nLimit: {limit or 'unbegrenzt'}\n"
                                               f"Von: {member.mention}")
        return "Das Nutzerlimit wurde entfernt." if limit == 0 else f"Das Nutzerlimit ist jetzt **{limit}**."

    async def emergency(self, member: discord.Member, reason: str) -> str:
        channel, data = self.current_temp(member)
        guild = channel.guild
        role = guild.get_role(TEMPVOICE_STAFF_ROLE_ID)
        alert_channel = guild.get_channel(TEMPVOICE_ALERT_CHANNEL_ID)
        if role is None or not isinstance(alert_channel, discord.TextChannel):
            raise TVError("Der Notfall-Button ist noch nicht eingerichtet. Bitte wende dich direkt an das Team.")

        now = time.monotonic()
        last = self.emergency_cooldowns.get(channel.id)
        if last is not None and now - last < EMERGENCY_COOLDOWN:
            retry = int(time.time() + EMERGENCY_COOLDOWN - (now - last))
            raise TVError(f"Das Team wurde für diesen Kanal bereits alarmiert. Erneut möglich <t:{retry}:R>.")
        self.emergency_cooldowns[channel.id] = now

        # Der Melder ist selbst im Kanal, die Liste ist also nie leer
        members = ", ".join(m.mention for m in channel.members)
        embed = discord.Embed(
            title="Notfall in einem Sprachkanal",
            description=reason.strip() or "*Kein Grund angegeben*",
            color=discord.Color.light_embed(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Kanal", value=f"{channel.mention} ({channel.name})", inline=False)
        embed.add_field(name="Gemeldet von", value=f"{member.mention} (`{member.id}`)")
        embed.add_field(name="Besitzer", value=f"<@{data.owner_id}>")
        embed.add_field(name=f"Im Kanal ({len(channel.members)})", value=members[:1024], inline=False)

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Zum Kanal", url=channel.jump_url))
        try:
            alert = await alert_channel.send(content=role.mention, embed=embed, view=view)
        except discord.HTTPException:
            self.emergency_cooldowns.pop(channel.id, None)
            raise
        await self.log_event("Notfall gemeldet", f"Kanal: {channel.mention}\nVon: {member.mention}\n"
                                                 f"Grund: {embed.description}\n[Zur Meldung]({alert.jump_url})")
        return "Das Staff-Team wurde alarmiert und kümmert sich so schnell wie möglich darum."

    # Admin-Befehl

    @commands.command(name="tempvoice-setup")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def tempvoice_setup(self, ctx: commands.Context) -> None:
        """Postet das Interface in diesen Kanal."""
        await ctx.channel.send(view=self.view, **interface_message(ctx.guild))
        await self.log_event("Interface gepostet", f"Kanal: {ctx.channel.mention}\nVon: {ctx.author.mention}")
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot) -> None:
    if not TEMPVOICE_CREATOR_CHANNEL_ID:
        log.warning("TEMPVOICE_CREATOR_CHANNEL_ID ist nicht gesetzt, TempVoice wird übersprungen")
        return
    await bot.add_cog(TempVoice(bot))
