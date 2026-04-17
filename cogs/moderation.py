import discord
from discord.ext import commands
from datetime import timedelta
import config

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _log(self, guild, embed: discord.Embed):
        ch = guild.get_channel(config.LOG_CHANNEL_ID)
        if ch:
            await ch.send(embed=embed)

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason="No reason provided"):
        await member.ban(reason=reason)
        await ctx.send(f"\U0001f528 **{member}** has been banned. Reason: {reason}")
        embed = discord.Embed(title="Ban", description=f"{member.mention} banned by {ctx.author.mention}\n**Reason:** {reason}", color=discord.Color.red())
        await self._log(ctx.guild, embed)

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason="No reason provided"):
        await member.kick(reason=reason)
        await ctx.send(f"\U0001f462 **{member}** has been kicked. Reason: {reason}")
        embed = discord.Embed(title="Kick", description=f"{member.mention} kicked by {ctx.author.mention}\n**Reason:** {reason}", color=discord.Color.orange())
        await self._log(ctx.guild, embed)

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def mute(self, ctx, member: discord.Member, minutes: int = 10, *, reason="No reason provided"):
        duration = timedelta(minutes=minutes)
        await member.timeout(duration, reason=reason)
        await ctx.send(f"\U0001f507 **{member}** muted for {minutes}m. Reason: {reason}")
        embed = discord.Embed(title="Mute", description=f"{member.mention} muted {minutes}m by {ctx.author.mention}\n**Reason:** {reason}", color=discord.Color.yellow())
        await self._log(ctx.guild, embed)

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int = 10):
        """Delete the last N messages (default 10). Usage: !purge 25"""
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"\U0001f5d1\ufe0f Deleted {len(deleted)-1} messages.", delete_after=5)

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, *, user_id: int):
        """Unban a user by ID. Usage: !unban 123456789"""
        user = await self.bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        await ctx.send(f"\u2705 Unbanned **{user}**.")

async def setup(bot):
    await bot.add_cog(Moderation(bot))
