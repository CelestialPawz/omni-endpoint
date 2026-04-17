import discord
from discord.ext import commands
from collections import defaultdict
import time
import config

SPAM_THRESHOLD = 5
SPAM_WINDOW    = 5
MAX_CAPS_RATIO = 0.7
MIN_CAPS_LEN   = 10

BANNED_LINKS = ["grabify", "discord.gift", "bit.ly"]

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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if message.author.guild_permissions.manage_messages:
            return

        content = message.content
        user_id = message.author.id
        now = time.time()

        timestamps = self.message_log[user_id]
        timestamps.append(now)
        self.message_log[user_id] = [t for t in timestamps if now - t < SPAM_WINDOW]
        if len(self.message_log[user_id]) >= SPAM_THRESHOLD:
            await message.delete()
            await message.channel.send(
                f"{message.author.mention} Slow down \u2014 spam detected.",
                delete_after=5
            )
            await self._log(message.guild, f"**Spam** from {message.author.mention} in {message.channel.mention}")
            return

        if len(content) >= MIN_CAPS_LEN:
            caps_ratio = sum(1 for c in content if c.isupper()) / len(content)
            if caps_ratio >= MAX_CAPS_RATIO:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention} Ease up on the caps.",
                    delete_after=5
                )
                await self._log(message.guild, f"**Caps** from {message.author.mention}: `{content[:80]}`")
                return

        for link in BANNED_LINKS:
            if link in content.lower():
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention} That link isn't allowed here.",
                    delete_after=5
                )
                await self._log(message.guild, f"**Banned link** from {message.author.mention}: `{content[:80]}`")
                return

async def setup(bot):
    await bot.add_cog(AutoMod(bot))
