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

class ModNotes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="note")
    @has_mod_role()
    async def note(self, ctx, member: discord.Member, *, text: str):
        """Add a private mod note. Usage: !note @user <text>"""
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "INSERT INTO mod_notes (guild_id, user_id, moderator_id, note) VALUES (?, ?, ?, ?)",
                (str(ctx.guild.id), str(member.id), str(ctx.author.id), text)
            )
            await db.commit()
        try:
            await ctx.message.delete()
        except Exception:
            pass
        await ctx.send(f"\U0001f4dd Note added for {member.mention}.", delete_after=10)

    @commands.command(name="modlogs", aliases=["ml"])
    @has_mod_role()
    async def modlogs(self, ctx, member: discord.Member):
        """View full mod history + notes for a user. Usage: !modlogs @user"""
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT action, moderator_id, reason, timestamp FROM mod_logs "
                "WHERE guild_id = ? AND target_id = ? ORDER BY timestamp DESC LIMIT 15",
                (str(ctx.guild.id), str(member.id))
            ) as cur:
                logs = await cur.fetchall()
            async with db.execute(
                "SELECT moderator_id, note, timestamp FROM mod_notes "
                "WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC LIMIT 5",
                (str(ctx.guild.id), str(member.id))
            ) as cur:
                notes = await cur.fetchall()

        embed = discord.Embed(
            title=f"\U0001f4cb Mod History \u2014 {member.display_name}",
            color=discord.Color.orange()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        if not logs and not notes:
            embed.description = "No mod history found for this user."
        else:
            if logs:
                lines = []
                for action, mod_id, reason, ts in logs:
                    r = f" \u2014 {reason}" if reason else ""
                    lines.append(f"`{str(ts)[:10]}` **{action}** by <@{mod_id}>{r}")
                embed.add_field(name=f"Actions ({len(logs)})", value="\n".join(lines), inline=False)
            if notes:
                lines = [f"`{str(ts)[:10]}` <@{mod_id}>: {note}" for mod_id, note, ts in notes]
                embed.add_field(name=f"Notes ({len(notes)})", value="\n".join(lines), inline=False)
        embed.set_footer(text=f"User ID: {member.id}")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ModNotes(bot))
