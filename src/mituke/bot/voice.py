from __future__ import annotations

from typing import Protocol, TypeGuard

from discord.ext.voice_recv import VoiceRecvClient


class GracefulSink(Protocol):
    def request_stop(self) -> None: ...

    async def wait_closed(self) -> None: ...


def _supports_graceful_shutdown(sink: object | None) -> TypeGuard[GracefulSink]:
    return (
        sink is not None
        and hasattr(sink, "request_stop")
        and hasattr(sink, "wait_closed")
    )


def reset_voice_receive_state(voice_client: VoiceRecvClient) -> None:
    ssrc_to_id = getattr(voice_client, "_ssrc_to_id", None)
    if hasattr(ssrc_to_id, "clear"):
        ssrc_to_id.clear()

    id_to_ssrc = getattr(voice_client, "_id_to_ssrc", None)
    if hasattr(id_to_ssrc, "clear"):
        id_to_ssrc.clear()


async def stop_receiving(voice_client: VoiceRecvClient) -> None:
    sink = voice_client.sink if voice_client.is_listening() else None

    if _supports_graceful_shutdown(sink):
        sink.request_stop()

    if voice_client.is_listening():
        voice_client.stop_listening()

    if _supports_graceful_shutdown(sink):
        await sink.wait_closed()

    reset_voice_receive_state(voice_client)
