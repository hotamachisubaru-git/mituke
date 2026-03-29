from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PendingAudioBuffer:
    retention_seconds: float
    max_bytes: int
    audio_by_ssrc: dict[int, tuple[float, bytearray]] = field(default_factory=dict)

    def remember(self, ssrc: int | None, pcm: bytes, now: float) -> None:
        if ssrc is None or not pcm:
            return

        self.discard_stale(now)
        _, buffer = self.audio_by_ssrc.get(ssrc, (now, bytearray()))
        buffer.extend(pcm)
        if len(buffer) > self.max_bytes:
            del buffer[:-self.max_bytes]
        self.audio_by_ssrc[ssrc] = (now, buffer)

    def take(self, ssrc: int | None, now: float) -> bytes:
        self.discard_stale(now)
        if ssrc is None:
            return b""

        pending_audio = self.audio_by_ssrc.pop(ssrc, None)
        if pending_audio is None:
            return b""

        updated_at, buffer = pending_audio
        if now - updated_at > self.retention_seconds:
            return b""

        return bytes(buffer)

    def discard_stale(self, now: float) -> None:
        stale_ssrcs = [
            ssrc
            for ssrc, (updated_at, _) in self.audio_by_ssrc.items()
            if now - updated_at > self.retention_seconds
        ]
        for ssrc in stale_ssrcs:
            self.audio_by_ssrc.pop(ssrc, None)

    def clear(self) -> None:
        self.audio_by_ssrc.clear()
