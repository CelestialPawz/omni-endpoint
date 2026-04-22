import discord
from discord.ext import commands
import asyncio
import yt_dlp
from collections import deque

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data     = data
        self.title    = data.get('title', 'Unknown')
        self.url      = data.get('webpage_url', '')
        self.duration = data.get('duration', 0)
        self.thumbnail = data.get('thumbnail')
        self.uploader  = data.get('uploader', 'Unknown')

    @classmethod
    async def from_query(cls, query: str, *, loop=None, volume=0.5):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
        if 'entries' in data:
            data = data['entries'][0]
        url = data['url']
        return cls(discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS), data=data, volume=volume)

    @staticmethod
    def fmt_duration(seconds):
        if not seconds:
            return '?'
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f'{h}:{m:02}:{s:02}' if h else f'{m}:{s:02}'


class GuildMusic:
    def __init__(self):
        self.queue:   deque   = deque()
        self.current: YTDLSource | None = None
        self.volume:  float   = 0.5
        self.loop:    bool    = False


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot   = bot
        self._data: dict[int, GuildMusic] = {}

    def _guild(self, guild_id: int) -> GuildMusic:
        if guild_id not in self._data:
            self._data[guild_id] = GuildMusic()
        return self._data[guild_id]

    def _after(self, ctx, error):
        if error:
            print(f'[Music] Player error: {error}')
        fut = asyncio.run_coroutine_threadsafe(self._next(ctx), self.bot.loop)
        try:
            fut.result()
        except Exception as e:
            print(f'[Music] _after error: {e}')

    async def _next(self, ctx):
        gm = self._guild(ctx.guild.id)
        if gm.loop and gm.current:
            # re-fetch and replay current
            try:
                src = await YTDLSource.from_query(gm.current.url, loop=self.bot.loop, volume=gm.volume)
                gm.current = src
                ctx.voice_client.play(src, after=lambda e: self._after(ctx, e))
                return
            except Exception:
                pass
        if gm.queue:
            query = gm.queue.popleft()
            try:
                src = await YTDLSource.from_query(query, loop=self.bot.loop, volume=gm.volume)
                gm.current = src
                ctx.voice_client.play(src, after=lambda e: self._after(ctx, e))
                await ctx.send(embed=self._np_embed(src, '\U0001f3b5 Now Playing'))
            except Exception as e:
                await ctx.send(f'\u274c Could not play next track: `{e}`')
                await self._next(ctx)
        else:
            gm.current = None

    def _np_embed(self, src: YTDLSource, title='\U0001f3b5 Now Playing') -> discord.Embed:
        e = discord.Embed(title=title, description=f'[{src.title}]({src.url})', color=discord.Color.blurple())
        e.add_field(name='Duration', value=YTDLSource.fmt_duration(src.duration), inline=True)
        e.add_field(name='Uploader', value=src.uploader, inline=True)
        if src.thumbnail:
            e.set_thumbnail(url=src.thumbnail)
        return e

    # ── Commands ──────────────────────────────────────────────────────────

    @commands.command(name='play', aliases=['p'])
    async def play(self, ctx, *, query: str):
        """Play a song or add it to the queue. Usage: !play <title or URL>"""
        if not ctx.author.voice:
            return await ctx.send('\u274c Join a voice channel first.')

        vc = ctx.voice_client
        if not vc:
            vc = await ctx.author.voice.channel.connect()
        elif ctx.author.voice.channel != vc.channel:
            await vc.move_to(ctx.author.voice.channel)

        gm = self._guild(ctx.guild.id)

        if vc.is_playing() or vc.is_paused():
            gm.queue.append(query)
            await ctx.send(f'\u23f3 Added to queue: **{query}** (position {len(gm.queue)})')
            return

        async with ctx.typing():
            try:
                src = await YTDLSource.from_query(query, loop=self.bot.loop, volume=gm.volume)
            except Exception as e:
                return await ctx.send(f'\u274c Could not retrieve audio: `{e}`')

        gm.current = src
        vc.play(src, after=lambda e: self._after(ctx, e))
        await ctx.send(embed=self._np_embed(src))

    @commands.command(name='skip', aliases=['s'])
    async def skip(self, ctx):
        """Skip the current track."""
        vc = ctx.voice_client
        if not vc or not vc.is_playing():
            return await ctx.send('\u274c Nothing is playing.')
        vc.stop()
        await ctx.message.add_reaction('\u23ed\ufe0f')

    @commands.command(name='pause')
    async def pause(self, ctx):
        """Pause playback."""
        vc = ctx.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await ctx.message.add_reaction('\u23f8\ufe0f')
        else:
            await ctx.send('\u274c Nothing is playing.')

    @commands.command(name='resume')
    async def resume(self, ctx):
        """Resume playback."""
        vc = ctx.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await ctx.message.add_reaction('\u25b6\ufe0f')
        else:
            await ctx.send('\u274c Not paused.')

    @commands.command(name='stop', aliases=['disconnect', 'dc', 'leave'])
    async def stop(self, ctx):
        """Stop playback and disconnect."""
        gm = self._guild(ctx.guild.id)
        gm.queue.clear()
        gm.current = None
        vc = ctx.voice_client
        if vc:
            await vc.disconnect()
            await ctx.message.add_reaction('\u23f9\ufe0f')

    @commands.command(name='queue', aliases=['q'])
    async def queue(self, ctx):
        """Show the current queue."""
        gm = self._guild(ctx.guild.id)
        if not gm.current and not gm.queue:
            return await ctx.send('\U0001f4ed The queue is empty.')
        e = discord.Embed(title='\U0001f3b6 Queue', color=discord.Color.blurple())
        if gm.current:
            e.add_field(
                name='\U0001f3b5 Now Playing',
                value=f'[{gm.current.title}]({gm.current.url}) `{YTDLSource.fmt_duration(gm.current.duration)}`',
                inline=False
            )
        if gm.queue:
            lines = []
            for i, q in enumerate(list(gm.queue)[:10], 1):
                lines.append(f'`{i}.` {q}')
            if len(gm.queue) > 10:
                lines.append(f'*...and {len(gm.queue) - 10} more*')
            e.add_field(name='Up next', value='\n'.join(lines), inline=False)
        e.set_footer(text=f'Loop: {"\u2705" if gm.loop else "\u274c"}')
        await ctx.send(embed=e)

    @commands.command(name='nowplaying', aliases=['np'])
    async def nowplaying(self, ctx):
        """Show the currently playing track."""
        gm = self._guild(ctx.guild.id)
        if not gm.current:
            return await ctx.send('\u274c Nothing is playing.')
        await ctx.send(embed=self._np_embed(gm.current))

    @commands.command(name='volume', aliases=['vol'])
    async def volume(self, ctx, vol: int):
        """Set volume (1-100). Usage: !volume 75"""
        if not 1 <= vol <= 100:
            return await ctx.send('\u274c Volume must be between 1 and 100.')
        gm = self._guild(ctx.guild.id)
        gm.volume = vol / 100
        vc = ctx.voice_client
        if vc and vc.source:
            vc.source.volume = gm.volume
        await ctx.send(f'\U0001f509 Volume set to **{vol}%**')

    @commands.command(name='loop')
    async def loop(self, ctx):
        """Toggle loop for the current track."""
        gm = self._guild(ctx.guild.id)
        gm.loop = not gm.loop
        await ctx.send(f'\U0001f501 Loop: {"\u2705 enabled" if gm.loop else "\u274c disabled"}')

    @commands.command(name='clear')
    async def clear_queue(self, ctx):
        """Clear the queue without stopping the current track."""
        gm = self._guild(ctx.guild.id)
        gm.queue.clear()
        await ctx.send('\U0001f9f9 Queue cleared.')


async def setup(bot):
    await bot.add_cog(Music(bot))
