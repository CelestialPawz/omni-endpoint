import discord
from discord.ext import commands

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.remove_command("help")

    @commands.command(name="help")
    async def help_cmd(self, ctx):
        """Show this help message."""
        embed = discord.Embed(
            title="\U0001f916 OMNI Endpoint \u2014 Command Reference",
            description="Prefix: `!` \u00b7 Slash commands also available.",
            color=discord.Color.blurple()
        )
        embed.add_field(
            name="\U0001f4ca Server Status",
            value="`!ss` / `!serverstatus` \u2014 Full StarServer status\n`!pihole` \u2014 Pi-hole stats\n`!sshstatus` \u2014 Deep SSH *(Admin)*",
            inline=False
        )
        embed.add_field(
            name="\U0001f6e1\ufe0f Moderation",
            value=(
                "`!ban` `!kick` `!mute` `!unmute` `!purge` `!unban`\n"
                "`!slowmode` `!lock` `!unlock` `!announce`\n"
                "*Requires mod role.*"
            ),
            inline=False
        )
        embed.add_field(
            name="\u26a0\ufe0f Warnings",
            value="`!warn` `!warnings` `!clearwarns`",
            inline=False
        )
        embed.add_field(
            name="\U0001f4cb Mod Notes & Logs",
            value="`!note @user <text>` \u2014 Private note\n`!modlogs @user` / `!ml` \u2014 Full history",
            inline=False
        )
        embed.add_field(
            name="\U0001f3f7\ufe0f Tags",
            value=(
                "`!tag <name>` \u00b7 `!tag add/edit/remove/list/info`\n"
                "Slash: `/tag` `/taglist` `/tagadd` `/tagedit` `/tagremove`"
            ),
            inline=False
        )
        embed.add_field(
            name="\u2139\ufe0f Utility",
            value="`!ping` `!uptime` `!stats` `!avatar` `!userinfo` `!serverinfo`",
            inline=False
        )
        embed.add_field(
            name="\u2b50 Levels",
            value=(
                "`!rank [@user]` / `!level` / `!xp` \u2014 Rank card\n"
                "`!leaderboard [page]` / `!lb` / `!top` \u2014 XP leaderboard\n"
                "`!setlevelrole <lvl> @Role` \u2014 Role reward\n"
                "`!levelroles` \u2014 List role rewards\n"
                "`!givexp @user <n>` \u00b7 `!resetxp @user` \u2014 Admin tools"
            ),
            inline=False
        )
        embed.add_field(
            name="\u23f0 Reminders",
            value="`!remindme <time> <msg>` \u00b7 `!reminders` \u00b7 `!delreminder <id>`",
            inline=False
        )
        embed.add_field(
            name="\u2b50 Starboard",
            value="`!setstarboard #ch [threshold]`",
            inline=False
        )
        embed.add_field(
            name="\U0001f3ae Fun",
            value=(
                "`!8ball` `!coinflip` `!roll` `!meme` `!joke` `!fact`\n"
                "`!poll` `!rps` `!trivia` `!wouldyourather` `!ship` `!define`"
            ),
            inline=False
        )
        embed.add_field(
            name="\U0001f916 AI Chat",
            value="Mention me to chat with OMNI. `!clearhistory` to reset.",
            inline=False
        )
        embed.set_footer(text="OMNI Endpoint | Crystal Kitsune Studios")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Help(bot))
