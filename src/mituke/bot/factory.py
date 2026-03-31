from __future__ import annotations

import discord
from discord.ext import commands
from rich.console import Console

from mituke.bot import messages
from mituke.bot.commands import show_help, start_listening, stop_listening
from mituke.bot.events import (
    handle_command_error,
    handle_ready,
    handle_voice_state_update,
)
from mituke.config import Settings


def create_bot(settings: Settings, console: Console) -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.voice_states = True

    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

    def handle_listen_error(error: Exception | None) -> None:
        if error is not None:
            console.log(messages.listen_error(error))

    @bot.command(name="join", aliases=["listen"])
    async def join_command(ctx: commands.Context) -> None:
        await start_listening(ctx, settings, handle_listen_error)

    @bot.command(name="leave", aliases=["stop"])
    async def leave_command(ctx: commands.Context) -> None:
        await stop_listening(ctx)

    @bot.command(name="help")
    async def help_command(ctx: commands.Context) -> None:
        await show_help(ctx)

    @bot.event
    async def on_voice_state_update(
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        await handle_voice_state_update(member, before, after, console)

    @bot.event
    async def on_ready() -> None:
        await handle_ready(bot, console)

    @bot.event
    async def on_command_error(
        ctx: commands.Context,
        error: commands.CommandError,
    ) -> None:
        await handle_command_error(ctx, error, console)

    return bot
