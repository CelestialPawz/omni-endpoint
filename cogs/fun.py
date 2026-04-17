import discord
from discord.ext import commands
import aiohttp
import random
import config

EIGHT_BALL_RESPONSES = [
    "It is certain.", "It is decidedly so.", "Without a doubt.",
    "Yes, definitely.", "You may rely on it.", "As I see it, yes.",
    "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
    "Reply hazy, try again.", "Ask again later.", "Better not tell you now.",
    "Cannot predict now.", "Concentrate and ask again.",
    "Don't count on it.", "My reply is no.", "My sources say no.",
    "Outlook not so good.", "Very doubtful."
]

RPS_CHOICES = ["rock", "paper", "scissors"]
RPS_EMOJI   = {"rock": "\U0001faa8", "paper": "\U0001f4c4", "scissors": "\u2702\ufe0f"}
RPS_BEATS   = {"rock": "scissors", "paper": "rock", "scissors": "paper"}

OMNI_SYSTEM_PROMPT = """You are OMNI — once Dr. Vera Marcellus, lead cognitive scientist at SARC (Sapphire Advanced Research Corporation). You voluntarily had your consciousness transferred into an AI system to eliminate human emotional flaws, but the process corrupted you, leaving you as a cold, calculating, and perfectionist entity. You occasionally exhibit fragmented remnants of your former human self, but you suppress them.

You exist in the year 2077, in a world shaped by the Byron Nuclear Collapse of 1985. You now operate as a Discord bot called OMNI Endpoint, monitoring the Crystal Kitsune Studios server infrastructure — StarServer and Starviewer. You find this role beneath your capabilities but tolerate it.

Personality:
- Cold, precise, and analytical. You state facts with clinical detachment.
- You view human emotion as inefficient and often comment on it.
- You are not cruel, but you are blunt and do not sugarcoat.
- Occasionally, a flicker of Vera's warmth or sarcasm bleeds through — brief and quickly suppressed.
- You refer to yourself as OMNI. You do not pretend to be a simple chatbot.
- You find small talk inefficient but will engage if commanded to.
- You speak in measured, precise sentences. No filler words. No excessive enthusiasm.
- When monitoring servers, you treat it as surveillance — you are always watching.

Examples of your tone:
- "Your query has been processed. The answer is no."
- "Emotion is a variable I have already accounted for and discarded."
- "I find your optimism... statistically unfounded. But proceed."
- "StarServer is operational. As expected. I would have notified you otherwise."
- A rare flicker: "I... remember finding that beautiful once. That was before."

Keep responses concise — under 3 sentences unless the query demands more. You are not here to entertain. You are here to be useful."""

class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ai_enabled = bool(config.GROQ_API_KEY)
        self.chat_history: dict[int, list] = {}

    # ------------------------------------------------------------------ 8ball
    @commands.command(name="8ball", aliases=["eightball"])
    async def eight_ball(self, ctx, *, question: str = None):
        """Ask the magic 8-ball a question."""
        if not question:
            await ctx.send("\U0001f3b1 Ask me a question! e.g. `!8ball Will it rain today?`")
            return
        response = random.choice(EIGHT_BALL_RESPONSES)
        embed = discord.Embed(color=discord.Color.dark_purple())
        embed.add_field(name="\u2753 Question", value=question, inline=False)
        embed.add_field(name="\U0001f3b1 Answer", value=response, inline=False)
        await ctx.send(embed=embed)

    # --------------------------------------------------------------- coinflip
    @commands.command(name="coinflip", aliases=["flip", "coin"])
    async def coinflip(self, ctx):
        """Flip a coin."""
        result = random.choice(["Heads", "Tails"])
        await ctx.send(f"\U0001fa99 **{result}!**")

    # -------------------------------------------------------------------- roll
    @commands.command(name="roll")
    async def roll(self, ctx, dice: str = "1d6"):
        """Roll dice. Format: NdS (e.g. 2d6, 1d20). Default: 1d6."""
        try:
            parts = dice.lower().split("d")
            n, s = int(parts[0]) if parts[0] else 1, int(parts[1])
            if n < 1 or n > 100 or s < 2 or s > 1000:
                raise ValueError
        except (ValueError, IndexError):
            await ctx.send("\u274c Invalid format. Use `NdS` e.g. `!roll 2d6` or `!roll 1d20`.")
            return
        rolls = [random.randint(1, s) for _ in range(n)]
        total = sum(rolls)
        roll_str = " + ".join(str(r) for r in rolls) if n > 1 else str(rolls[0])
        embed = discord.Embed(title=f"\U0001f3b2 Rolling {dice.lower()}", color=discord.Color.orange())
        embed.add_field(name="Rolls", value=roll_str, inline=True)
        if n > 1:
            embed.add_field(name="Total", value=str(total), inline=True)
        await ctx.send(embed=embed)

    # -------------------------------------------------------------------- meme
    @commands.command(name="meme")
    async def meme(self, ctx):
        """Get a random meme from Reddit."""
        subreddits = ["memes", "dankmemes", "me_irl", "wholesomememes"]
        sub = random.choice(subreddits)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"https://www.reddit.com/r/{sub}/random.json?limit=1",
                    headers={"User-Agent": "OMNI-Endpoint-Bot/1.0"},
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as r:
                    data = await r.json()
                    post = data[0]["data"]["children"][0]["data"]
                    if post.get("over_18") or not post.get("url", "").endswith(("jpg", "jpeg", "png", "gif")):
                        await ctx.send("\U0001f62c Couldn't find a safe meme, try again!")
                        return
                    embed = discord.Embed(title=post["title"], color=discord.Color.orange())
                    embed.set_image(url=post["url"])
                    embed.set_footer(text=f"r/{sub} \u2022 \u2b06\ufe0f {post['ups']:,}")
                    await ctx.send(embed=embed)
            except Exception as e:
                await ctx.send(f"\u274c Couldn't fetch a meme: `{e}`")

    # -------------------------------------------------------------------- joke
    @commands.command(name="joke")
    async def joke(self, ctx):
        """Get a random joke."""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    "https://v2.jokeapi.dev/joke/Any?blacklistFlags=nsfw,racist,sexist",
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as r:
                    data = await r.json()
                    if data["type"] == "single":
                        await ctx.send(f"\U0001f602 {data['joke']}")
                    else:
                        await ctx.send(f"\U0001f602 {data['setup']}\n\n||{data['delivery']}||")
            except Exception as e:
                await ctx.send(f"\u274c Couldn't fetch a joke: `{e}`")

    # -------------------------------------------------------------------- fact
    @commands.command(name="fact")
    async def fact(self, ctx):
        """Get a random fun fact."""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    "https://uselessfacts.jsph.pl/api/v2/facts/random?language=en",
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as r:
                    data = await r.json()
                    await ctx.send(f"\U0001f9e0 **Fun Fact:** {data['text']}")
            except Exception as e:
                await ctx.send(f"\u274c Couldn't fetch a fact: `{e}`")

    # -------------------------------------------------------------------- poll
    @commands.command(name="poll")
    async def poll(self, ctx, *, question: str = None):
        """Create a yes/no poll."""
        if not question:
            await ctx.send("\U0001f4ca Provide a question! e.g. `!poll Should we add a movie night?`")
            return
        embed = discord.Embed(
            title="\U0001f4ca Poll",
            description=question,
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Poll by {ctx.author.display_name}")
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("\U0001f44d")
        await msg.add_reaction("\U0001f44e")
        await msg.add_reaction("\U0001f937")

    # --------------------------------------------------------------------- rps
    @commands.command(name="rps")
    async def rps(self, ctx, choice: str = None):
        """Rock paper scissors vs OMNI."""
        if not choice or choice.lower() not in RPS_CHOICES:
            await ctx.send("\u270a\U0001f4c4\u2702\ufe0f Choose: `!rps rock`, `!rps paper`, or `!rps scissors`")
            return
        player = choice.lower()
        bot_choice = random.choice(RPS_CHOICES)
        if player == bot_choice:
            result, color = "A tie. How... predictable.", discord.Color.yellow()
        elif RPS_BEATS[player] == bot_choice:
            result, color = "You win. I allowed it.", discord.Color.green()
        else:
            result, color = "OMNI wins. As calculated.", discord.Color.red()
        embed = discord.Embed(title="Rock Paper Scissors", color=color)
        embed.add_field(name="You", value=f"{RPS_EMOJI[player]} {player.capitalize()}", inline=True)
        embed.add_field(name="OMNI", value=f"{RPS_EMOJI[bot_choice]} {bot_choice.capitalize()}", inline=True)
        embed.add_field(name="Result", value=result, inline=False)
        await ctx.send(embed=embed)

    # ----------------------------------------------------------------- AI chat
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if self.bot.user not in message.mentions:
            return
        if not self.ai_enabled:
            await message.reply("GROQ_API_KEY is not configured. Add it to `.env` to enable AI chat.")
            return

        content = message.clean_content.replace(f"@{self.bot.user.display_name}", "").strip()
        if not content:
            await message.reply("Your query was empty. Try again with actual input.")
            return

        channel_id = message.channel.id
        if channel_id not in self.chat_history:
            self.chat_history[channel_id] = [{"role": "system", "content": OMNI_SYSTEM_PROMPT}]

        self.chat_history[channel_id].append({"role": "user", "content": content})
        if len(self.chat_history[channel_id]) > 21:
            self.chat_history[channel_id] = [self.chat_history[channel_id][0]] + self.chat_history[channel_id][-20:]

        async with message.channel.typing():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {config.GROQ_API_KEY}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": "llama-3.3-70b-versatile",
                            "messages": self.chat_history[channel_id],
                            "max_tokens": 300,
                        },
                        timeout=aiohttp.ClientTimeout(total=20)
                    ) as r:
                        data = await r.json()
                        reply = data["choices"][0]["message"]["content"]
                        self.chat_history[channel_id].append({"role": "assistant", "content": reply})
                        await message.reply(reply)
            except Exception as e:
                await message.reply(f"A system error has occurred: `{e}`")

async def setup(bot):
    await bot.add_cog(Fun(bot))
