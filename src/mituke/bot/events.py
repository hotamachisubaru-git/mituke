from __future__ import annotations

import discord
from discord.ext import commands
from discord.ext.voice_recv import VoiceRecvClient
from rich.console import Console

from mituke.bot.voice import stop_receiving


async def handle_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
    console: Console,
) -> None:
    voice_client = member.guild.voice_client
    if not isinstance(voice_client, VoiceRecvClient):
        return

    connected_channel = voice_client.channel
    if connected_channel is None:
        return

    if before.channel != connected_channel and after.channel != connected_channel:
        return

    non_bot_members = [
        current_member
        for current_member in connected_channel.members
        if not current_member.bot
    ]
    if non_bot_members:
        return

    await stop_receiving(voice_client)

    await voice_client.disconnect(force=True)
    console.log(f"VC {connected_channel.name} が空になったため退出しました。")


async def handle_ready(bot: commands.Bot, console: Console) -> None:
    if bot.user is None:
        return

    console.log(f"{bot.user} としてログインしました。")


async def handle_command_error(
    ctx: commands.Context,
    error: commands.CommandError,
    console: Console,
) -> None:
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("不明なコマンドです。`!help` で使い方を確認できます。")
        return

    console.log(f"コマンド実行中にエラーが発生しました: {error}")
    await ctx.send("コマンドの実行中にエラーが発生しました。ログを確認してください。")
