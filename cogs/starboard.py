import discord
from discord.ext import commands
import aiosqlite
import database

STAR_EMOJI = "\u2b50"

class Starboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if str(payload.emoji) != STAR_EMOJI or not payload.guild_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        channel_id = await database.get_setting(str(guild.id), "starboard_channel_id")
        threshold = await database.get_setting(str(guild.id), "starboard_threshold") or 3
        if not channel_id:
            return
        sb_channel = guild.get_channel(int(channel_id))
        if not sb_channel:
            return
        src_channel = guild.get_channel(payload.channel_id)
        if not src_channel or src_channel.id == sb_channel.id:
            return
        try:
            message = await src_channel.fetch_message(payload.message_id)
        except Exception:
            return
        star_reaction = discord.utils.get(message.reactions, emoji=STAR_EMOJI)
        star_count = star_reaction.count if star_reaction else 0
        embed = discord.Embed(description=message.content or "", color=discord.Color.gold())
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        embed.add_field(name="Source", value=f"[Jump to message]({message.jump_url})")
        if message.attachments:
            embed.set_image(url=message.attachments[0].url)
        embed.set_footer(text=f"{STAR_EMOJI} {star_count} \u2022 #{src_channel.name}")
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT starboard_message_id FROM starboard_entries WHERE guild_id = ? AND message_id = ?",
                (str(guild.id), str(message.id))
            ) as cur:
                row = await cur.fetchone()
            if not row and star_count >= int(threshold):
                sb_msg = await sb_channel.send(embed=embed)
                await db.execute(
                    "INSERT INTO starboard_entries (guild_id, message_id, starboard_message_id, star_count) VALUES (?, ?, ?, ?)",
                    (str(guild.id), str(message.id), str(sb_msg.id), star_count)
                )
                await db.commit()
            elif row and row[0]:
                try:
                    sb_msg = await sb_channel.fetch_message(int(row[0]))
                    await sb_msg.edit(embed=embed)
                except Exception:
                    pass
                await db.execute(
                    "UPDATE starboard_entries SET star_count = ? WHERE guild_id = ? AND message_id = ?",
                    (star_count, str(guild.id), str(message.id))
                )
                await db.commit()

    @commands.command(name="setstarboard")
    @commands.has_permissions(manage_guild=True)
    async def set_starboard(self, ctx, channel: discord.TextChannel, threshold: int = 3):
        """Set the starboard channel. Usage: !setstarboard #channel [threshold]"""
        await database.set_setting(str(ctx.guild.id), "starboard_channel_id", str(channel.id))
        await database.set_setting(str(ctx.guild.id), "starboard_threshold", threshold)
        await ctx.send(f"\u2b50 Starboard set to {channel.mention} with threshold **{threshold}** stars.")

async def setup(bot):
    await bot.add_cog(Starboard(bot))
