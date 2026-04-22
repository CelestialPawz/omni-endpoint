import discord
from discord.ext import commands, tasks
import aiosqlite
import re
import database
import config


class ModMail(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.appeal_check.start()

    def cog_unload(self):
        self.appeal_check.cancel()

    # ── DB helpers ──────────────────────────────────────────────────────

    async def _get_channel_id(self, user_id: str):
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT thread_id FROM modmail_sessions WHERE user_id = ? AND closed = 0",
                (user_id,)
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else None

    async def _get_user_id(self, channel_id: int):
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT user_id FROM modmail_sessions WHERE thread_id = ? AND closed = 0",
                (channel_id,)
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else None

    async def _open_session(self, user_id: str, channel_id: int):
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO modmail_sessions (user_id, thread_id, closed) VALUES (?, ?, 0)",
                (user_id, channel_id)
            )
            await db.commit()

    async def _close_session(self, user_id: str):
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "UPDATE modmail_sessions SET closed = 1 WHERE user_id = ?",
                (user_id,)
            )
            await db.commit()

    # ── Channel helpers ───────────────────────────────────────────────

    def _safe_name(self, name: str) -> str:
        safe = re.sub(r"[^a-z0-9-]", "-", name.lower())
        return re.sub(r"-+", "-", safe).strip("-") or "user"

    async def _get_category(self, guild: discord.Guild):
        cat = guild.get_channel(config.MODMAIL_CATEGORY_ID)
        if cat and isinstance(cat, discord.CategoryChannel):
            return cat
        return None

    async def _create_channel(self, guild: discord.Guild, name: str, topic: str) -> discord.TextChannel:
        category = await self._get_category(guild)
        overwrites = dict(category.overwrites) if category else {}
        overwrites[guild.default_role] = discord.PermissionOverwrite(read_messages=False)
        return await guild.create_text_channel(
            name=name,
            category=category,
            overwrites=overwrites,
            topic=topic,
        )

    # ── Appeal task loop ───────────────────────────────────────────────

    @tasks.loop(seconds=30)
    async def appeal_check(self):
        if not config.MODMAIL_CATEGORY_ID:
            return
        guild = None
        for g in self.bot.guilds:
            if g.get_channel(config.MODMAIL_CATEGORY_ID):
                guild = g
                break
        if not guild:
            return

        async with aiosqlite.connect(database.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM ban_appeals WHERE status = 'pending' ORDER BY created_at ASC"
            ) as cur:
                appeals = await cur.fetchall()

            for appeal in appeals:
                try:
                    safe = self._safe_name(appeal["discord_username"])
                    channel = await self._create_channel(
                        guild,
                        name=f"appeal-{safe}",
                        topic=f"Ban Appeal | {appeal['discord_username']} ({appeal['discord_id']})",
                    )
                    embed = discord.Embed(
                        title="\U0001f6a8 Ban Appeal",
                        color=discord.Color.red(),
                        timestamp=discord.utils.utcnow(),
                    )
                    embed.add_field(name="Discord Username", value=appeal["discord_username"], inline=True)
                    embed.add_field(name="Discord ID", value=f"`{appeal['discord_id']}`", inline=True)
                    embed.add_field(name="\u200b", value="\u200b", inline=True)
                    embed.add_field(
                        name="Why they think they were banned",
                        value=appeal["ban_reason"] or "*Not provided*",
                        inline=False
                    )
                    embed.add_field(
                        name="Appeal Message",
                        value=appeal["appeal_message"][:1000],
                        inline=False
                    )
                    embed.set_footer(text=f"Appeal #{appeal['id']} \u00b7 Submitted via web panel")
                    await channel.send(
                        embed=embed,
                        content="Use `!close accept [reason]` or `!close deny [reason]` to resolve."
                    )
                    await db.execute(
                        "UPDATE ban_appeals SET status = 'open', channel_id = ? WHERE id = ?",
                        (channel.id, appeal["id"])
                    )
                    await db.commit()
                except Exception as e:
                    print(f"[ModMail] Appeal #{appeal['id']} channel creation failed: {e}")

    @appeal_check.before_loop
    async def before_appeal_check(self):
        await self.bot.wait_until_ready()

    # ── DM listener ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # ─ Incoming DM ─────────────────────────────────────────────
        if isinstance(message.channel, discord.DMChannel):
            if not config.MODMAIL_CATEGORY_ID:
                return
            user_id    = str(message.author.id)
            channel_id = await self._get_channel_id(user_id)
            channel    = self.bot.get_channel(channel_id) if channel_id else None

            if not channel:
                guild = None
                for g in self.bot.guilds:
                    if g.get_channel(config.MODMAIL_CATEGORY_ID):
                        guild = g
                        break
                if not guild:
                    return
                channel = await self._create_channel(
                    guild,
                    name=f"mail-{self._safe_name(message.author.name)}",
                    topic=f"ModMail | {message.author} ({message.author.id})",
                )
                await self._open_session(user_id, channel.id)
                intro = discord.Embed(
                    title="\U0001f4ec New ModMail",
                    color=discord.Color.blurple(),
                    description=(
                        f"**User:** {message.author.mention} (`{message.author.id}`)\n"
                        f"**Account age:** <t:{int(message.author.created_at.timestamp())}:R>\n\n"
                        f"Just type here to reply \u2014 messages are forwarded to the user's DMs.\n"
                        f"Use `!close [reason]` to close and delete this channel."
                    )
                )
                intro.set_thumbnail(url=message.author.display_avatar.url)
                await channel.send(embed=intro)
                try:
                    await message.author.send(embed=discord.Embed(
                        title="\U0001f4ec ModMail opened",
                        description="Your message has been received. Staff will reply here shortly.",
                        color=discord.Color.blurple()
                    ))
                except discord.Forbidden:
                    pass

            embed = discord.Embed(
                description=message.content or "*[no text content]*",
                color=0x5865f2,
                timestamp=message.created_at,
            )
            embed.set_author(name=f"{message.author} (User)", icon_url=message.author.display_avatar.url)
            if message.attachments:
                embed.add_field(name="Attachments", value="\n".join(a.url for a in message.attachments), inline=False)
            await channel.send(embed=embed)
            await message.add_reaction("\u2705")
            return

        # ─ Staff reply in modmail/appeal channel ──────────────────────
        if isinstance(message.channel, discord.TextChannel):
            if message.channel.category_id != config.MODMAIL_CATEGORY_ID:
                return
            if message.content.startswith(config.PREFIX):
                return
            user_id = await self._get_user_id(message.channel.id)
            if not user_id:
                return
            try:
                user = self.bot.get_user(int(user_id)) or await self.bot.fetch_user(int(user_id))
            except Exception:
                return
            embed = discord.Embed(
                description=message.content or "*[no text content]*",
                color=0x57f287,
                timestamp=message.created_at,
            )
            embed.set_author(name=f"Staff \u00b7 {message.author.display_name}", icon_url=message.author.display_avatar.url)
            embed.set_footer(text="Reply from the moderation team")
            if message.attachments:
                embed.add_field(name="Attachments", value="\n".join(a.url for a in message.attachments), inline=False)
            try:
                await user.send(embed=embed)
                await message.add_reaction("\u2705")
            except discord.Forbidden:
                await message.add_reaction("\u274c")
                await message.channel.send("\u26a0\ufe0f Could not DM user \u2014 DMs may be disabled.", delete_after=10)

    # ── Commands ──────────────────────────────────────────────────────────

    @commands.command(name="close")
    @commands.has_permissions(manage_messages=True)
    async def close_thread(self, ctx, verdict: str = None, *, reason: str = "No reason provided"):
        """Close a ModMail or appeal channel. Usage: !close [accept|deny] [reason]"""
        if not isinstance(ctx.channel, discord.TextChannel):
            return
        if ctx.channel.category_id != config.MODMAIL_CATEGORY_ID:
            return

        # Check if this is an appeal channel
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT id, discord_id, discord_username FROM ban_appeals WHERE channel_id = ? AND status = 'open'",
                (ctx.channel.id,)
            ) as cur:
                appeal = await cur.fetchone()

        if appeal:
            appeal_id, discord_id, discord_username = appeal
            status = verdict.lower() if verdict in ("accept", "deny") else "closed"
            async with aiosqlite.connect(database.DB_PATH) as db:
                await db.execute(
                    "UPDATE ban_appeals SET status = ? WHERE id = ?",
                    (status, appeal_id)
                )
                await db.commit()
            await ctx.send(f"\u2705 Appeal #{appeal_id} marked as **{status}**. Reason: {reason}")
            await ctx.channel.delete(reason=f"Appeal {status} by {ctx.author}: {reason}")
            return

        # Regular modmail
        user_id = await self._get_user_id(ctx.channel.id)
        if not user_id:
            await ctx.send("\u274c No active session found for this channel.")
            return
        try:
            user = self.bot.get_user(int(user_id)) or await self.bot.fetch_user(int(user_id))
            await user.send(embed=discord.Embed(
                title="\U0001f4ea ModMail Closed",
                description=f"Your modmail has been closed by staff.\n**Reason:** {reason}",
                color=discord.Color.red()
            ))
        except Exception:
            pass
        await self._close_session(user_id)
        await ctx.send(f"\u2705 Closing. Reason: {reason}")
        await ctx.channel.delete(reason=f"ModMail closed by {ctx.author}: {reason}")


async def setup(bot):
    await bot.add_cog(ModMail(bot))
