import discord
from discord.ext import commands
import aiosqlite
import os

DB_PATH = os.getenv('DB_PATH', 'omni.db')
GUILD_ID = os.getenv('GUILD_ID', '')

DEFAULT_COMMANDS = {
    "info":  "OMNI Endpoint \u2014 Server management + StarServer monitoring bot. Developed by Axel @ Crystal Kitsune Studios.",
    "rules": "1. Be respectful.\n2. No spam.\n3. No NSFW outside designated channels.\n4. Follow Discord ToS.",
    "cks":   "Crystal Kitsune Studios \u2014 https://crystal-kitsune-studios.com",
}

class CustomCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        async with aiosqlite.connect(DB_PATH) as db:
            for name, content in DEFAULT_COMMANDS.items():
                await db.execute(
                    "INSERT OR IGNORE INTO tags (guild_id, name, content, created_by) VALUES (?, ?, ?, 'system')",
                    (GUILD_ID, name, content)
                )
            await db.commit()

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Intercept CommandNotFound and check if it's a custom tag."""
        if not isinstance(error, commands.CommandNotFound):
            return

        cmd = ctx.invoked_with.lower()
        guild_id = str(ctx.guild.id) if ctx.guild else GUILD_ID

        try:
            async with aiosqlite.connect(DB_PATH) as db:
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
            print(f'[CustomCommands] Error looking up tag "{cmd}": {e}')

async def setup(bot):
    await bot.add_cog(CustomCommands(bot))
