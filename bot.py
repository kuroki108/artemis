import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

log = logging.getLogger("artemis")

intents = discord.Intents.default()
intents.guilds = True
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    activity=discord.CustomActivity(name="⟣ 🪽 lunaR palace ₊ ⊹")
)


async def setup_hook():
    await bot.load_extension("modules.counting")
    await bot.load_extension("modules.bump_reminder")
    await bot.load_extension("modules.verification")
    # Slash-Commands bei Discord registrieren, sonst tauchen sie nicht auf.
    synced = await bot.tree.sync()
    log.info("%d Slash-Command(s) synchronisiert", len(synced))


bot.setup_hook = setup_hook


@bot.event
async def on_ready():
    log.info("Bot ist online als %s", bot.user)


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN wurde nicht gefunden.")

    # root_logger=True: auch die Logs der Module landen in der Konsole.
    bot.run(TOKEN, root_logger=True)
