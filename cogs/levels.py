import discord
from discord.ext import commands
import aiosqlite
import math
import random
import time
import database

XP_MIN = 15
XP_MAX = 25
XP_COOLDOWN = 60

def xp_for_level(level: int) -> int:
    """Total XP required to reach this level."""
    return 100 * level * (level + 1) // 2

def level_from_xp(xp: int) -> int:
    """Calculate level from total XP."""
    if xp <= 0:
        return 0
    return int((-1 + math.sqrt(1 + 4 * xp / 50)) / 2)

def xp_progress(xp: int) -> tuple[int, int, int]:
    """Returns (current_level, xp_into_level, xp_needed_for_next)."""
    level = level_from_xp(xp)
    xp_current_floor = xp_for_level(level)
    xp_next_floor    = xp_for_level(level + 1)
    return level, xp - xp_current_floor, xp_next_floor - xp_current_floor

def make_bar(filled: int, total: int, length: int = 12) -> str:
    n = round((filled / total) * length) if total else 0
    return "\u2588" * n + "\u2591" * (length - n)


class Levels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        guild_id = str(message.guild.id)
        user_id  = str(message.author.id)
        now      = time.time()

        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT xp, level, last_xp_time FROM levels WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            ) as cur:
                row = await cur.fetchone()

            xp, level, last_xp_time = row if row else (0, 0, 0.0)

            if now - last_xp_time < XP_COOLDOWN:
                return

            gained    = random.randint(XP_MIN, XP_MAX)
            new_xp    = xp + gained
            new_level = level_from_xp(new_xp)

            await db.execute(
                """
                INSERT INTO levels (guild_id, user_id, xp, level, last_xp_time)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id)
                DO UPDATE SET xp = excluded.xp, level = excluded.level, last_xp_time = excluded.last_xp_time
                """,
                (guild_id, user_id, new_xp, new_level, now)
            )
            await db.commit()

        if new_level > level:
            await self._announce_levelup(message, new_level)

    async def _announce_levelup(self, message: discord.Message, new_level: int):
        embed = discord.Embed(
            title="\u2b06\ufe0f Level Up!",
            description=f"\U0001f389 {message.author.mention} reached **Level {new_level}**!",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=message.author.display_avatar.url)
        await message.channel.send(embed=embed, delete_after=30)
        await self._assign_level_role(message.guild, message.author, new_level)

    async def _assign_level_role(self, guild: discord.Guild, member: discord.Member, level: int):
        role_map = await self._get_level_roles(str(guild.id))
        if not role_map:
            return
        earned = {lvl: rid for lvl, rid in role_map.items() if level >= lvl}
        if not earned:
            return
        target_lvl = max(earned)
        role = guild.get_role(earned[target_lvl])
        if role and role not in member.roles:
            try:
                level_role_ids = set(role_map.values())
                to_remove = [r for r in member.roles if r.id in level_role_ids and r != role]
                if to_remove:
                    await member.remove_roles(*to_remove, reason="Level role update")
                await member.add_roles(role, reason=f"Reached level {level}")
            except Exception:
                pass

    async def _get_level_roles(self, guild_id: str) -> dict[int, int]:
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT level_required, role_id FROM level_roles WHERE guild_id = ? ORDER BY level_required",
                (guild_id,)
            ) as cur:
                rows = await cur.fetchall()
        return {r[0]: r[1] for r in rows}

    @commands.command(name="rank", aliases=["level", "xp"])
    async def rank(self, ctx, member: discord.Member = None):
        """Show your level and XP. Usage: !rank [@user]"""
        member   = member or ctx.author
        guild_id = str(ctx.guild.id)
        user_id  = str(member.id)

        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT xp, level FROM levels WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            ) as cur:
                row = await cur.fetchone()
            async with db.execute(
                "SELECT COUNT(*) FROM levels WHERE guild_id = ? AND xp > ?",
                (guild_id, row[0] if row else 0)
            ) as cur:
                above = (await cur.fetchone())[0]

        if not row:
            await ctx.send(f"**{member.display_name}** hasn't earned any XP yet.")
            return

        total_xp, _ = row
        level, xp_in, xp_needed = xp_progress(total_xp)
        bar      = make_bar(xp_in, xp_needed)
        rank_pos = above + 1

        embed = discord.Embed(color=member.color if member.color.value else discord.Color.blurple())
        embed.set_author(name=f"{member.display_name}'s Rank", icon_url=member.display_avatar.url)
        embed.add_field(name="Level", value=str(level), inline=True)
        embed.add_field(name="Rank",  value=f"#{rank_pos}", inline=True)
        embed.add_field(name="Total XP", value=f"{total_xp:,}", inline=True)
        embed.add_field(
            name=f"Progress to Level {level + 1}",
            value=f"`{bar}` {xp_in:,} / {xp_needed:,} XP",
            inline=False
        )
        embed.set_footer(text="OMNI Endpoint | Crystal Kitsune Studios")
        await ctx.send(embed=embed)

    @commands.command(name="leaderboard", aliases=["lb", "top"])
    async def leaderboard(self, ctx, page: int = 1):
        """Show the XP leaderboard. Usage: !leaderboard [page]"""
        per_page = 10
        offset   = (page - 1) * per_page
        guild_id = str(ctx.guild.id)

        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT user_id, xp, level FROM levels WHERE guild_id = ? ORDER BY xp DESC LIMIT ? OFFSET ?",
                (guild_id, per_page, offset)
            ) as cur:
                rows = await cur.fetchall()
            async with db.execute(
                "SELECT COUNT(*) FROM levels WHERE guild_id = ?", (guild_id,)
            ) as cur:
                total = (await cur.fetchone())[0]

        if not rows:
            await ctx.send("No XP data yet. Start chatting!")
            return

        total_pages = math.ceil(total / per_page)
        medals = {1: "\U0001f947", 2: "\U0001f948", 3: "\U0001f949"}
        lines  = []
        for i, (user_id, xp, level) in enumerate(rows, start=offset + 1):
            medal  = medals.get(i, f"`#{i}`")
            member = ctx.guild.get_member(int(user_id))
            name   = member.display_name if member else f"<@{user_id}>"
            lines.append(f"{medal} **{name}** \u2014 Level {level} \u00b7 {xp:,} XP")

        embed = discord.Embed(
            title=f"\U0001f3c6 XP Leaderboard \u2014 {ctx.guild.name}",
            description="\n".join(lines),
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Page {page}/{total_pages} \u00b7 {total} members ranked")
        await ctx.send(embed=embed)

    @commands.command(name="setlevelrole", aliases=["levelrole"])
    @commands.has_permissions(manage_roles=True)
    async def set_level_role(self, ctx, level: int, role: discord.Role):
        """Assign a role reward for a level. Usage: !setlevelrole <level> @Role"""
        if level < 1:
            await ctx.send("\u274c Level must be at least 1.")
            return
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                """
                INSERT INTO level_roles (guild_id, level_required, role_id)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, level_required)
                DO UPDATE SET role_id = excluded.role_id
                """,
                (str(ctx.guild.id), level, role.id)
            )
            await db.commit()
        await ctx.send(f"\u2705 **{role.name}** will be awarded at **Level {level}**.")

    @commands.command(name="removelevelrole")
    @commands.has_permissions(manage_roles=True)
    async def remove_level_role(self, ctx, level: int):
        """Remove a level role reward. Usage: !removelevelrole <level>"""
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "DELETE FROM level_roles WHERE guild_id = ? AND level_required = ?",
                (str(ctx.guild.id), level)
            )
            await db.commit()
        await ctx.send(f"\U0001f5d1\ufe0f Level role for Level {level} removed.")

    @commands.command(name="levelroles")
    async def list_level_roles(self, ctx):
        """List all configured level role rewards."""
        role_map = await self._get_level_roles(str(ctx.guild.id))
        if not role_map:
            await ctx.send("No level roles configured. Use `!setlevelrole <level> @Role`.")
            return
        embed = discord.Embed(title="\U0001f396\ufe0f Level Role Rewards", color=discord.Color.blurple())
        lines = [
            f"Level **{lvl}** \u2192 {ctx.guild.get_role(rid).mention if ctx.guild.get_role(rid) else f'*(deleted role {rid})*'}"
            for lvl, rid in sorted(role_map.items())
        ]
        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)

    @commands.command(name="resetxp")
    @commands.has_permissions(administrator=True)
    async def reset_xp(self, ctx, member: discord.Member):
        """Reset a member's XP to 0. Usage: !resetxp @user"""
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "DELETE FROM levels WHERE guild_id = ? AND user_id = ?",
                (str(ctx.guild.id), str(member.id))
            )
            await db.commit()
        await ctx.send(f"\u2705 Reset XP for {member.mention}.")

    @commands.command(name="givexp")
    @commands.has_permissions(administrator=True)
    async def give_xp(self, ctx, member: discord.Member, amount: int):
        """Manually award XP. Usage: !givexp @user <amount>"""
        if amount <= 0:
            await ctx.send("\u274c Amount must be positive.")
            return
        guild_id = str(ctx.guild.id)
        user_id  = str(member.id)
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT xp, level FROM levels WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            ) as cur:
                row = await cur.fetchone()
            old_xp    = row[0] if row else 0
            old_level = row[1] if row else 0
            new_xp    = old_xp + amount
            new_level = level_from_xp(new_xp)
            await db.execute(
                """
                INSERT INTO levels (guild_id, user_id, xp, level, last_xp_time)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id)
                DO UPDATE SET xp = excluded.xp, level = excluded.level
                """,
                (guild_id, user_id, new_xp, new_level, time.time())
            )
            await db.commit()
        await ctx.send(f"\u2705 Gave **{amount:,} XP** to {member.mention}. Now at Level {new_level} ({new_xp:,} XP).")
        if new_level > old_level:
            await self._assign_level_role(ctx.guild, member, new_level)


async def setup(bot):
    await bot.add_cog(Levels(bot))
