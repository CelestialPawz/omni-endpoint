import discord
from discord.ext import commands
import config
import asyncio
import traceback

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=config.PREFIX, intents=intents)

COGS = [
    "cogs.automod",
    "cogs.welcome",
    "cogs.roles",
    "cogs.moderation",
    "cogs.logs",
    "cogs.custom_commands",
    "cogs.status",
    "cogs.fun",
    "cogs.help",
]

@bot.event
async def on_ready():
    print(f"[OMNI Endpoint] Online as {bot.user} ({bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"[OMNI Endpoint] Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"[OMNI Endpoint] Sync error: {e}")

@bot.event
async def on_command_error(ctx, error):
    print(f"[ERROR] Command '{ctx.command}' raised: {error}")
    traceback.print_exception(type(error), error, error.__traceback__)
    await ctx.send(f"\u274c Error: `{error}`")

async def main():
    async with bot:
        for cog in COGS:
            await bot.load_extension(cog)
            print(f"[OMNI Endpoint] Loaded {cog}")
        await bot.start(config.TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
