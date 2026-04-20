import discord
from discord import app_commands
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

    # ============================================================ PREFIX

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
            if row:
                await db.execute(
                    "UPDATE tags SET uses = uses + 1 WHERE guild_id = ? AND name = ?",
                    (str(ctx.guild.id), name.lower())
                )
                await db.commit()
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
            await db.execute("DELETE FROM tags WHERE guild_id = ? AND name = ?", (str(ctx.guild.id), name.lower()))
            await db.commit()
        await ctx.send(f"\U0001f5d1\ufe0f Tag `{name}` removed.")

    @tag.command(name="list")
    async def tag_list(self, ctx):
        """List all tags."""
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT name, uses FROM tags WHERE guild_id = ? ORDER BY name",
                (str(ctx.guild.id),)
            ) as cur:
                rows = await cur.fetchall()
        if not rows:
            await ctx.send("No tags yet. Add one with `!tag add <name> <content>`.")
            return
        names = ", ".join(f"`{r[0]}`" for r in rows)
        embed = discord.Embed(title="\U0001f3f7\ufe0f Tags", description=names, color=discord.Color.blurple())
        embed.set_footer(text=f"{len(rows)} tag(s) \u00b7 Use !tag <name> to invoke")
        await ctx.send(embed=embed)

    @tag.command(name="info")
    async def tag_info(self, ctx, name: str):
        """Show info about a tag. Usage: !tag info <name>"""
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT content, created_by, uses FROM tags WHERE guild_id = ? AND name = ?",
                (str(ctx.guild.id), name.lower())
            ) as cur:
                row = await cur.fetchone()
        if not row:
            await ctx.send(f"\u274c Tag `{name}` not found.")
            return
        content, created_by, uses = row
        embed = discord.Embed(title=f"\U0001f3f7\ufe0f Tag: {name}", color=discord.Color.blurple())
        embed.add_field(name="Content", value=content[:1024], inline=False)
        embed.add_field(name="Created By", value=f"<@{created_by}>" if created_by and created_by != "system" else "System", inline=True)
        embed.add_field(name="Uses", value=str(uses or 0), inline=True)
        await ctx.send(embed=embed)

    # ============================================================ SLASH

    @app_commands.command(name="tag", description="Look up a tag by name.")
    @app_commands.describe(name="Name of the tag")
    async def slash_tag(self, interaction: discord.Interaction, name: str):
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT content FROM tags WHERE guild_id = ? AND name = ?",
                (str(interaction.guild_id), name.lower())
            ) as cur:
                row = await cur.fetchone()
            if row:
                await db.execute(
                    "UPDATE tags SET uses = uses + 1 WHERE guild_id = ? AND name = ?",
                    (str(interaction.guild_id), name.lower())
                )
                await db.commit()
        if not row:
            await interaction.response.send_message(f"\u274c Tag `{name}` not found.", ephemeral=True)
            return
        await interaction.response.send_message(row[0])

    @app_commands.command(name="taglist", description="List all tags for this server.")
    async def slash_taglist(self, interaction: discord.Interaction):
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT name FROM tags WHERE guild_id = ? ORDER BY name", (str(interaction.guild_id),)
            ) as cur:
                rows = await cur.fetchall()
        if not rows:
            await interaction.response.send_message("No tags yet.", ephemeral=True)
            return
        embed = discord.Embed(title="\U0001f3f7\ufe0f Tags", description=", ".join(f"`{r[0]}`" for r in rows), color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="tagadd", description="Add a new tag. (Mod only)")
    @app_commands.describe(name="Tag name", content="Tag content")
    async def slash_tagadd(self, interaction: discord.Interaction, name: str, content: str):
        if not any(r.id in MOD_ROLE_IDS for r in interaction.user.roles):
            await interaction.response.send_message("\u274c No permission.", ephemeral=True)
            return
        async with aiosqlite.connect(database.DB_PATH) as db:
            try:
                await db.execute(
                    "INSERT INTO tags (guild_id, name, content, created_by) VALUES (?, ?, ?, ?)",
                    (str(interaction.guild_id), name.lower(), content, str(interaction.user.id))
                )
                await db.commit()
                await interaction.response.send_message(f"\u2705 Tag `{name}` created.", ephemeral=True)
            except Exception:
                await interaction.response.send_message(f"\u274c Tag `{name}` already exists.", ephemeral=True)

    @app_commands.command(name="tagedit", description="Edit an existing tag. (Mod only)")
    @app_commands.describe(name="Tag name", content="New content")
    async def slash_tagedit(self, interaction: discord.Interaction, name: str, content: str):
        if not any(r.id in MOD_ROLE_IDS for r in interaction.user.roles):
            await interaction.response.send_message("\u274c No permission.", ephemeral=True)
            return
        async with aiosqlite.connect(database.DB_PATH) as db:
            result = await db.execute(
                "UPDATE tags SET content = ? WHERE guild_id = ? AND name = ?",
                (content, str(interaction.guild_id), name.lower())
            )
            await db.commit()
        if result.rowcount == 0:
            await interaction.response.send_message(f"\u274c Tag `{name}` not found.", ephemeral=True)
        else:
            await interaction.response.send_message(f"\u2705 Tag `{name}` updated.", ephemeral=True)

    @app_commands.command(name="tagremove", description="Remove a tag. (Mod only)")
    @app_commands.describe(name="Tag name to remove")
    async def slash_tagremove(self, interaction: discord.Interaction, name: str):
        if not any(r.id in MOD_ROLE_IDS for r in interaction.user.roles):
            await interaction.response.send_message("\u274c No permission.", ephemeral=True)
            return
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "DELETE FROM tags WHERE guild_id = ? AND name = ?",
                (str(interaction.guild_id), name.lower())
            )
            await db.commit()
        await interaction.response.send_message(f"\U0001f5d1\ufe0f Tag `{name}` removed.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Tags(bot))
