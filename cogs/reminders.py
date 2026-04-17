import discord
from discord.ext import commands
from discord.ext import tasks
import aiosqlite
import database
import time
import re

def parse_time(s: str) -> int:
    total = 0
    for amt, unit in re.findall(r"(\d+)([smhd])", s.lower()):
        amt = int(amt)
        if unit == "s": total += amt
        elif unit == "m": total += amt * 60
        elif unit == "h": total += amt * 3600
        elif unit == "d": total += amt * 86400
    return total

def fmt_seconds(s: int) -> str:
    d, r = divmod(int(s), 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s: parts.append(f"{s}s")
    return " ".join(parts) or "0s"

class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()

    @commands.command(name="remindme", aliases=["remind"])
    async def remindme(self, ctx, time_str: str, *, message: str):
        """Set a reminder. Usage: !remindme 1h30m Do the thing"""
        seconds = parse_time(time_str)
        if seconds < 10:
            await ctx.send("\u274c Invalid time. Examples: `30s`, `5m`, `2h`, `1d`")
            return
        due_at = time.time() + seconds
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "INSERT INTO reminders (user_id, channel_id, message, due_at) VALUES (?, ?, ?, ?)",
                (str(ctx.author.id), str(ctx.channel.id), message, due_at)
            )
            await db.commit()
        await ctx.send(f"\u23f0 Got it! Reminding you about **{message}** in `{fmt_seconds(seconds)}`.")

    @commands.command(name="reminders")
    async def list_reminders(self, ctx):
        """List your active reminders."""
        now = time.time()
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT id, message, due_at FROM reminders WHERE user_id = ? AND done = 0 ORDER BY due_at ASC",
                (str(ctx.author.id),)
            ) as cur:
                rows = await cur.fetchall()
        if not rows:
            await ctx.send("You have no active reminders.")
            return
        embed = discord.Embed(title="\u23f0 Your Reminders", color=discord.Color.blurple())
        for rid, msg, due in rows:
            remaining = max(0, due - now)
            embed.add_field(name=f"#{rid} \u2014 in {fmt_seconds(remaining)}", value=msg, inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="delreminder")
    async def del_reminder(self, ctx, reminder_id: int):
        """Delete one of your reminders by ID."""
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "DELETE FROM reminders WHERE id = ? AND user_id = ?",
                (reminder_id, str(ctx.author.id))
            )
            await db.commit()
        await ctx.send(f"\u2705 Reminder #{reminder_id} deleted.")

    @tasks.loop(seconds=15)
    async def check_reminders(self):
        now = time.time()
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT id, user_id, channel_id, message FROM reminders WHERE due_at <= ? AND done = 0",
                (now,)
            ) as cur:
                rows = await cur.fetchall()
            for row_id, user_id, channel_id, message in rows:
                channel = self.bot.get_channel(int(channel_id))
                if channel:
                    try:
                        await channel.send(f"\u23f0 <@{user_id}> Reminder: **{message}**")
                    except Exception:
                        pass
                await db.execute("UPDATE reminders SET done = 1 WHERE id = ?", (row_id,))
            await db.commit()

    @check_reminders.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Reminders(bot))
