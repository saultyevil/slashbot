#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
from functools import partial

import disnake
from async_timeout import timeout
from disnake.ext import commands
from youtube_dl import YoutubeDL
from youtube_dl.postprocessor import ffmpeg

import config

cd_user = commands.BucketType.user


class VoiceConnectionError(commands.CommandError):
    """Custom Exception class for connection errors."""


class InvalidVoiceChannel(VoiceConnectionError):
    """Exception for cases of invalid Voice Channels."""


ytdlopts = {
    'format': 'bestaudio/best',
    'outtmpl': 'downloads/%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'  # ipv6 addresses cause issues sometimes
}

ffmpeg_options = {"options": "-vn"}

ytdl = YoutubeDL(ytdlopts)


class YTDLSource(disnake.PCMVolumeTransformer):
    """YouTube downloader class, for streaming to a discord voice channel."""
    def __init__(self, source, *, data, requester):
        super().__init__(source)
        self.requester = requester
        self.title = data.get("title")
        self.web_url = data.get("webpage_url")
        self.duration = data.get("duration")

    def __getitem__(self, item):
        return self.__getattribute__(item)

    @classmethod
    async def create_source(cls, ctx, search: str, *, loop, download=False):
        loop = loop or asyncio.get_event_loop()
        to_run = partial(ytdl.extract_info, url=search, download=download)
        data = await loop.run_in_executor(None, to_run)

        if "entries" in data:
            data = data["entries"][0]

        embed = disnake.Embed(title="",
                              description=f"Queued [{data['title']}]]({data['webpage_url']}) [{ctx.author.mention}]",
                              color=disnake.Color.default())

        await ctx.response.send_message(embed=embed)

        if download:
            source = ytdl.prepare_filename(data)
        else:
            return {"webpage_url": data["webpage_url"], "requester": ctx.author, "title": data["title"]}

        return cls(disnake.FFmpegPCMAudio(source, **ffmpeg_options), data=data, requester=ctx.author)

    @classmethod
    async def regather_stream(cls, data, *, loop):
        loop = loop or asyncio.get_event_loop()
        requester = data["requester"]

        to_run = partial(ytdl.extract_info, url=data["webpage_url"], download=False)
        data = await loop.run_in_executor(None, to_run)

        return cls(disnake.FFmpegPCMAudio(data["url"], **ffmpeg_options), data=data, requester=requester)


class MusicPlayer:
    """Actual music player class."""
    __slots__ = ("bot", "guild", "channel", "cog", "queue", "next", "current", "np", "volume")

    def __init__(self, ctx):
        self.bot = ctx.bot
        self.guild = ctx.guild
        self.channel = ctx.channel
        self.response = ctx.response
        self.cog = self.bot.get_cog("Music")
        self.queue = asyncio.Queue()
        self.next = asyncio.Event()
        self.np = None
        self.volume = .5
        self.current = None
        ctx.bot.loop.create_task(self.player_loop())

    async def player_loop(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next.clear()

            try:
                async with timeout(300):
                    source = await self.queue.get()
            except asyncio.TimeoutError:
                return self.destroy(self.guild)

            if not isinstance(source, YTDLSource):
                try:
                    source = await YTDLSource.regather_stream(source, loop=self.bot.loop)
                except Exception as e:
                    await self.channel.send(f"There was an error processing your song.\n```css\n[{e}]\n```")
                    continue

            source.volume = self.volume
            self.current = source
            self.guild.voice_client.play(source, after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set))

            embed = disnake.Embed(title="Now playing",
                                  description=f"[{source.title}]]({source.web_url}) [{source.requester.mention}]",
                                  color=disnake.Color.default())
            self.np = await self.response.send_message(embed=embed)

            await self.next.wait()
            source.cleanup()
            self.current = None

    def destroy(self, guild):
        return self.bot.loop.create_task(self.cog.cleanup(None, guild))


class Music(commands.Cog):
    """Music playing commands."""
    def __init__(self, bot):
        self.bot = bot
        self.players = {}
        self.channels = {}

    # Before command invoke ----------------------------------------------------

    async def cog_before_slash_command_invoke(self, ctx):
        """Reset the cooldown for some users and servers."""
        if ctx.guild.id != config.id_server_adult_children:
            return ctx.application_command.reset_cooldown(ctx)

        if ctx.author.id in config.no_cooldown_users:
            return ctx.application_command.reset_cooldown(ctx)

    # Commands -----------------------------------------------------------------

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="join", description="join a voice server")
    async def connect(self, ctx, *, channel=None):
        """Connect the bot to the voice channel the requester is in."""
        if not channel:
            try:
                channel = ctx.author.voice.channel
            except AttributeError:
                return await ctx.response.send_message("You are not connected to a voice channel.", ephemeral=True)

        vc = ctx.guild.voice_client
        if vc:
            if vc.channel.id == channel.id:
                return
            try:
                await vc.move_to(channel)
            except asyncio.TimeoutError:
                raise VoiceConnectionError(f"Moving to channel: {channel} timed out.", ephemeral=True)
        else:
            try:
                await channel.connect()
            except asyncio.TimeoutError:
                raise VoiceConnectionError(f"Connecting to channel: {channel} timed out.", ephemeral=True)

        self.channels[ctx.guild.id] = channel.id
        return await ctx.response.send_message(f"Connected to voice", ephemeral=True)

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="play", description="request a song")
    async def play(self, ctx, *, search=None):
        """Add a song to the queue."""
        vc = ctx.guild.voice_client
        if not vc:
            return await ctx.response.send_message("Invite me to a voice channel first.", ephemeral=True)

        player = self.get_player(ctx)
        source = await YTDLSource.create_source(ctx, search, loop=self.bot.loop, download=False)
        await player.queue.put(source)
        await ctx.response.send_message(f"{ctx.author.name} added to queue: {source.title}")

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="leave", description="disconnect from voice")
    async def leave(self, ctx):
        """Disconnect from the voice channel."""
        vc = ctx.guild.voice_client
        if not vc or not vc.is_connected():
            return await ctx.response.send_message("I am not connected to a voice channel.", ephemeral=True)

        await self.cleanup(ctx, ctx.guild)

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="skip", description="skip the song")
    async def skip(self, ctx):
        """Skip the current song."""
        vc = ctx.guild.voice_client
        if not vc or not vc.is_connected():
            return await ctx.response.send_message("I am not connected to a voice channel.", ephemeral=True)

        if vc.is_paused():
            pass
        elif not vc.is_playing():
            return

        vc.stop()
        await ctx.response.send_message(f"{ctx.author.name} skipped the song.")

    async def volume(self, ctx, volume=commands.Param(gt=0, lt=100)):
        """Set the volume for the player.

        Parameters
        ----------
        volume: float
            The volume level, between 0 and 100.
        """
        vc = ctx.voice_client
        if vc.source:
            vc.source.volume = volume / 100

        player = self.get_player(ctx)
        player.volume = volume / 100

        await ctx.response.send_message(f"Volume set to {volume}% by {ctx.author.name}.")

    # Listeners ----------------------------------------------------------------

    @commands.Cog.listener("on_voice_state_update")
    async def leave_when_voice_empty(self, member, before, after):
        """Leave when the voice channel is empty."""
        if member.id == self.bot.user.id: return
        if len(self.channels) == 0: return
        if member.guild.id not in self.channels.keys(): return

        channel = self.channels[member.guild.id]
        members = channel.members
        if self.bot.user in members and len(members) == 1:
            await self.cleanup(None, member.guild)

    # Functions ----------------------------------------------------------------

    async def cleanup(self, ctx, guild):
        """Disconnect and remove guild from self.players."""
        await guild.voice_client.disconnect()
        if len(self.players):
            del self.players[guild.id]
        if ctx:
            return await ctx.response.send_message("Disconnected from voice channel.", ephemeral=True)

    def get_player(self, ctx):
        """Get the guild player, or create one."""
        try:
            player = self.players[ctx.guild.id]
        except KeyError:
            player = MusicPlayer(ctx)
            self.players[ctx.guild.id] = player

        return player
