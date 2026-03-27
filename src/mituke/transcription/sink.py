from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any

import discord
from discord.ext.voice_recv import AudioSink
from rich.console import Console
from vosk import KaldiRecognizer

from mituke.transcription.audio import convert_pcm_48khz_stereo_to_16khz_mono
from mituke.transcription.model import load_vosk_model
from mituke.transcription.state import MessageState, RecognitionState, SinkEvent
from mituke.transcription.text import join_transcript_parts, normalize_transcript

console = Console()


class VoskSink(AudioSink):
    def __init__(
        self,
        text_channel: discord.abc.Messageable,
        model_path: Path,
        loop: asyncio.AbstractEventLoop,
        partial_update_interval: float = 1.0,
    ) -> None:
        super().__init__()
        self.text_channel = text_channel
        self.loop = loop
        self.partial_update_interval = partial_update_interval
        self.model = load_vosk_model(str(model_path.resolve()))
        self.recognition_states: dict[int, RecognitionState] = {}
        self.message_states: dict[int, MessageState] = {}
        self.state_lock = threading.Lock()
        self.event_queue: asyncio.Queue[SinkEvent] = asyncio.Queue()
        self.worker_task = loop.create_task(self._event_worker())

    def wants_opus(self) -> bool:
        return False

    def write(self, user: discord.User | discord.Member | None, data: Any) -> None:
        if user is None or user.bot:
            return

        pcm = getattr(data, "pcm", None)
        if not pcm:
            return

        mono_16khz_pcm = convert_pcm_48khz_stereo_to_16khz_mono(pcm)
        if not mono_16khz_pcm:
            return

        should_send_partial = False
        display_text = ""
        now = time.monotonic()
        with self.state_lock:
            current_state = self._get_or_create_state(user.id, user.display_name)
            current_state.display_name = user.display_name

            if current_state.recognizer.AcceptWaveform(mono_16khz_pcm):
                result = json.loads(current_state.recognizer.Result())
                text = normalize_transcript(result.get("text", ""))
                if not text:
                    return

                current_state.committed_texts.append(text)
                current_state.partial_text = ""
                display_text = join_transcript_parts(current_state.committed_texts)
            else:
                partial_result = json.loads(current_state.recognizer.PartialResult())
                partial_text = normalize_transcript(partial_result.get("partial", ""))
                if not partial_text:
                    return

                current_state.partial_text = partial_text
                if (
                    now - current_state.last_partial_sent_at
                    >= self.partial_update_interval
                ):
                    current_state.last_partial_sent_at = now
                    display_text = join_transcript_parts(
                        [*current_state.committed_texts, current_state.partial_text]
                    )
                    should_send_partial = bool(display_text)

                if not should_send_partial:
                    return

        if display_text and not should_send_partial:
            self._queue_event("update", user.id, user.display_name, display_text)
            return

        if should_send_partial:
            self._queue_event("update", user.id, user.display_name, display_text)

    @AudioSink.listener()
    def on_voice_member_speaking_start(self, member: discord.Member) -> None:
        if member.bot:
            return

        self._queue_event("start", member.id, member.display_name, "")

    @AudioSink.listener()
    def on_voice_member_speaking_stop(self, member: discord.Member) -> None:
        if member.bot:
            return

        final_text = self._finalize_user_session(member.id)
        self._queue_event("finalize", member.id, member.display_name, final_text)

    async def _event_worker(self) -> None:
        while True:
            event = await self.event_queue.get()
            try:
                if event.kind == "shutdown":
                    return
                if event.kind == "start":
                    await self._handle_start(event)
                elif event.kind == "update":
                    await self._handle_update(event)
                elif event.kind == "finalize":
                    await self._handle_finalize(event)
            except discord.HTTPException as error:
                console.log(f"Discord への送信に失敗しました: {error}")
            except Exception as error:
                console.log(f"文字起こし処理で予期しないエラーが発生しました: {error}")
            finally:
                self.event_queue.task_done()

    async def _handle_start(self, event: SinkEvent) -> None:
        message_state = self.message_states.get(event.user_id)
        if message_state and message_state.message is not None:
            return

        content = f"{event.display_name}: 話し始めました。文字起こしを始めます…"
        message = await self.text_channel.send(content)
        self.message_states[event.user_id] = MessageState(
            message=message,
            last_content=content,
        )

    async def _handle_update(self, event: SinkEvent) -> None:
        if not event.text:
            return

        content = f"{event.display_name}: {event.text}"
        message_state = self.message_states.get(event.user_id)

        if message_state is None or message_state.message is None:
            message = await self.text_channel.send(content)
            self.message_states[event.user_id] = MessageState(
                message=message,
                last_content=content,
            )
            return

        if message_state.last_content == content:
            return

        await message_state.message.edit(content=content)
        message_state.last_content = content

    async def _handle_finalize(self, event: SinkEvent) -> None:
        message_state = self.message_states.pop(event.user_id, None)

        if not event.text:
            if message_state and message_state.message is not None:
                await message_state.message.delete()
            return

        content = f"{event.display_name}: {event.text}"
        if message_state is None or message_state.message is None:
            await self.text_channel.send(content)
            return

        if message_state.last_content != content:
            await message_state.message.edit(content=content)

    def _get_or_create_state(self, user_id: int, display_name: str) -> RecognitionState:
        current_state = self.recognition_states.get(user_id)
        if current_state is None:
            current_state = RecognitionState(
                recognizer=KaldiRecognizer(self.model, 16000),
                display_name=display_name,
            )
            self.recognition_states[user_id] = current_state

        return current_state

    def _finalize_user_session(self, user_id: int) -> str:
        with self.state_lock:
            current_state = self.recognition_states.pop(user_id, None)

        if current_state is None:
            return ""

        final_result = json.loads(current_state.recognizer.FinalResult())
        final_text = normalize_transcript(final_result.get("text", ""))
        if final_text:
            current_state.committed_texts.append(final_text)

        return join_transcript_parts(current_state.committed_texts)

    def _queue_event(
        self,
        kind: str,
        user_id: int,
        display_name: str,
        text: str,
    ) -> None:
        event = SinkEvent(
            kind=kind,
            user_id=user_id,
            display_name=display_name,
            text=text,
        )
        self.loop.call_soon_threadsafe(self.event_queue.put_nowait, event)

    def cleanup(self) -> None:
        pending_events: list[SinkEvent] = []
        with self.state_lock:
            pending_speakers = [
                (user_id, current_state.display_name)
                for user_id, current_state in self.recognition_states.items()
            ]

        for user_id, display_name in pending_speakers:
            final_text = self._finalize_user_session(user_id)
            pending_events.append(
                SinkEvent(
                    kind="finalize",
                    user_id=user_id,
                    display_name=display_name,
                    text=final_text,
                )
            )

        def enqueue_cleanup() -> None:
            for event in pending_events:
                self.event_queue.put_nowait(event)
            self.event_queue.put_nowait(SinkEvent("shutdown", 0, "", ""))

        self.loop.call_soon_threadsafe(enqueue_cleanup)
