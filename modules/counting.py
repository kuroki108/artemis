import asyncio
import json
import random
from pathlib import Path

import discord
from discord.ext import commands

from config import COUNTING_CHANNEL_ID, COUNTING_ROLE_ID
from database import load_counting_state, save_counting_state


# Pfad relativ zur Projektstruktur, damit der Bot aus jedem Ordner startet.
QUOTES_PATH = Path(__file__).parent.parent / "data" / "counting_quotes.json"

with open(QUOTES_PATH, "r", encoding="utf-8") as f:
    counting_quotes = json.load(f)


class Counting(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        (
            self.count,
            self.last_user_id,
            self.counting_role_user_id,
        ) = load_counting_state(COUNTING_CHANNEL_ID)
        # Nachrichten auch während Discord-Anfragen nacheinander verarbeiten.
        self.lock = asyncio.Lock()

    def save_state(self):
        save_counting_state(
            COUNTING_CHANNEL_ID,
            self.count,
            self.last_user_id,
            self.counting_role_user_id,
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id != COUNTING_CHANNEL_ID or message.guild is None:
            return

        async with self.lock:
            try:
                number = int(message.content.strip())
            except ValueError:
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass
                return

            expected = self.count + 1

            # Gleicher User zweimal hintereinander -> Reset.
            if message.author.id == self.last_user_id:
                self.count = 0
                self.last_user_id = None
                self.save_state()
                await message.add_reaction("❌")
                await message.channel.send(
                    f"{message.author.mention}, du warst bereits dran. "
                    "Zählung zurückgesetzt."
                )
                return

            # Falsche Zahl -> Reset und Rolle übertragen.
            if number != expected:
                self.count = 0
                self.last_user_id = None
                # Bisherigen Rolleninhaber behalten, bis die Rolle übertragen ist.
                self.save_state()

                role = discord.Object(id=COUNTING_ROLE_ID)
                previous_user_id = self.counting_role_user_id

                if previous_user_id != message.author.id:
                    await message.author.add_roles(role)

                    if previous_user_id is not None:
                        previous_member = message.guild.get_member(previous_user_id)
                        if previous_member is None:
                            try:
                                previous_member = await message.guild.fetch_member(
                                    previous_user_id
                                )
                            except discord.NotFound:
                                # Der bisherige Rolleninhaber hat den Server verlassen.
                                previous_member = None
                        if previous_member is not None:
                            await previous_member.remove_roles(role)

                    self.counting_role_user_id = message.author.id
                    self.save_state()

                await message.add_reaction("❌")
                await message.channel.send(
                    f"Falsche Zahl! Erwartet wurde **{expected}**. "
                    "Zählung zurückgesetzt."
                )
                await message.channel.send(
                    random.choice(counting_quotes["wrong_number"])
                )
                return

            # Richtig.
            self.count = number
            self.last_user_id = message.author.id
            self.save_state()
            await message.add_reaction("✅")


async def setup(bot: commands.Bot):
    await bot.add_cog(Counting(bot))