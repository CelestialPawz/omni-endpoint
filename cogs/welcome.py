import discord
from discord.ext import commands
import config

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        ch = member.guild.get_channel(config.WELCOME_CHANNEL_ID)
        if not ch:
            return
        embed = discord.Embed(
            title="Welcome to the server!",
            description=f"Glad to have you, {member.mention}. Read the rules and enjoy your stay.",
            color=discord.Color.teal()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Member #{member.guild.member_count}")
        await ch.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        ch = member.guild.get_channel(config.WELCOME_CHANNEL_ID)
        if not ch:
            return
        await ch.send(f"**{member.display_name}** has left the server. \U0001f44b")

async def setup(bot):
    await bot.add_cog(Welcome(bot))
