import discord
from discord.ext import commands
from datetime import timedelta
import database
import config

MOD_ROLE_IDS = (1004147266757603389, 1004147268120752248)

def has_mod_role():
    async def predicate(ctx):
        role_ids = [r.id for r in ctx.author.roles]
        if any(r in role_ids for r in MOD_ROLE_IDS):
            return True
        raise commands.MissingAnyRole(list(MOD_ROLE_IDS))
    return commands.check(predicate)

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _log(self, guild, embed: discord.Embed):
        ch = guild.get_channel(config.LOG_CHANNEL_ID)
        if ch:
            await ch.send(embed=embed)

    @commands.command()
    @has_mod_role()
    async def ban(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Ban a member."""
        await member.ban(reason=reason)
        await ctx.send(f"\U0001f528 **{member}** has been banned. Reason: {reason}")
        await database.add_mod_log(str(ctx.guild.id), "ban", str(ctx.author.id), str(member.id), reason)
        embed = discord.Embed(title="Ban", description=f"{member.mention} banned by {ctx.author.mention}\n**Reason:** {reason}", color=discord.Color.red())
        await self._log(ctx.guild, embed)

    @commands.command()
    @has_mod_role()
    async def kick(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Kick a member."""
        await member.kick(reason=reason)
        await ctx.send(f"\U0001f462 **{member}** has been kicked. Reason: {reason}")
        await database.add_mod_log(str(ctx.guild.id), "kick", str(ctx.author.id), str(member.id), reason)
        embed = discord.Embed(title="Kick", description=f"{member.mention} kicked by {ctx.author.mention}\n**Reason:** {reason}", color=discord.Color.orange())
        await self._log(ctx.guild, embed)

    @commands.command()
    @has_mod_role()
    async def mute(self, ctx, member: discord.Member, minutes: int = 10, *, reason="No reason provided"):
        """Timeout a member."""
        await member.timeout(timedelta(minutes=minutes), reason=reason)
        await ctx.send(f"\U0001f507 **{member}** muted for {minutes}m. Reason: {reason}")
        await database.add_mod_log(str(ctx.guild.id), "mute", str(ctx.author.id), str(member.id), reason)
        embed = discord.Embed(title="Mute", description=f"{member.mention} muted {minutes}m by {ctx.author.mention}\n**Reason:** {reason}", color=discord.Color.yellow())
        await self._log(ctx.guild, embed)

    @commands.command()
    @has_mod_role()
    async def unmute(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Remove timeout from a member. Usage: !unmute @user [reason]"""
        await member.timeout(None, reason=reason)
        await ctx.send(f"\U0001f50a **{member}** has been unmuted.")
        await database.add_mod_log(str(ctx.guild.id), "unmute", str(ctx.author.id), str(member.id), reason)
        embed = discord.Embed(title="Unmute", description=f"{member.mention} unmuted by {ctx.author.mention}\n**Reason:** {reason}", color=discord.Color.green())
        await self._log(ctx.guild, embed)

    @commands.command()
    @has_mod_role()
    async def purge(self, ctx, amount: int = 10):
        """Delete last N messages."""
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"\U0001f5d1\ufe0f Deleted {len(deleted)-1} messages.", delete_after=5)

    @commands.command()
    @has_mod_role()
    async def unban(self, ctx, *, user_id: int):
        """Unban a user by ID."""
        user = await self.bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        await database.add_mod_log(str(ctx.guild.id), "unban", str(ctx.author.id), str(user_id))
        await ctx.send(f"\u2705 Unbanned **{user}**.")

    @commands.command()
    @has_mod_role()
    async def slowmode(self, ctx, seconds: int = 0):
        """Set channel slowmode. Usage: !slowmode [seconds]"""
        if seconds < 0 or seconds > 21600:
            await ctx.send("\u274c Slowmode must be between 0 and 21600 seconds.")
            return
        await ctx.channel.edit(slowmode_delay=seconds)
        await ctx.send("\u2705 Slowmode disabled." if seconds == 0 else f"\u23f1\ufe0f Slowmode set to **{seconds}s**.")

    @commands.command()
    @has_mod_role()
    async def lock(self, ctx, channel: discord.TextChannel = None, *, reason="No reason provided"):
        """Lock a channel. Usage: !lock [#channel] [reason]"""
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=reason)
        await ctx.send(f"\U0001f512 {channel.mention} locked. Reason: {reason}")
        embed = discord.Embed(title="\U0001f512 Channel Locked", description=f"{channel.mention} locked by {ctx.author.mention}\n**Reason:** {reason}", color=discord.Color.red())
        await self._log(ctx.guild, embed)

    @commands.command()
    @has_mod_role()
    async def unlock(self, ctx, channel: discord.TextChannel = None, *, reason="No reason provided"):
        """Unlock a channel. Usage: !unlock [#channel] [reason]"""
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=reason)
        await ctx.send(f"\U0001f513 {channel.mention} unlocked.")
        embed = discord.Embed(title="\U0001f513 Channel Unlocked", description=f"{channel.mention} unlocked by {ctx.author.mention}", color=discord.Color.green())
        await self._log(ctx.guild, embed)

    @commands.command()
    @has_mod_role()
    async def announce(self, ctx, channel: discord.TextChannel, *, message: str):
        """Send an announcement. Usage: !announce #channel <message>"""
        embed = discord.Embed(description=message, color=discord.Color.blurple())
        embed.set_footer(text=f"Announcement by {ctx.author.display_name}")
        await channel.send(embed=embed)
        await ctx.send(f"\u2705 Announcement sent to {channel.mention}.")

async def setup(bot):
    await bot.add_cog(Moderation(bot))
