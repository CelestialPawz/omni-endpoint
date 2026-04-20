import discord
from discord.ext import commands
import aiosqlite
import time
import database

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()

    @commands.command(name="ping")
    async def ping(self, ctx):
        """Show bot latency."""
        ws = round(self.bot.latency * 1000)
        t = time.perf_counter()
        msg = await ctx.send("\U0001f4e1 Pinging...")
        rtt = round((time.perf_counter() - t) * 1000)
        color = discord.Color.green() if ws < 100 else discord.Color.yellow() if ws < 200 else discord.Color.red()
        embed = discord.Embed(title="\U0001f3d3 Pong!", color=color)
        embed.add_field(name="WebSocket", value=f"{ws}ms", inline=True)
        embed.add_field(name="Round-trip", value=f"{rtt}ms", inline=True)
        await msg.edit(content=None, embed=embed)

    @commands.command(name="uptime")
    async def uptime(self, ctx):
        """Show how long OMNI has been running."""
        s = int(time.time() - self.start_time)
        d, r = divmod(s, 86400)
        h, r = divmod(r, 3600)
        m, s = divmod(r, 60)
        parts = []
        if d: parts.append(f"{d}d")
        if h: parts.append(f"{h}h")
        if m: parts.append(f"{m}m")
        parts.append(f"{s}s")
        embed = discord.Embed(
            title="\u23f1\ufe0f OMNI Uptime",
            description=f"Online for **{' '.join(parts)}**.",
            color=discord.Color.blurple()
        )
        embed.set_footer(text="OMNI Endpoint | Crystal Kitsune Studios")
        await ctx.send(embed=embed)

    @commands.command(name="stats")
    async def stats(self, ctx):
        """Bot statistics."""
        guild_count = len(self.bot.guilds)
        member_count = sum(g.member_count for g in self.bot.guilds)
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute("SELECT COUNT(*) FROM tags WHERE guild_id = ?", (str(ctx.guild.id),)) as cur:
                tag_count = (await cur.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM warnings WHERE guild_id = ?", (str(ctx.guild.id),)) as cur:
                warn_count = (await cur.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM reminders WHERE done = 0") as cur:
                reminder_count = (await cur.fetchone())[0]
        embed = discord.Embed(title="\U0001f4ca OMNI Stats", color=discord.Color.blurple())
        embed.add_field(name="Guilds", value=str(guild_count), inline=True)
        embed.add_field(name="Members (total)", value=f"{member_count:,}", inline=True)
        embed.add_field(name="Tags (this server)", value=str(tag_count), inline=True)
        embed.add_field(name="Warnings (this server)", value=str(warn_count), inline=True)
        embed.add_field(name="Active Reminders", value=str(reminder_count), inline=True)
        embed.set_footer(text="OMNI Endpoint | Crystal Kitsune Studios")
        await ctx.send(embed=embed)

    @commands.command(name="avatar", aliases=["av", "pfp"])
    async def avatar(self, ctx, member: discord.Member = None):
        """Show a user's avatar. Usage: !avatar [@user]"""
        member = member or ctx.author
        embed = discord.Embed(title=f"{member.display_name}'s Avatar", color=discord.Color.blurple())
        embed.set_image(url=member.display_avatar.url)
        links = (
            f"[PNG]({member.display_avatar.with_format('png').url}) \u00b7 "
            f"[WebP]({member.display_avatar.with_format('webp').url})"
        )
        if member.display_avatar.is_animated():
            links += f" \u00b7 [GIF]({member.display_avatar.with_format('gif').url})"
        embed.add_field(name="Download", value=links)
        await ctx.send(embed=embed)

    @commands.command(name="userinfo", aliases=["ui", "whois"])
    async def userinfo(self, ctx, member: discord.Member = None):
        """Show info about a user. Usage: !userinfo [@user]"""
        member = member or ctx.author
        roles = [r.mention for r in reversed(member.roles) if r.name != "@everyone"]
        roles_str = " ".join(roles[:10]) if roles else "None"
        if len(roles) > 10:
            roles_str += f" *(+{len(roles) - 10} more)*"
        color = member.color if member.color.value else discord.Color.blurple()
        embed = discord.Embed(title=f"{member} \u2014 {member.id}", color=color)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Display Name", value=member.display_name, inline=True)
        embed.add_field(name="Bot", value="Yes" if member.bot else "No", inline=True)
        embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, "D"), inline=False)
        embed.add_field(
            name="Joined Server",
            value=discord.utils.format_dt(member.joined_at, "D") if member.joined_at else "Unknown",
            inline=False
        )
        embed.add_field(name=f"Roles ({len(roles)})", value=roles_str, inline=False)
        if member.premium_since:
            embed.add_field(name="Boosting Since", value=discord.utils.format_dt(member.premium_since, "D"), inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="serverinfo", aliases=["si", "guildinfo"])
    async def serverinfo(self, ctx):
        """Show server information."""
        g = ctx.guild
        text_ch  = sum(1 for c in g.channels if isinstance(c, discord.TextChannel))
        voice_ch = sum(1 for c in g.channels if isinstance(c, discord.VoiceChannel))
        embed = discord.Embed(title=g.name, description=g.description or "", color=discord.Color.blurple())
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        embed.add_field(name="Owner", value=g.owner.mention if g.owner else "Unknown", inline=True)
        embed.add_field(name="Members", value=f"{g.member_count:,}", inline=True)
        embed.add_field(name="Roles", value=str(len(g.roles)), inline=True)
        embed.add_field(name="Channels", value=f"\U0001f4ac {text_ch} text \u00b7 \U0001f50a {voice_ch} voice", inline=True)
        embed.add_field(name="Boosts", value=f"{g.premium_subscription_count} (Tier {g.premium_tier})", inline=True)
        embed.add_field(name="Created", value=discord.utils.format_dt(g.created_at, "D"), inline=True)
        if g.banner:
            embed.set_image(url=g.banner.url)
        embed.set_footer(text=f"ID: {g.id} \u00b7 OMNI Endpoint")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Utility(bot))
