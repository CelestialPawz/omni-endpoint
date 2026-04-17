import discord
from discord.ext import commands

CUSTOM_COMMANDS = {
    "info": "OMNI Endpoint \u2014 Server management + StarServer monitoring bot. Developed by Axel @ Crystal Kitsune Studios.",
    "rules": "1. Be respectful.\n2. No spam.\n3. No NSFW outside designated channels.\n4. Follow Discord ToS.",
    "cks": "Crystal Kitsune Studios \u2014 https://crystal-kitsune-studios.com",
}

class CustomCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.content.startswith("!"):
            return
        cmd = message.content[1:].split()[0].lower()
        if cmd in CUSTOM_COMMANDS:
            await message.channel.send(CUSTOM_COMMANDS[cmd])

async def setup(bot):
    await bot.add_cog(CustomCommands(bot))
