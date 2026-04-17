import discord
from discord.ext import commands
from collections import defaultdict
import time
import re
import database
import config

INVITE_PATTERN = re.compile(r"(discord\.gg|discord\.com/invite)/[a-zA-Z0-9]+")

class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.message_log: dict[int, list[float]] = defaultdict(list)

    async def _log(self, guild, description: str):
        ch = guild.get_channel(config.LOG_CHANNEL_ID)
        if ch:
            embed = discord.Embed(
                title="\U0001f6e1\ufe0f AutoMod Action",
                description=description,
                color=discord.Color.orange()
            )
            await ch.send(embed=embed)

    async def _get(self, guild_id, key, default):
        val = await database.get_setting(str(guild_id), key)
        return val if val is not None else default

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if message.author.guild_permissions.manage_messages:
            return

        gid = message.guild.id
        content = message.content
        user_id = message.author.id
        now = time.time()

        # Spam check
        if await self._get(gid, "automod_spam", 1):
            threshold = int(await self._get(gid, "automod_spam_threshold", 5))
            timestamps = self.message_log[user_id]
            timestamps.append(now)
            self.message_log[user_id] = [t for t in timestamps if now - t < 5]
            if len(self.message_log[user_id]) >= threshold:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention} Spam detected. Slow down.",
                    delete_after=5
                )
                await self._log(message.guild, f"**Spam** from {message.author.mention} in {message.channel.mention}")
                await database.add_mod_log(str(gid), "automod_spam", str(self.bot.user.id), str(user_id))
                return

        # Caps check
        if await self._get(gid, "automod_caps", 1):
            caps_ratio = float(await self._get(gid, "automod_caps_ratio", 0.7))
            if len(content) >= 10:
                ratio = sum(1 for c in content if c.isupper()) / len(content)
                if ratio >= caps_ratio:
                    await message.delete()
                    await message.channel.send(
                        f"{message.author.mention} Ease up on the caps.",
                        delete_after=5
                    )
                    await self._log(message.guild, f"**Caps** from {message.author.mention}: `{content[:80]}`")
                    await database.add_mod_log(str(gid), "automod_caps", str(self.bot.user.id), str(user_id))
                    return

        # Invite filter
        if await self._get(gid, "automod_invites", 1):
            if INVITE_PATTERN.search(content):
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention} Discord invites are not allowed here.",
                    delete_after=5
                )
                await self._log(message.guild, f"**Invite link** from {message.author.mention}: `{content[:80]}`")
                await database.add_mod_log(str(gid), "automod_invite", str(self.bot.user.id), str(user_id))
                return

        # Banned links (static)
        for link in ["grabify", "bit.ly"]:
            if link in content.lower():
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention} That link is not permitted.",
                    delete_after=5
                )
                await self._log(message.guild, f"**Banned link** from {message.author.mention}: `{content[:80]}`")
                await database.add_mod_log(str(gid), "automod_link", str(self.bot.user.id), str(user_id))
                return

async def setup(bot):
    await bot.add_cog(AutoMod(bot))
