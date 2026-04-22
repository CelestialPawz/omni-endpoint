import discord
from discord.ext import commands
import aiosqlite
import database
import config


class ModMail(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── DB helpers ──────────────────────────────────────────────────────

    async def _get_thread_id(self, user_id: str):
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT thread_id FROM modmail_sessions WHERE user_id = ? AND closed = 0",
                (user_id,)
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else None

    async def _get_user_id(self, thread_id: int):
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT user_id FROM modmail_sessions WHERE thread_id = ? AND closed = 0",
                (thread_id,)
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else None

    async def _open_session(self, user_id: str, thread_id: int):
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO modmail_sessions (user_id, thread_id, closed) VALUES (?, ?, 0)",
                (user_id, thread_id)
            )
            await db.commit()

    async def _close_session(self, user_id: str):
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "UPDATE modmail_sessions SET closed = 1 WHERE user_id = ?",
                (user_id,)
            )
            await db.commit()

    # ── Listener ─────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # ─ Incoming DM from user ─────────────────────────────────────
        if isinstance(message.channel, discord.DMChannel):
            if not config.MODMAIL_CHANNEL_ID:
                return
            channel = self.bot.get_channel(config.MODMAIL_CHANNEL_ID)
            if not channel:
                return

            user_id   = str(message.author.id)
            thread_id = await self._get_thread_id(user_id)
            thread    = None

            if thread_id:
                thread = channel.guild.get_thread(thread_id)
                if thread and thread.archived:
                    try:
                        await thread.edit(archived=False)
                    except Exception:
                        thread = None

            if not thread:
                thread = await channel.create_thread(
                    name=f"{message.author.name} ({message.author.id})",
                    type=discord.ChannelType.private_thread,
                    auto_archive_duration=10080,
                    invitable=False,
                )
                await self._open_session(user_id, thread.id)
                intro = discord.Embed(
                    title="\U0001f4ec New ModMail Thread",
                    color=discord.Color.blurple(),
                    description=(
                        f"**User:** {message.author.mention} (`{message.author.id}`)\n"
                        f"**Account age:** <t:{int(message.author.created_at.timestamp())}:R>\n\n"
                        f"Reply here to message the user.\n"
                        f"Use `!close [reason]` to close this thread."
                    )
                )
                intro.set_thumbnail(url=message.author.display_avatar.url)
                await thread.send(embed=intro)
                try:
                    await message.author.send(
                        embed=discord.Embed(
                            title="\U0001f4ec ModMail opened",
                            description="Your message has been received. Staff will reply here shortly.",
                            color=discord.Color.blurple()
                        )
                    )
                except discord.Forbidden:
                    pass

            # Forward user message to thread
            embed = discord.Embed(
                description=message.content or "*[no text content]*",
                color=0x5865f2,
                timestamp=message.created_at,
            )
            embed.set_author(
                name=f"{message.author} (User)",
                icon_url=message.author.display_avatar.url
            )
            if message.attachments:
                embed.add_field(
                    name="Attachments",
                    value="\n".join(a.url for a in message.attachments),
                    inline=False
                )
            await thread.send(embed=embed)
            await message.add_reaction("\u2705")
            return

        # ─ Staff reply in modmail thread ──────────────────────────
        if isinstance(message.channel, discord.Thread):
            if message.channel.parent_id != config.MODMAIL_CHANNEL_ID:
                return
            if message.content.startswith(config.PREFIX):
                return  # let commands handle it

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
            embed.set_author(
                name=f"Staff \u00b7 {message.author.display_name}",
                icon_url=message.author.display_avatar.url
            )
            embed.set_footer(text="Reply from the moderation team")
            if message.attachments:
                embed.add_field(
                    name="Attachments",
                    value="\n".join(a.url for a in message.attachments),
                    inline=False
                )
            try:
                await user.send(embed=embed)
                await message.add_reaction("\u2705")
            except discord.Forbidden:
                await message.add_reaction("\u274c")
                await message.channel.send(
                    "\u26a0\ufe0f Could not DM user \u2014 they may have DMs disabled.",
                    delete_after=10
                )

    # ── Commands ──────────────────────────────────────────────────────────

    @commands.command(name="close")
    @commands.has_permissions(manage_messages=True)
    async def close_thread(self, ctx, *, reason: str = "No reason provided"):
        """Close a ModMail thread. Usage: !close [reason]"""
        if not isinstance(ctx.channel, discord.Thread):
            await ctx.send("\u274c This command can only be used inside a ModMail thread.", delete_after=5)
            return
        if ctx.channel.parent_id != config.MODMAIL_CHANNEL_ID:
            return

        user_id = await self._get_user_id(ctx.channel.id)
        if not user_id:
            await ctx.send("\u274c No active session found for this thread.")
            return

        try:
            user = self.bot.get_user(int(user_id)) or await self.bot.fetch_user(int(user_id))
            await user.send(embed=discord.Embed(
                title="\U0001f4ea ModMail Closed",
                description=f"Your modmail thread has been closed by staff.\n**Reason:** {reason}",
                color=discord.Color.red()
            ))
        except Exception:
            pass

        await self._close_session(user_id)
        await ctx.send(f"\u2705 Thread closed. Reason: {reason}")
        await ctx.channel.edit(archived=True, locked=True)


async def setup(bot):
    await bot.add_cog(ModMail(bot))
