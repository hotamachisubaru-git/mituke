from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from discord.ext import commands

from mituke.bot.events import (
    handle_command_error,
    handle_ready,
    handle_voice_state_update,
)


class FakeVoiceRecvClient:
    def __init__(
        self,
        *,
        channel: object | None = None,
        listening: bool = False,
        sink: object | None = None,
    ) -> None:
        self.channel = channel
        self._listening = listening
        self.sink = sink
        self.stop_called = False
        self.disconnect_calls: list[bool] = []

    def is_listening(self) -> bool:
        return self._listening

    def stop_listening(self) -> None:
        self.stop_called = True
        self._listening = False

    async def disconnect(self, *, force: bool) -> None:
        self.disconnect_calls.append(force)


class FakeManagedSink:
    def __init__(self) -> None:
        self.request_stop_called = False
        self.wait_closed_called = False

    def request_stop(self) -> None:
        self.request_stop_called = True

    async def wait_closed(self) -> None:
        self.wait_closed_called = True


class FakeContext:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []

    async def send(self, content: str) -> None:
        self.sent_messages.append(content)


class VoiceStateUpdateTests(unittest.IsolatedAsyncioTestCase):
    async def test_disconnects_when_only_bots_remain(self) -> None:
        connected_channel = SimpleNamespace(
            name="General",
            members=[SimpleNamespace(bot=True)],
        )
        managed_sink = FakeManagedSink()
        voice_client = FakeVoiceRecvClient(
            channel=connected_channel,
            listening=True,
            sink=managed_sink,
        )
        member = SimpleNamespace(guild=SimpleNamespace(voice_client=voice_client))
        before = SimpleNamespace(channel=connected_channel)
        after = SimpleNamespace(channel=None)
        console = Mock()

        with patch("mituke.bot.events.VoiceRecvClient", FakeVoiceRecvClient):
            await handle_voice_state_update(member, before, after, console)

        self.assertTrue(voice_client.stop_called)
        self.assertTrue(managed_sink.request_stop_called)
        self.assertTrue(managed_sink.wait_closed_called)
        self.assertEqual(voice_client.disconnect_calls, [True])
        console.log.assert_called_once_with("VC General が空になったため退出しました。")

    async def test_keeps_connection_when_non_bot_member_remains(self) -> None:
        connected_channel = SimpleNamespace(
            name="General",
            members=[SimpleNamespace(bot=False), SimpleNamespace(bot=True)],
        )
        voice_client = FakeVoiceRecvClient(channel=connected_channel, listening=True)
        member = SimpleNamespace(guild=SimpleNamespace(voice_client=voice_client))
        before = SimpleNamespace(channel=connected_channel)
        after = SimpleNamespace(channel=None)
        console = Mock()

        with patch("mituke.bot.events.VoiceRecvClient", FakeVoiceRecvClient):
            await handle_voice_state_update(member, before, after, console)

        self.assertFalse(voice_client.stop_called)
        self.assertEqual(voice_client.disconnect_calls, [])
        console.log.assert_not_called()


class ReadyTests(unittest.IsolatedAsyncioTestCase):
    async def test_logs_logged_in_user(self) -> None:
        console = Mock()
        bot = SimpleNamespace(user="mituke#0001")

        await handle_ready(bot, console)

        console.log.assert_called_once_with("mituke#0001 としてログインしました。")


class CommandErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_handles_unknown_command(self) -> None:
        ctx = FakeContext()
        console = Mock()

        await handle_command_error(ctx, commands.CommandNotFound("nope"), console)

        self.assertEqual(
            ctx.sent_messages,
            ["不明なコマンドです。`!help` で使い方を確認できます。"],
        )
        console.log.assert_not_called()

    async def test_logs_and_reports_unexpected_command_errors(self) -> None:
        ctx = FakeContext()
        console = Mock()
        error = commands.CommandError("boom")

        await handle_command_error(ctx, error, console)

        console.log.assert_called_once_with(
            "コマンド実行中にエラーが発生しました: boom"
        )
        self.assertEqual(
            ctx.sent_messages,
            ["コマンドの実行中にエラーが発生しました。ログを確認してください。"],
        )
