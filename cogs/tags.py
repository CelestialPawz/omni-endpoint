import discord
from discord.ext import commands
import aiosqlite
import database

MOD_ROLE_IDS = (1004147266757603389, 1004147268120752248)

def has_mod_role():
    async def predicate(ctx):
        if any(r.id in MOD_ROLE_IDS for r in ctx.author.roles):
            return True
        raise commands.MissingAnyRole(list(MOD_ROLE_IDS))
    return commands.check(predicate)

class Tags(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="tag", invoke_without_command=True)
    async def tag(self, ctx, name: str = None):
        """Use a tag. Usage: !tag <name>"""
        if not name:
            await ctx.send("Usage: `!tag <name>` | Manage: `!tag add`, `!tag edit`, `!tag remove`, `!tag list`")
            return
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT content FROM tags WHERE guild_id = ? AND name = ?",
                (str(ctx.guild.id), name.lower())
            ) as cur:
                row = await cur.fetchone()
        if not row:
            await ctx.send(f"\u274c Tag `{name}` not found. See `!tag list`.")
            return
        await ctx.send(row[0])

    @tag.command(name="add")
    @has_mod_role()
    async def tag_add(self, ctx, name: str, *, content: str):
        """Add a tag. Usage: !tag add <name> <content>"""
        async with aiosqlite.connect(database.DB_PATH) as db:
            try:
                await db.execute(
                    "INSERT INTO tags (guild_id, name, content, created_by) VALUES (?, ?, ?, ?)",
                    (str(ctx.guild.id), name.lower(), content, str(ctx.author.id))
                )
                await db.commit()
                await ctx.send(f"\u2705 Tag `{name}` created.")
            except Exception:
                await ctx.send(f"\u274c Tag `{name}` already exists. Use `!tag edit {name} <new content>` to update it.")

    @tag.command(name="edit")
    @has_mod_role()
    async def tag_edit(self, ctx, name: str, *, content: str):
        """Edit a tag. Usage: !tag edit <name> <new content>"""
        async with aiosqlite.connect(database.DB_PATH) as db:
            result = await db.execute(
                "UPDATE tags SET content = ? WHERE guild_id = ? AND name = ?",
                (content, str(ctx.guild.id), name.lower())
            )
            await db.commit()
        if result.rowcount == 0:
            await ctx.send(f"\u274c Tag `{name}` not found.")
        else:
            await ctx.send(f"\u2705 Tag `{name}` updated.")

    @tag.command(name="remove", aliases=["delete"])
    @has_mod_role()
    async def tag_remove(self, ctx, name: str):
        """Remove a tag."""
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "DELETE FROM tags WHERE guild_id = ? AND name = ?",
                (str(ctx.guild.id), name.lower())
            )
            await db.commit()
        await ctx.send(f"\U0001f5d1\ufe0f Tag `{name}` removed.")

    @tag.command(name="list")
    async def tag_list(self, ctx):
        """List all tags."""
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT name FROM tags WHERE guild_id = ? ORDER BY name",
                (str(ctx.guild.id),)
            ) as cur:
                rows = await cur.fetchall()
        if not rows:
            await ctx.send("No tags yet. Add one with `!tag add <name> <content>`.")
            return
        names = ", ".join(f"`{r[0]}`" for r in rows)
        embed = discord.Embed(title="\U0001f3f7\ufe0f Tags", description=names, color=discord.Color.blurple())
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Tags(bot))
