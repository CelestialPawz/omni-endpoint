import discord
from discord.ext import commands

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Remove default help command
        self.bot.remove_command("help")

    @commands.command(name="help")
    async def help_cmd(self, ctx):
        """Show this help message."""
        embed = discord.Embed(
            title="\U0001f916 OMNI Endpoint — Command Reference",
            description="I am OMNI. I monitor, moderate, and respond. Use the prefix `!`.",
            color=discord.Color.blurple()
        )

        embed.add_field(
            name="\U0001f4ca Server Status",
            value=(
                "`!ss` / `!serverstatus` \u2014 Full StarServer status\n"
                "`!pihole` \u2014 Pi-hole stats (Starviewer)\n"
                "`!sshstatus` \u2014 Deep SSH status *(Admin only)*"
            ),
            inline=False
        )

        embed.add_field(
            name="\U0001f6e1\ufe0f Moderation",
            value=(
                "`!ban <user> [reason]` \u2014 Ban a member\n"
                "`!kick <user> [reason]` \u2014 Kick a member\n"
                "`!mute <user> [minutes] [reason]` \u2014 Timeout a member\n"
                "`!purge [amount]` \u2014 Delete messages (default 10)\n"
                "`!unban <user_id>` \u2014 Unban by ID\n"
                "*Requires High Level Clearance or Low Clearance role.*"
            ),
            inline=False
        )

        embed.add_field(
            name="\U0001f3ae Fun",
            value=(
                "`!8ball <question>` \u2014 Magic 8-ball\n"
                "`!coinflip` \u2014 Heads or tails\n"
                "`!roll [NdS]` \u2014 Roll dice (e.g. `2d6`, `1d20`)\n"
                "`!meme` \u2014 Random meme\n"
                "`!joke` \u2014 Random joke\n"
                "`!fact` \u2014 Random fun fact\n"
                "`!poll <question>` \u2014 Quick poll\n"
                "`!rps <rock/paper/scissors>` \u2014 Play vs OMNI"
            ),
            inline=False
        )

        embed.add_field(
            name="\U0001f916 AI Chat",
            value="Mention me \u2014 `@OMNI Endpoint <message>` \u2014 and I will respond.",
            inline=False
        )

        embed.set_footer(text="OMNI Endpoint | Crystal Kitsune Studios")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Help(bot))
