from __future__ import annotations

import asyncio

import discord
from discord.ext import commands
from discord.ext.voice_recv import VoiceRecvClient

from mituke.config import Settings
from mituke.transcription.sink import VoskSink


async def start_listening(
    ctx: commands.Context,
    settings: Settings,
    handle_listen_error,
) -> None:
    if ctx.guild is None or not isinstance(ctx.author, discord.Member):
        await ctx.send("このコマンドはサーバー内のテキストチャンネルで使ってください。")
        return

    voice_state = ctx.author.voice
    if voice_state is None or voice_state.channel is None:
        await ctx.send("先に参加したいボイスチャンネルへ入ってください。")
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

    if voice_client.is_listening():
        voice_client.stop_listening()

    sink = VoskSink(
        text_channel=ctx.channel,
        model_path=settings.vosk_model_path,
        loop=asyncio.get_running_loop(),
    )
    voice_client.listen(sink, after=handle_listen_error)

    await ctx.send(
        f"VC `{target_channel.name}` へ参加しました。"
        f" これからこのチャンネルで文字起こしを送ります。"
    )


async def stop_listening(ctx: commands.Context) -> None:
    if ctx.guild is None:
        await ctx.send("このコマンドはサーバー内で使ってください。")
        return

    voice_client = ctx.guild.voice_client
    if voice_client is None:
        await ctx.send("今はどのボイスチャンネルにも参加していません。")
        return

    if isinstance(voice_client, VoiceRecvClient) and voice_client.is_listening():
        voice_client.stop_listening()

    await voice_client.disconnect(force=True)
    await ctx.send("ボイスチャンネルから退出しました。")


async def show_help(ctx: commands.Context) -> None:
    await ctx.send(
        "使い方:\n"
        "`!join` で、あなたが入っている VC に Bot が参加します。\n"
        "`!leave` で、文字起こしを止めて VC から退出します。\n"
        "`!help` で、この案内をもう一度表示できます。"
    )
