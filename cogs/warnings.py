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

class Warnings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @has_mod_role()
    async def warn(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Warn a member. Usage: !warn @user [reason]"""
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "INSERT INTO warnings (guild_id, user_id, moderator_id, reason) VALUES (?, ?, ?, ?)",
                (str(ctx.guild.id), str(member.id), str(ctx.author.id), reason)
            )
            await db.commit()
            async with db.execute(
                "SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?",
                (str(ctx.guild.id), str(member.id))
            ) as cur:
                count = (await cur.fetchone())[0]
        await database.add_mod_log(str(ctx.guild.id), "warn", str(ctx.author.id), str(member.id), reason)
        embed = discord.Embed(title="\u26a0\ufe0f Warning Issued", color=discord.Color.yellow())
        embed.add_field(name="User", value=member.mention, inline=True)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_footer(text=f"Total warnings: {count}")
        await ctx.send(embed=embed)
        try:
            await member.send(f"\u26a0\ufe0f You have been warned in **{ctx.guild.name}**.\nReason: {reason}\nTotal warnings: {count}")
        except Exception:
            pass

    @commands.command()
    @has_mod_role()
    async def warnings(self, ctx, member: discord.Member):
        """View warnings for a member."""
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT reason, moderator_id, timestamp FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY timestamp DESC LIMIT 10",
                (str(ctx.guild.id), str(member.id))
            ) as cur:
                rows = await cur.fetchall()
        if not rows:
            await ctx.send(f"\u2705 {member.mention} has no warnings.")
            return
        embed = discord.Embed(title=f"\u26a0\ufe0f Warnings for {member.display_name}", color=discord.Color.orange())
        for i, (reason, mod_id, ts) in enumerate(rows, 1):
            embed.add_field(name=f"#{i} \u2014 {str(ts)[:10]}", value=f"**Reason:** {reason}\n**By:** <@{mod_id}>", inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    @has_mod_role()
    async def clearwarns(self, ctx, member: discord.Member):
        """Clear all warnings for a member."""
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?",
                (str(ctx.guild.id), str(member.id))
            )
            await db.commit()
        await database.add_mod_log(str(ctx.guild.id), "clearwarns", str(ctx.author.id), str(member.id))
        await ctx.send(f"\u2705 Cleared all warnings for {member.mention}.")

async def setup(bot):
    await bot.add_cog(Warnings(bot))
