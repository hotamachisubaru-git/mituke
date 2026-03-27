from __future__ import annotations

import asyncio
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mituke.transcription.sink import VoskSink
from mituke.transcription.state import MessageState


class FakeRecognizer:
    def __init__(self, _model: object, _sample_rate: int) -> None:
        self.accept_waveform = False
        self.result_text = ""
        self.partial_text = "あとから"
        self.final_text = ""
        self.accept_calls: list[bytes] = []

    def AcceptWaveform(self, pcm: bytes) -> bool:
        self.accept_calls.append(pcm)
        return self.accept_waveform

    def Result(self) -> str:
        return json.dumps({"text": self.result_text})

    def PartialResult(self) -> str:
        return json.dumps({"partial": self.partial_text})

    def FinalResult(self) -> str:
        return json.dumps({"text": self.final_text})


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


class VoskSinkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.text_channel = FakeTextChannel()
        self.loop = asyncio.get_running_loop()

        self.model_patcher = patch(
            "mituke.transcription.sink.load_vosk_model",
            return_value=object(),
        )
        self.recognizer_patcher = patch(
            "mituke.transcription.sink.KaldiRecognizer",
            FakeRecognizer,
        )
        self.audio_patcher = patch(
            "mituke.transcription.sink.convert_pcm_48khz_stereo_to_16khz_mono",
            side_effect=lambda pcm: pcm,
        )

        self.model_patcher.start()
        self.recognizer_patcher.start()
        self.audio_patcher.start()

    async def asyncTearDown(self) -> None:
        self.audio_patcher.stop()
        self.recognizer_patcher.stop()
        self.model_patcher.stop()

    async def test_request_stop_finalizes_pending_message(self) -> None:
        sink = VoskSink(
            text_channel=self.text_channel,
            model_path=Path("."),
            loop=self.loop,
        )
        message = FakeMessage("Alice: 話し始めました。文字起こしを始めます…")
        sink.message_states[1] = MessageState(
            message=message,
            last_content=message.content,
        )
        with sink.state_lock:
            state = sink._get_or_create_state(1, "Alice")
            state.committed_texts.append("こんにちは")

        sink.request_stop()
        await sink.wait_closed()

        self.assertEqual(message.edits, ["Alice: こんにちは"])
        self.assertNotIn(1, sink.message_states)
        self.assertTrue(sink.worker_task.done())

    async def test_cleanup_ignores_late_audio_after_shutdown(self) -> None:
        sink = VoskSink(
            text_channel=self.text_channel,
            model_path=Path("."),
            loop=self.loop,
        )

        sink.cleanup()
        await sink.wait_closed()

        user = SimpleNamespace(id=1, display_name="Alice", bot=False)
        sink.write(user, SimpleNamespace(pcm=b"pcm"))
        sink.on_voice_member_speaking_start(user)
        await asyncio.sleep(0)

        self.assertEqual(sink.recognition_states, {})
        self.assertEqual(self.text_channel.messages, [])

    async def test_buffers_audio_until_user_mapping_is_available(self) -> None:
        sink = VoskSink(
            text_channel=self.text_channel,
            model_path=Path("."),
            loop=self.loop,
        )

        sink.write(None, SimpleNamespace(pcm=b"lead", packet=SimpleNamespace(ssrc=42)))

        user = SimpleNamespace(id=1, display_name="Alice", bot=False)
        sink.write(user, SimpleNamespace(pcm=b"tail", packet=SimpleNamespace(ssrc=42)))

        await asyncio.sleep(0)
        await asyncio.wait_for(sink.event_queue.join(), 1)

        state = sink.recognition_states[1]
        recognizer = state.recognizer

        self.assertEqual(recognizer.accept_calls, [b"leadtail"])
        self.assertEqual(len(self.text_channel.messages), 1)
        self.assertEqual(self.text_channel.messages[0].content, "Alice: あとから")
        self.assertEqual(
            self.text_channel.messages[0].edits,
            ["Alice: あとから"],
        )

        sink.request_stop()
        await sink.wait_closed()

    async def test_start_event_and_audio_fallback_do_not_duplicate_message(self) -> None:
        sink = VoskSink(
            text_channel=self.text_channel,
            model_path=Path("."),
            loop=self.loop,
        )

        user = SimpleNamespace(id=1, display_name="Alice", bot=False)
        sink.on_voice_member_speaking_start(user)
        sink.write(user, SimpleNamespace(pcm=b"voice", packet=SimpleNamespace(ssrc=42)))

        await asyncio.sleep(0)
        await asyncio.wait_for(sink.event_queue.join(), 1)

        self.assertEqual(len(self.text_channel.messages), 1)
        self.assertEqual(self.text_channel.messages[0].content, "Alice: あとから")
        self.assertEqual(
            self.text_channel.messages[0].edits,
            ["Alice: あとから"],
        )

        sink.request_stop()
        await sink.wait_closed()
