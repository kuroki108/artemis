import asyncio
import json
import random
from pathlib import Path

import discord
from discord.ext import commands

from config import ADMIN_ROLES, COUNTING_CHANNEL_ID
import database


COUNTING_QUOTES_FILE = Path(__file__).resolve().parent.parent / "data" / "counting_quotes.json"


class Counting(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.count = 0
        self.last_user_id = None
        self.counting_quote = []
        self._database_lock = asyncio.Lock()
        self._load_counting_quotes()

    def _load_counting_quotes(self) -> None:
        try:
            sayings = json.loads(COUNTING_QUOTES_FILE.read_text(encoding="utf-8"))
            self.counting_quote = sayings.get("falsche_zahl", []) if isinstance(sayings, dict) else []
        except (FileNotFoundError, json.JSONDecodeError):
            self.counting_quote = []

    async def cog_load(self) -> None:
        database.initialize_database()
        self.count = database.load_count()
        self._load_counting_quotes()

    async def _save_count(self) -> None:
        async with self._database_lock:
            database.save_count(self.count)

    def counting_quote_func(self, message: str) -> str:
        if self.counting_quote:
            return f"{random.choice(self.counting_quote)}\n\n{message}"
        return message

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id != COUNTING_CHANNEL_ID:
            return

        try:
            number = int(message.content.strip())
        except ValueError:
            return  # Nicht numerische Nachrichten ignorieren.

        expected = self.count + 1

        # Gleicher User zweimal hintereinander -> Reset
        if self.last_user_id is not None and message.author.id == self.last_user_id:
            self.count = 0
            self.last_user_id = None
            await self._save_count()
            await message.add_reaction("❌")
            reset_message = (
                f"{message.author.mention}, du warst bereits dran. "
                f"Die Zählung wurde zurückgesetzt. Nächste Zahl: **1**"
            )
            await message.channel.send(self.counting_quote_func(reset_message))
            return

        # Falsche Zahl -> Reset
        if number != expected:
            self.count = 0
            self.last_user_id = None
            await self._save_count()
            await message.add_reaction("❌")
            reset_message = (
                f"Falsche Zahl! Erwartet wurde **{expected}**. "
                f"Die Zählung wurde zurückgesetzt. Nächste Zahl: **1**"
            )
            await message.channel.send(self.counting_quote_func(reset_message))
            return

        # Richtig
        self.count = number
        self.last_user_id = message.author.id
        await self._save_count()
        await message.add_reaction("✅")

    @commands.command(name="set")
    @commands.has_any_role(*ADMIN_ROLES)
    async def set_number(self, ctx: commands.Context, number: int):
        #Setzt den aktuellen Zählerstand (die nächste erwartete Zahl ist number+1).
        if number < 0:
            await ctx.send("Die Zahl darf nicht negativ sein.")
            return

        self.count = number
        self.last_user_id = None  # Reset, damit niemand fälschlich als "doppelt dran" gilt
        await self._save_count()

        await ctx.send(
            f"Zählerstand wurde auf **{number}** gesetzt. "
            f"Nächste erwartete Zahl: **{number + 1}**"
        )

    @set_number.error
    async def set_number_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingAnyRole):
            await ctx.send("Dafür brauchst du Administrator-Rechte.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Bitte eine gültige Zahl angeben, z. B. `!set 41`.")
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(Counting(bot))