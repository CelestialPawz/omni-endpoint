import discord
from discord.ext import commands
import config

class Logs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _log(self, guild, embed):
        ch = guild.get_channel(config.LOG_CHANNEL_ID)
        if ch:
            await ch.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        embed = discord.Embed(
            title="\U0001f5d1\ufe0f Message Deleted",
            description=f"**Author:** {message.author.mention}\n**Channel:** {message.channel.mention}\n**Content:** {message.content[:500] or '*empty*'}",
            color=discord.Color.red()
        )
        await self._log(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild or before.content == after.content:
            return
        embed = discord.Embed(
            title="\u270f\ufe0f Message Edited",
            description=f"**Author:** {before.author.mention}\n**Channel:** {before.channel.mention}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Before", value=before.content[:400] or "*empty*", inline=False)
        embed.add_field(name="After", value=after.content[:400] or "*empty*", inline=False)
        await self._log(before.guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        embed = discord.Embed(title="\U0001f528 Member Banned", description=f"{user.mention} (`{user}`)", color=discord.Color.dark_red())
        await self._log(guild, embed)

async def setup(bot):
    await bot.add_cog(Logs(bot))
