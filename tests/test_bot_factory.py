from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock

from mituke.bot.factory import create_bot
from mituke.config import Settings


class CreateBotTests(unittest.TestCase):
    def test_registers_expected_commands_and_intents(self) -> None:
        bot = create_bot(Settings("token", Path("model"), None), Mock())

        self.assertIsNone(bot.help_command)
        self.assertTrue(bot.intents.message_content)
        self.assertTrue(bot.intents.members)
        self.assertTrue(bot.intents.voice_states)
        self.assertIn("join", bot.all_commands)
        self.assertIn("listen", bot.all_commands)
        self.assertIn("leave", bot.all_commands)
        self.assertIn("stop", bot.all_commands)
        self.assertIn("help", bot.all_commands)
