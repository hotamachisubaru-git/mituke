from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mituke.app import run


class RunTests(unittest.TestCase):
    def test_run_loads_settings_configures_opus_and_starts_bot(self) -> None:
        settings = SimpleNamespace(discord_token="test-token")
        bot = Mock()

        with (
            patch("mituke.app.load_settings", return_value=settings) as load_settings,
            patch("mituke.app.configure_opus") as configure_opus,
            patch("mituke.app.install_packet_decoder_guard") as install_packet_decoder_guard,
            patch("mituke.app.create_bot", return_value=bot) as create_bot,
        ):
            run()

        load_settings.assert_called_once_with()
        configure_opus.assert_called_once()
        install_packet_decoder_guard.assert_called_once()
        create_bot.assert_called_once()
        bot.run.assert_called_once_with("test-token")
