from __future__ import annotations

import unittest

from mituke.transcription.pending_audio import PendingAudioBuffer


class PendingAudioBufferTests(unittest.TestCase):
    def test_keeps_only_recent_audio_up_to_max_bytes(self) -> None:
        buffer = PendingAudioBuffer(retention_seconds=1.0, max_bytes=4)

        buffer.remember(42, b"abcd", 1.0)
        buffer.remember(42, b"ef", 1.1)

        self.assertEqual(buffer.take(42, 1.1), b"cdef")

    def test_drops_stale_audio_before_take(self) -> None:
        buffer = PendingAudioBuffer(retention_seconds=1.0, max_bytes=8)

        buffer.remember(42, b"abcd", 1.0)

        self.assertEqual(buffer.take(42, 2.1), b"")

    def test_clears_all_pending_audio(self) -> None:
        buffer = PendingAudioBuffer(retention_seconds=1.0, max_bytes=8)

        buffer.remember(42, b"abcd", 1.0)
        buffer.clear()

        self.assertEqual(buffer.audio_by_ssrc, {})
