from __future__ import annotations

import asyncio

import discord
from discord.ext import commands
from discord.ext.voice_recv import VoiceRecvClient

from mituke.bot import messages
from mituke.bot.voice import stop_receiving
from mituke.config import Settings
from mituke.transcription.sink import VoskSink


async def start_listening(
    ctx: commands.Context,
    settings: Settings,
    handle_listen_error,
) -> None:
    if ctx.guild is None or not isinstance(ctx.author, discord.Member):
        await ctx.send(messages.SERVER_TEXT_CHANNEL_REQUIRED)
        return

    voice_state = ctx.author.voice
    if voice_state is None or voice_state.channel is None:
        await ctx.send(messages.VOICE_CHANNEL_REQUIRED)
        return

    target_channel = voice_state.channel
    voice_client = ctx.guild.voice_client

    if voice_client is not None and not isinstance(voice_client, VoiceRecvClient):
        await voice_client.disconnect(force=True)
        voice_client = None

    if voice_client is None:
        voice_client = await target_channel.connect(cls=VoiceRecvClient)
    elif voice_client.channel != target_channel:
        await voice_client.move_to(target_channel)

    assert isinstance(voice_client, VoiceRecvClient)

    await stop_receiving(voice_client)

    sink = VoskSink(
        text_channel=ctx.channel,
        model_path=settings.vosk_model_path,
        loop=asyncio.get_running_loop(),
    )
    voice_client.listen(sink, after=handle_listen_error)

    await ctx.send(messages.joined_voice_channel(target_channel.name))


async def stop_listening(ctx: commands.Context) -> None:
    if ctx.guild is None:
        await ctx.send(messages.SERVER_CONTEXT_REQUIRED)
        return

    voice_client = ctx.guild.voice_client
    if voice_client is None:
        await ctx.send(messages.VOICE_CLIENT_MISSING)
        return

    if isinstance(voice_client, VoiceRecvClient):
        await stop_receiving(voice_client)

    await voice_client.disconnect(force=True)
    await ctx.send(messages.VOICE_CHANNEL_LEFT)


async def show_help(ctx: commands.Context) -> None:
    await ctx.send(messages.HELP_TEXT)
