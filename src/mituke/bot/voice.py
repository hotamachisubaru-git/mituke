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


async def stop_receiving(voice_client: VoiceRecvClient) -> None:
    sink = voice_client.sink if voice_client.is_listening() else None

    if _supports_graceful_shutdown(sink):
        sink.request_stop()

    if voice_client.is_listening():
        voice_client.stop_listening()

    if _supports_graceful_shutdown(sink):
        await sink.wait_closed()
