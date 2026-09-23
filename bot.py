import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


async def setup_hook():
    await bot.load_extension("modules.counting")


bot.setup_hook = setup_hook


@bot.event
async def on_ready():
    print(f"Bot ist online als {bot.user}")


@bot.command()
async def ping(ctx: commands.Context):
    await ctx.send(f"Pong! 🏓")


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN wurde nicht gefunden.")

    bot.run(TOKEN)