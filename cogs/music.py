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
    "format": "bestaudio/best",
    "outtmpl": "downloads/%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",  # ipv6 addresses cause issues sometimes
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
    async def create_source(cls, inter, search: str, *, loop, download=False):
        loop = loop or asyncio.get_event_loop()
        to_run = partial(ytdl.extract_info, url=search, download=download)
        data = await loop.run_in_executor(None, to_run)

        if "entries" in data:
            data = data["entries"][0]

        embed = disnake.Embed(
            title="",
            description=f"Queued [{data['title']}]]({data['webpage_url']}) [{inter.author.mention}]",
            color=disnake.Color.default(),
        )

        await inter.response.send_message(embed=embed)

        if download:
            source = ytdl.prepare_filename(data)
        else:
            return {
                "webpage_url": data["webpage_url"],
                "requester": inter.author,
                "title": data["title"],
            }

        return cls(
            disnake.FFmpegPCMAudio(source, **ffmpeg_options),
            data=data,
            requester=inter.author,
        )

    @classmethod
    async def regather_stream(cls, data, *, loop):
        loop = loop or asyncio.get_event_loop()
        requester = data["requester"]

        to_run = partial(ytdl.extract_info, url=data["webpage_url"], download=False)
        data = await loop.run_in_executor(None, to_run)

        return cls(
            disnake.FFmpegPCMAudio(data["url"], **ffmpeg_options),
            data=data,
            requester=requester,
        )


class MusicPlayer:
    """Actual music player class."""

    __slots__ = (
        "bot",
        "guild",
        "channel",
        "cog",
        "queue",
        "next",
        "current",
        "np",
        "volume",
    )

    def __init__(self, inter):
        self.bot = inter.bot
        self.guild = inter.guild
        self.channel = inter.channel
        # self.response = inter.response
        self.cog = self.bot.get_cog("Music")
        self.queue = asyncio.Queue()
        self.next = asyncio.Event()
        self.np = None
        self.volume = 0.5
        self.current = None
        inter.bot.loop.create_task(self.player_loop())

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
            self.guild.voice_client.play(
                source,
                after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set),
            )

            embed = disnake.Embed(
                title="Now playing",
                description=f"[{source.title}]]({source.web_url}) [{source.requester.mention}]",
                color=disnake.Color.default(),
            )

            # self.np = await self.response.send_message(embed=embed)

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

    async def cog_before_slash_command_invoke(self, inter):
        """Reset the cooldown for some users and servers."""
        if inter.guild.id != config.ID_SERVER_ADULT_CHILDREN:
            return inter.application_command.reset_cooldown(inter)

        if inter.author.id in config.NO_COOLDOWN_USERS:
            return inter.application_command.reset_cooldown(inter)

    # Commands -----------------------------------------------------------------

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="join", description="join a voice server")
    async def connect(self, inter, *, channel=None):
        """Connect the bot to the voice channel the requester is in."""
        if not channel:
            try:
                channel = inter.author.voice.channel
            except AttributeError:
                return await inter.response.send_message("You are not connected to a voice channel.", ephemeral=True)

        vc = inter.guild.voice_client
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

        self.channels[inter.guild.id] = channel.id
        return await inter.response.send_message(f"Connected to voice", ephemeral=True)

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="play", description="request a song")
    async def play(self, inter, *, search=None):
        """Add a song to the queue."""
        await inter.response.defer(ephemeral=True)
        vc = inter.guild.voice_client
        if not vc:
            return await inter.edit_original_message("Invite me to a voice channel first.", ephemeral=True)

        player = self.get_player(inter)
        source = await YTDLSource.create_source(inter, search, loop=self.bot.loop, download=False)
        await player.queue.put(source)
        # await inter.edit_original_message(f"{inter.author.name} added to queue: {source.title}")

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="leave", description="disconnect from voice")
    async def leave(self, inter):
        """Disconnect from the voice channel."""
        vc = inter.guild.voice_client
        if not vc or not vc.is_connected():
            return await inter.response.send_message("I am not connected to a voice channel.", ephemeral=True)

        await self.cleanup(inter, inter.guild)

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="skip", description="skip the song")
    async def skip(self, inter):
        """Skip the current song."""
        vc = inter.guild.voice_client
        if not vc or not vc.is_connected():
            return await inter.response.send_message("I am not connected to a voice channel.", ephemeral=True)

        if vc.is_paused():
            pass
        elif not vc.is_playing():
            return

        vc.stop()
        await inter.response.send_message(f"{inter.author.name} skipped the song.")

    async def volume(self, inter, volume=commands.Param(gt=0, lt=100)):
        """Set the volume for the player.

        Parameters
        ----------
        volume: float
            The volume level, between 0 and 100.
        """
        vc = inter.voice_client
        if vc.source:
            vc.source.volume = volume / 100

        player = self.get_player(inter)
        player.volume = volume / 100

        await inter.response.send_message(f"Volume set to {volume}% by {inter.author.name}.")

    # Listeners ----------------------------------------------------------------

    @commands.Cog.listener("on_voice_state_update")
    async def leave_when_voice_empty(self, member, before, after):
        """Leave when the voice channel is empty."""
        if member.id == self.bot.user.id:
            return
        if len(self.channels) == 0:
            return
        if member.guild.id not in self.channels.keys():
            return

        channel = self.channels[member.guild.id]

        try:
            members = channel.members
            if self.bot.user in members and len(members) == 1:
                await self.cleanup(None, member.guild)
        except Exception as e:
            # print(e)
            # print(channel)
            _ = e

    # Functions ----------------------------------------------------------------

    async def cleanup(self, inter, guild):
        """Disconnect and remove guild from self.players."""
        await guild.voice_client.disconnect()
        if len(self.players):
            del self.players[guild.id]
        if inter:
            return await inter.response.send_message("Disconnected from voice channel.", ephemeral=True)

    def get_player(self, inter):
        """Get the guild player, or create one."""
        try:
            player = self.players[inter.guild.id]
        except KeyError:
            player = MusicPlayer(inter)
            self.players[inter.guild.id] = player

        return player
