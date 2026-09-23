import asyncio
import json
import logging
import random
import sqlite3
from pathlib import Path

import discord
from discord.ext import commands

from config import ADMIN_ROLES, COUNTING_CHANNEL_ID, MATH_PRO_ROLE_ID
import database

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
COUNTING_QUOTES_FILE = DATA_DIR / "counting_quotes.json"


class Counting(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.count = 0
        self.last_user_id: int | None = None
        self.role_holder_id: int | None = None
        self.quotes: list[str] = []
        self._state_lock = asyncio.Lock()

    async def cog_load(self) -> None:
        database.initialize_database()
        state = database.load_state()
        self.count = state["count"]
        self.last_user_id = state["last_user_id"]
        self.role_holder_id = state["role_holder_id"]
        self.quotes = self._load_quotes()

    @staticmethod
    def _load_quotes() -> list[str]:
        try:
            data = json.loads(COUNTING_QUOTES_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            log.warning("counting_quotes.json konnte nicht geladen werden: %s", exc)
            return []

        quotes = data.get("falsche_zahl", []) if isinstance(data, dict) else []
        if not isinstance(quotes, list):
            return []
        return [q for q in quotes if isinstance(q, str) and q.strip()]

    def _state(self) -> dict[str, int | None]:
        return {
            "count": self.count,
            "last_user_id": self.last_user_id,
            "role_holder_id": self.role_holder_id,
        }

    async def _save_state_locked(self) -> None:
        try:
            database.save_state(self._state())
        except (OSError, sqlite3.Error):
            log.exception("Counting-Zustand konnte nicht gespeichert werden.")

    async def _save_state(self) -> None:
        async with self._state_lock:
            await self._save_state_locked()

    async def _reset(self) -> None:
        self.count = 0
        self.last_user_id = None
        await self._save_state()

    async def _safe_reaction(self, message: discord.Message, emoji: str) -> None:
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            log.warning("Reaktion konnte nicht gesetzt werden.", exc_info=True)

    async def _safe_send(
        self, channel: discord.abc.Messageable, content: str
    ) -> None:
        try:
            await channel.send(content)
        except discord.HTTPException:
            log.warning("Counting-Nachricht konnte nicht gesendet werden.", exc_info=True)

    async def _send_quote(self, channel: discord.abc.Messageable) -> None:
        if self.quotes:
            await self._safe_send(channel, random.choice(self.quotes))

    async def _transfer_role(self, member: discord.Member) -> None:
        if MATH_PRO_ROLE_ID is None:
            return

        guild = member.guild
        me = guild.me
        role = guild.get_role(MATH_PRO_ROLE_ID)
        if role is None:
            log.warning("Rolle %s nicht gefunden.", MATH_PRO_ROLE_ID)
            return
        if me is None or not me.guild_permissions.manage_roles:
            log.warning("Bot hat keine Berechtigung zum Verwalten von Rollen.")
            return
        if role >= me.top_role:
            log.warning("Rolle %s steht über der höchsten Bot-Rolle.", role.id)
            return

        old_id = self.role_holder_id
        if old_id == member.id and role in member.roles:
            return  # hat die Rolle bereits

        try:
            await member.add_roles(role, reason="Falsche Zahl beim Counting")
        except discord.HTTPException:
            log.warning("Rollenwechsel fehlgeschlagen.", exc_info=True)
            return

        self.role_holder_id = member.id
        await self._save_state()

        if old_id is not None and old_id != member.id:
            old_member = guild.get_member(old_id)
            if old_member is None:
                try:
                    old_member = await guild.fetch_member(old_id)
                except discord.HTTPException:
                    old_member = None  # nicht mehr auf dem Server
            if old_member is not None and role in old_member.roles:
                try:
                    await old_member.remove_roles(role, reason="Neuer Verzähler")
                except discord.HTTPException:
                    log.warning("Alte Counting-Rolle konnte nicht entfernt werden.", exc_info=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id != COUNTING_CHANNEL_ID:
            return

        try:
            number = int(message.content.strip())
        except ValueError:
            return  # keine Zahl -> ignorieren, kein Reset

        expected = self.count + 1

        # Gleicher User zweimal hintereinander -> Reset (keine Rolle)
        if self.last_user_id is not None and message.author.id == self.last_user_id:
            await self._reset()
            await self._safe_reaction(message, "❌")
            await self._safe_send(
                message.channel,
                f"{message.author.mention}, du warst bereits dran. "
                f"Zaehlung zurueckgesetzt. Naechste Zahl: **1**"
            )
            return

        # Falsche Zahl -> Reset, Spruch, Rolle
        if number != expected:
            await self._reset()
            await self._safe_reaction(message, "❌")
            await self._safe_send(
                message.channel,
                f"Falsche Zahl! Erwartet wurde **{expected}**. "
                f"Zaehlung zurueckgesetzt. Naechste Zahl: **1**"
            )
            await self._send_quote(message.channel)
            await self._transfer_role(message.author)
            return

        # Richtig
        self.count = number
        self.last_user_id = message.author.id
        await self._save_state()
        await self._safe_reaction(message, "✅")

    @commands.command(name="set")
    @commands.has_any_role(*ADMIN_ROLES)
    async def set_number(self, ctx: commands.Context, number: int):
        """Setzt den aktuellen Zählerstand (die nächste erwartete Zahl ist number+1)."""
        if number < 0:
            await ctx.send("Die Zahl darf nicht negativ sein.")
            return

        self.count = number
        self.last_user_id = None  # Reset, damit niemand fälschlich als "doppelt dran" gilt
        await self._save_state()

        await ctx.send(
            f"Zählerstand wurde auf **{number}** gesetzt. "
            f"Nächste erwartete Zahl: **{number + 1}**"
        )

    @set_number.error
    async def set_number_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingAnyRole):
            await ctx.send("Dafür brauchst du Administrator-Rechte.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Bitte eine gültige Zahl angeben, z. B. `!set 41`.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Bitte eine gültige Zahl angeben, z. B. `!set 41`.")
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(Counting(bot))