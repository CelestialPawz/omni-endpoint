import discord
from discord.ext import commands
import aiosqlite
import re
import database
import config


class ModMail(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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

    def _channel_name(self, user: discord.User) -> str:
        safe = re.sub(r"[^a-z0-9-]", "-", user.name.lower())
        safe = re.sub(r"-+", "-", safe).strip("-") or "user"
        return f"mail-{safe}"

    async def _get_category(self, guild: discord.Guild) -> discord.CategoryChannel | None:
        cat = guild.get_channel(config.MODMAIL_CATEGORY_ID)
        if cat and isinstance(cat, discord.CategoryChannel):
            return cat
        return None

    # ── Listener ─────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # ─ Incoming DM from user ─────────────────────────────────────
        if isinstance(message.channel, discord.DMChannel):
            if not config.MODMAIL_CATEGORY_ID:
                return

            user_id    = str(message.author.id)
            channel_id = await self._get_channel_id(user_id)
            channel    = self.bot.get_channel(channel_id) if channel_id else None

            if not channel:
                # Find the guild via the category
                guild = None
                for g in self.bot.guilds:
                    cat = g.get_channel(config.MODMAIL_CATEGORY_ID)
                    if cat:
                        guild = g
                        break
                if not guild:
                    return

                category = await self._get_category(guild)
                if not category:
                    return

                # Create a new channel in the category
                overwrites = dict(category.overwrites)
                overwrites[guild.default_role] = discord.PermissionOverwrite(read_messages=False)
                channel = await guild.create_text_channel(
                    name=self._channel_name(message.author),
                    category=category,
                    overwrites=overwrites,
                    topic=f"ModMail | {message.author} ({message.author.id})",
                    reason=f"ModMail opened by {message.author}",
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
                    await message.author.send(
                        embed=discord.Embed(
                            title="\U0001f4ec ModMail opened",
                            description="Your message has been received. Staff will reply here shortly.",
                            color=discord.Color.blurple()
                        )
                    )
                except discord.Forbidden:
                    pass

            # Forward user message to staff channel
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
            await channel.send(embed=embed)
            await message.add_reaction("\u2705")
            return

        # ─ Staff reply in modmail channel ──────────────────────────
        if isinstance(message.channel, discord.TextChannel):
            if not message.channel.category_id == config.MODMAIL_CATEGORY_ID:
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
        """Close a ModMail channel. Usage: !close [reason]"""
        if not isinstance(ctx.channel, discord.TextChannel):
            return
        if ctx.channel.category_id != config.MODMAIL_CATEGORY_ID:
            return

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
