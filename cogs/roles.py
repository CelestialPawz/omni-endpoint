import discord
from discord.ext import commands
import config

class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not config.AUTO_ROLE_ID:
            return
        role = member.guild.get_role(config.AUTO_ROLE_ID)
        if role:
            await member.add_roles(role, reason="Auto-role on join")

    @commands.command(name="role")
    @commands.has_permissions(manage_roles=True)
    async def assign_role(self, ctx, member: discord.Member, *, role: discord.Role):
        """Assign a role to a member. Usage: !role @user RoleName"""
        await member.add_roles(role)
        await ctx.send(f"\u2705 Gave **{role.name}** to {member.mention}.")

    @commands.command(name="removerole")
    @commands.has_permissions(manage_roles=True)
    async def remove_role(self, ctx, member: discord.Member, *, role: discord.Role):
        """Remove a role from a member. Usage: !removerole @user RoleName"""
        await member.remove_roles(role)
        await ctx.send(f"\u2705 Removed **{role.name}** from {member.mention}.")

async def setup(bot):
    await bot.add_cog(Roles(bot))
