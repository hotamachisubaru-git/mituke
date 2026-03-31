from __future__ import annotations

import discord

from mituke.transcription.state import MessageState, SinkEvent


def build_start_message(display_name: str) -> str:
    return f"{display_name}: 話し始めました。文字起こしを始めます…"


def build_transcript_message(display_name: str, text: str) -> str:
    return f"{display_name}: {text}"


class TranscriptMessagePublisher:
    def __init__(self, text_channel: discord.abc.Messageable) -> None:
        self.text_channel = text_channel
        self.message_states: dict[int, MessageState] = {}

    async def handle_start(self, event: SinkEvent) -> None:
        message_state = self.message_states.get(event.user_id)
        if message_state and message_state.message is not None:
            return

        content = build_start_message(event.display_name)
        message = await self.text_channel.send(content)
        self.message_states[event.user_id] = MessageState(
            message=message,
            last_content=content,
        )

    async def handle_update(self, event: SinkEvent) -> None:
        if not event.text:
            return

        content = build_transcript_message(event.display_name, event.text)
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

    async def handle_finalize(self, event: SinkEvent) -> None:
        message_state = self.message_states.pop(event.user_id, None)

        if not event.text:
            if message_state and message_state.message is not None:
                await message_state.message.delete()
            return

        content = build_transcript_message(event.display_name, event.text)
        if message_state is None or message_state.message is None:
            await self.text_channel.send(content)
            return

        if message_state.last_content != content:
            await message_state.message.edit(content=content)
