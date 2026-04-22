import discord
from discord.ext import commands

ACTIVITIES: dict[str, tuple[str, int]] = {
    "watch":   ("Watch Together",    880218394199220334),
    "poker":   ("Poker Night",       755827207812677713),
    "chess":   ("Chess in the Park", 832012774040141894),
    "sketch":  ("Sketchy Artist",    879864070101172255),
    "letters": ("Letter League",     879863881349087252),
    "words":   ("Word Snacks",       879863976006127627),
    "spell":   ("SpellCast",         852509694341283871),
    "putt":    ("Putt Party",        945737671223947305),
    "land":    ("Land-io",           903769130790969345),
    "bobble":  ("Bobble League",     947957217959759964),
    "gartic":  ("Gartic Phone",      1007373802981822582),
    "jam":     ("Jamspace",          1070087967294631976),
}


class Activities(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="activity", aliases=["game", "vc"])
    async def activity(self, ctx, *, name: str = None):
        """Launch a Discord Activity in your voice channel. Usage: !activity <name>"""
        if not name:
            lines = "\n".join(f"`{k}` \u2014 {label}" for k, (label, _) in ACTIVITIES.items())
            embed = discord.Embed(
                title="\U0001f3ae Available Activities",
                description=lines,
                color=discord.Color.blurple()
            )
            embed.set_footer(text="Usage: !activity <name>  |  You must be in a voice channel")
            await ctx.send(embed=embed)
            return

        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("\u274c You need to be in a voice channel first.")
            return

        vc  = ctx.author.voice.channel
        key = name.lower().strip()

        # exact key match
        match = ACTIVITIES.get(key)
        # fuzzy: check if query appears in key or display name
        if not match:
            for k, (label, app_id) in ACTIVITIES.items():
                if key in k or key in label.lower():
                    match = (label, app_id)
                    break

        if not match:
            await ctx.send(
                f"\u274c Unknown activity `{name}`.\n"
                f"Use `!activity` to see the full list."
            )
            return

        label, app_id = match
        try:
            invite = await vc.create_invite(
                max_age=86400,
                target_type=discord.InviteTarget.embedded_application,
                target_application_id=app_id,
            )
            embed = discord.Embed(
                title=f"\U0001f3ae {label}",
                description=f"[\U0001f517 Click to launch in **{vc.name}**]({invite.url})",
                color=discord.Color.green()
            )
            embed.set_footer(text="Link expires in 24 hours")
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("\u274c I don't have permission to create invites in that voice channel.")
        except Exception as e:
            await ctx.send(f"\u274c Failed to create activity invite: `{e}`")


async def setup(bot):
    await bot.add_cog(Activities(bot))
