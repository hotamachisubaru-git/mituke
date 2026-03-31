from __future__ import annotations

import unittest

from mituke.transcription.messages import (
    TranscriptMessagePublisher,
    build_start_message,
    build_transcript_message,
)
from mituke.transcription.state import SinkEvent


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content
        self.edits: list[str] = []
        self.deleted = False

    async def edit(self, *, content: str) -> None:
        self.content = content
        self.edits.append(content)

    async def delete(self) -> None:
        self.deleted = True


class FakeTextChannel:
    def __init__(self) -> None:
        self.messages: list[FakeMessage] = []

    async def send(self, content: str) -> FakeMessage:
        message = FakeMessage(content)
        self.messages.append(message)
        return message


class TranscriptMessagePublisherTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_then_update_reuses_same_message(self) -> None:
        publisher = TranscriptMessagePublisher(FakeTextChannel())
        start_event = SinkEvent(kind="start", user_id=1, display_name="Alice")
        update_event = SinkEvent(
            kind="update",
            user_id=1,
            display_name="Alice",
            text="こんにちは",
        )

        await publisher.handle_start(start_event)
        await publisher.handle_update(update_event)

        self.assertEqual(len(publisher.text_channel.messages), 1)
        self.assertEqual(
            publisher.text_channel.messages[0].edits,
            [build_transcript_message("Alice", "こんにちは")],
        )

    async def test_finalize_without_text_deletes_pending_message(self) -> None:
        publisher = TranscriptMessagePublisher(FakeTextChannel())
        await publisher.handle_start(SinkEvent(kind="start", user_id=1, display_name="Alice"))

        message = publisher.text_channel.messages[0]

        await publisher.handle_finalize(
            SinkEvent(kind="finalize", user_id=1, display_name="Alice", text="")
        )

        self.assertTrue(message.deleted)


class TranscriptMessageFormattingTests(unittest.TestCase):
    def test_builds_start_message(self) -> None:
        self.assertEqual(
            build_start_message("Alice"),
            "Alice: 話し始めました。文字起こしを始めます…",
        )

    def test_builds_transcript_message(self) -> None:
        self.assertEqual(
            build_transcript_message("Alice", "こんにちは"),
            "Alice: こんにちは",
        )
