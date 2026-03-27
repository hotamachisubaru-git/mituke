from __future__ import annotations

import logging

from rich.console import Console

from mituke.bot.factory import create_bot
from mituke.config import configure_opus, load_settings
from mituke.patches.voice_recv import install_packet_decoder_guard

logging.getLogger("discord.ext.voice_recv").setLevel(logging.WARNING)

console = Console()


def run() -> None:
    settings = load_settings()
    configure_opus(settings, console)
    install_packet_decoder_guard(console)
    bot = create_bot(settings, console)
    bot.run(settings.discord_token)
