import discord
from discord.ext import commands
import config
import asyncio
import traceback
import database
import aiosqlite
import os

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=config.PREFIX, intents=intents)

COGS = [
    "cogs.automod",
    "cogs.welcome",
    "cogs.roles",
    "cogs.moderation",
    "cogs.warnings",
    "cogs.logs",
    "cogs.tags",
    "cogs.starboard",
    "cogs.reminders",
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
    if isinstance(error, commands.CommandNotFound):
        # Check if it matches a custom tag in the DB
        cmd = ctx.invoked_with.lower()
        guild_id = str(ctx.guild.id) if ctx.guild else os.getenv('GUILD_ID', '')
        db_path = os.getenv('DB_PATH', 'omni.db')
        try:
            async with aiosqlite.connect(db_path) as db:
                async with db.execute(
                    'SELECT content FROM tags WHERE guild_id = ? AND name = ?',
                    (guild_id, cmd)
                ) as cursor:
                    row = await cursor.fetchone()
                if row:
                    await db.execute(
                        'UPDATE tags SET uses = uses + 1 WHERE guild_id = ? AND name = ?',
                        (guild_id, cmd)
                    )
                    await db.commit()
                    await ctx.send(row[0])
        except Exception as e:
            print(f'[OMNI Endpoint] Tag lookup error for "{cmd}": {e}')
        return
    elif isinstance(error, commands.MissingAnyRole):
        await ctx.send("\u274c You don't have the required role to use this command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"\u274c Missing argument: `{error.param.name}`. See `!help`.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("\u274c Member not found.")
    else:
        print(f"[ERROR] Command '{ctx.command}' raised: {error}")
        traceback.print_exception(type(error), error, error.__traceback__)
        await ctx.send(f"\u274c Error: `{error}`")

async def main():
    await database.init_db()
    print("[OMNI Endpoint] Database initialised.")
    async with bot:
        for cog in COGS:
            try:
                await bot.load_extension(cog)
                print(f"[OMNI Endpoint] Loaded {cog}")
            except Exception as e:
                print(f"[OMNI Endpoint] Failed to load {cog}: {e}")
        await bot.start(config.TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
