from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import discord
from discord.opus import Decoder
from discord.ext.voice_recv import AudioSink
from rich.console import Console
from vosk import KaldiRecognizer

from mituke.transcription.audio import (
    PCM_SAMPLE_WIDTH_BYTES,
    convert_pcm_48khz_stereo_to_16khz_mono,
)
from mituke.transcription.model import load_vosk_model
from mituke.transcription.state import MessageState, RecognitionState, SinkEvent
from mituke.transcription.text import join_transcript_parts, normalize_transcript

console = Console()
PENDING_AUDIO_RETENTION_SECONDS = 1.0
PENDING_AUDIO_MAX_BYTES = (
    Decoder.SAMPLING_RATE * Decoder.CHANNELS * PCM_SAMPLE_WIDTH_BYTES
)


@dataclass(frozen=True)
class RecognitionTask:
    kind: str
    user_id: int | None = None
    display_name: str = ""
    pcm: bytes = b""
    ssrc: int | None = None
    received_at: float = 0.0


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
        self.pending_audio_by_ssrc: dict[int, tuple[float, bytearray]] = {}
        self.state_lock = threading.Lock()
        self.shutdown_requested = threading.Event()
        self.processing_queue: queue.Queue[RecognitionTask] = queue.Queue()
        self.processor_thread = threading.Thread(
            target=self._recognition_worker,
            name="mituke-vosk-recognition",
            daemon=True,
        )
        self.event_queue: asyncio.Queue[SinkEvent] = asyncio.Queue()
        self.worker_task = loop.create_task(self._event_worker())
        self.processor_thread.start()

    def wants_opus(self) -> bool:
        return False

    def write(self, user: discord.User | discord.Member | None, data: Any) -> None:
        if self.shutdown_requested.is_set() or (user is not None and user.bot):
            return

        pcm = getattr(data, "pcm", None)
        if not pcm:
            return

        packet = getattr(data, "packet", None)
        self._enqueue_recognition_task(
            RecognitionTask(
                kind="audio",
                user_id=None if user is None else user.id,
                display_name="" if user is None else user.display_name,
                pcm=pcm,
                ssrc=getattr(packet, "ssrc", None),
                received_at=time.monotonic(),
            )
        )

    @AudioSink.listener()
    def on_voice_member_speaking_start(self, member: discord.Member) -> None:
        if self.shutdown_requested.is_set() or member.bot:
            return

        self._enqueue_recognition_task(
            RecognitionTask(
                kind="start",
                user_id=member.id,
                display_name=member.display_name,
            )
        )

    @AudioSink.listener()
    def on_voice_member_speaking_stop(self, member: discord.Member) -> None:
        if self.shutdown_requested.is_set() or member.bot:
            return

        self._enqueue_recognition_task(
            RecognitionTask(
                kind="stop",
                user_id=member.id,
                display_name=member.display_name,
            )
        )

    def _recognition_worker(self) -> None:
        while True:
            task = self.processing_queue.get()
            try:
                if task.kind == "shutdown":
                    self._finalize_all_sessions()
                    self._queue_event("shutdown", 0, "", "")
                    return
                if task.kind == "start":
                    self._process_start(task)
                elif task.kind == "stop":
                    self._process_stop(task)
                elif task.kind == "audio":
                    self._process_audio(task)
            except Exception as error:
                console.log(
                    f"音声認識ワーカーで予期しないエラーが発生しました: {error}"
                )
            finally:
                self.processing_queue.task_done()

    def _process_start(self, task: RecognitionTask) -> None:
        if task.user_id is None:
            return

        with self.state_lock:
            current_state = self._get_or_create_state(task.user_id, task.display_name)
            current_state.display_name = task.display_name
            if current_state.start_announced:
                return
            current_state.start_announced = True

        self._queue_event("start", task.user_id, task.display_name, "")

    def _process_stop(self, task: RecognitionTask) -> None:
        if task.user_id is None:
            return

        final_text = self._finalize_user_session(task.user_id)
        self._queue_event("finalize", task.user_id, task.display_name, final_text)

    def _process_audio(self, task: RecognitionTask) -> None:
        if task.user_id is None:
            self._remember_pending_audio(task.ssrc, task.pcm, task.received_at)
            return

        should_queue_start = False
        display_text = ""
        with self.state_lock:
            pending_audio = self._take_pending_audio(task.ssrc, task.received_at)
            current_state = self._get_or_create_state(task.user_id, task.display_name)
            current_state.display_name = task.display_name
            if not current_state.start_announced:
                current_state.start_announced = True
                should_queue_start = True

            mono_16khz_pcm, current_state.resample_state = (
                convert_pcm_48khz_stereo_to_16khz_mono(
                    pending_audio + task.pcm,
                    current_state.resample_state,
                )
            )
            if not mono_16khz_pcm:
                if should_queue_start:
                    self._queue_event("start", task.user_id, task.display_name, "")
                return

            if current_state.recognizer.AcceptWaveform(mono_16khz_pcm):
                result = json.loads(current_state.recognizer.Result())
                text = normalize_transcript(result.get("text", ""))
                if not text:
                    if should_queue_start:
                        self._queue_event("start", task.user_id, task.display_name, "")
                    return

                current_state.committed_texts.append(text)
                current_state.partial_text = ""
                display_text = join_transcript_parts(current_state.committed_texts)
            else:
                partial_result = json.loads(current_state.recognizer.PartialResult())
                partial_text = normalize_transcript(partial_result.get("partial", ""))
                if not partial_text:
                    if should_queue_start:
                        self._queue_event("start", task.user_id, task.display_name, "")
                    return

                current_state.partial_text = partial_text
                if (
                    task.received_at - current_state.last_partial_sent_at
                    >= self.partial_update_interval
                ):
                    current_state.last_partial_sent_at = task.received_at
                    display_text = join_transcript_parts(
                        [*current_state.committed_texts, current_state.partial_text]
                    )

        if should_queue_start:
            self._queue_event("start", task.user_id, task.display_name, "")

        if display_text:
            self._queue_event("update", task.user_id, task.display_name, display_text)

    async def _event_worker(self) -> None:
        while True:
            event = await self.event_queue.get()
            try:
                if event.kind == "shutdown":
                    return
                if self.shutdown_requested.is_set() and event.kind not in {
                    "finalize",
                    "shutdown",
                }:
                    continue
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
        if self.shutdown_requested.is_set() and kind not in {"finalize", "shutdown"}:
            return

        event = SinkEvent(
            kind=kind,
            user_id=user_id,
            display_name=display_name,
            text=text,
        )
        try:
            self.loop.call_soon_threadsafe(self.event_queue.put_nowait, event)
        except RuntimeError:
            console.log(
                "イベントループ停止後のため、文字起こしイベントを破棄しました。"
            )

    def _enqueue_recognition_task(self, task: RecognitionTask) -> None:
        if self.shutdown_requested.is_set() and task.kind != "shutdown":
            return

        self.processing_queue.put_nowait(task)

    def _remember_pending_audio(
        self,
        ssrc: int | None,
        pcm: bytes,
        now: float,
    ) -> None:
        if ssrc is None:
            return

        with self.state_lock:
            self._discard_stale_pending_audio(now)
            _, buffer = self.pending_audio_by_ssrc.get(ssrc, (now, bytearray()))
            buffer.extend(pcm)
            if len(buffer) > PENDING_AUDIO_MAX_BYTES:
                del buffer[:-PENDING_AUDIO_MAX_BYTES]
            self.pending_audio_by_ssrc[ssrc] = (now, buffer)

    def _take_pending_audio(self, ssrc: int | None, now: float) -> bytes:
        self._discard_stale_pending_audio(now)
        if ssrc is None:
            return b""

        pending_audio = self.pending_audio_by_ssrc.pop(ssrc, None)
        if pending_audio is None:
            return b""

        updated_at, buffer = pending_audio
        if now - updated_at > PENDING_AUDIO_RETENTION_SECONDS:
            return b""

        return bytes(buffer)

    def _discard_stale_pending_audio(self, now: float) -> None:
        stale_ssrcs = [
            ssrc
            for ssrc, (updated_at, _) in self.pending_audio_by_ssrc.items()
            if now - updated_at > PENDING_AUDIO_RETENTION_SECONDS
        ]
        for ssrc in stale_ssrcs:
            self.pending_audio_by_ssrc.pop(ssrc, None)

    def request_stop(self) -> None:
        self._begin_shutdown()

    async def wait_for_idle(self) -> None:
        await asyncio.to_thread(self.processing_queue.join)
        await self.event_queue.join()

    async def wait_closed(self) -> None:
        await asyncio.to_thread(self.processing_queue.join)
        await asyncio.to_thread(self.processor_thread.join)
        await asyncio.shield(self.worker_task)

    def cleanup(self) -> None:
        self._begin_shutdown()

    def _begin_shutdown(self) -> None:
        if self.shutdown_requested.is_set():
            return

        self.shutdown_requested.set()
        self._enqueue_recognition_task(RecognitionTask(kind="shutdown"))

    def _finalize_all_sessions(self) -> None:
        with self.state_lock:
            pending_speakers = [
                (user_id, current_state.display_name)
                for user_id, current_state in self.recognition_states.items()
            ]
            self.pending_audio_by_ssrc.clear()

        for user_id, display_name in pending_speakers:
            final_text = self._finalize_user_session(user_id)
            self._queue_event("finalize", user_id, display_name, final_text)
