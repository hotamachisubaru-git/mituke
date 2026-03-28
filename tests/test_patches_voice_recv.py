from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from mituke.patches.voice_recv import FALLBACK_PCM, install_packet_decoder_guard


class FakeOpusError(Exception):
    pass


class FakeDecoder:
    def __init__(self) -> None:
        self.calls: list[tuple[bytes | None, bool]] = []

    def decode(self, data: bytes | None, *, fec: bool) -> bytes:
        self.calls.append((data, fec))
        return b"concealed"


class BrokenConcealmentDecoder:
    def decode(self, data: bytes | None, *, fec: bool) -> bytes:
        raise FakeOpusError("concealment failed")


class FakePacketDecoder:
    def __init__(self, decoder: object | None = None) -> None:
        self._decoder = decoder or FakeDecoder()

    def _decode_packet(self, _packet: object) -> tuple[object, bytes]:
        raise FakeOpusError("bad packet")


class PacketDecoderGuardTests(unittest.TestCase):
    def test_replaces_corrupted_packet_with_concealed_pcm_and_resets_decoder(
        self,
    ) -> None:
        console = Mock()

        with (
            patch("mituke.patches.voice_recv.PacketDecoder", FakePacketDecoder),
            patch("mituke.patches.voice_recv.Decoder", FakeDecoder),
            patch("mituke.patches.voice_recv.OpusError", FakeOpusError),
            patch("mituke.patches.voice_recv._log_corrupted_packet") as log_warning,
        ):
            install_packet_decoder_guard(console)
            packet_decoder = FakePacketDecoder()
            previous_decoder = packet_decoder._decoder
            packet = object()

            returned_packet, pcm = packet_decoder._decode_packet(packet)

        self.assertIs(returned_packet, packet)
        self.assertEqual(pcm, b"concealed")
        self.assertIsNot(packet_decoder._decoder, previous_decoder)
        self.assertIsInstance(packet_decoder._decoder, FakeDecoder)
        log_warning.assert_called_once()

    def test_falls_back_to_silence_when_loss_concealment_fails(self) -> None:
        console = Mock()

        with (
            patch("mituke.patches.voice_recv.PacketDecoder", FakePacketDecoder),
            patch("mituke.patches.voice_recv.Decoder", FakeDecoder),
            patch("mituke.patches.voice_recv.OpusError", FakeOpusError),
            patch("mituke.patches.voice_recv._log_corrupted_packet"),
        ):
            install_packet_decoder_guard(console)
            packet_decoder = FakePacketDecoder(decoder=BrokenConcealmentDecoder())
            packet = object()

            returned_packet, pcm = packet_decoder._decode_packet(packet)

        self.assertIs(returned_packet, packet)
        self.assertEqual(pcm, FALLBACK_PCM)
        self.assertIsInstance(packet_decoder._decoder, FakeDecoder)
