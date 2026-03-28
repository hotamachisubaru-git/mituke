from __future__ import annotations

import unittest
from types import SimpleNamespace
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


class DeferredPacketDecoder:
    def __init__(self) -> None:
        self._decoder = FakeDecoder()
        self._cached_id: int | None = None
        self.ssrc = 42
        self.processed_packets: list[object] = []
        self.write_calls: list[tuple[object | None, object]] = []
        self.dave_session = Mock(ready=True)
        self.dave_session.decrypt.side_effect = lambda *_args: b"decoded-opus"
        self.sink = SimpleNamespace(
            write=lambda user, data: self.write_calls.append((user, data)),
            voice_client=SimpleNamespace(
                _connection=SimpleNamespace(dave_session=self.dave_session),
                _get_id_from_ssrc=lambda _ssrc: self._cached_id,
            ),
        )

    def _decode_packet(self, packet: object) -> tuple[object, bytes]:
        return packet, b"pcm"

    def _process_packet(self, packet: object):
        self.processed_packets.append(packet)
        return SimpleNamespace(source=self._get_cached_member(), pcm=b"pcm")

    def _get_cached_member(self):
        if self._cached_id is None:
            return None
        return SimpleNamespace(id=self._cached_id)

    def set_user_id(self, user_id: int) -> None:
        self._cached_id = user_id


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

    def test_replays_buffered_dave_packet_when_user_mapping_arrives(self) -> None:
        console = Mock()

        with patch("mituke.patches.voice_recv.PacketDecoder", DeferredPacketDecoder):
            install_packet_decoder_guard(console)
            packet_decoder = DeferredPacketDecoder()
            packet = SimpleNamespace(
                decrypted_data=b"encrypted-opus",
                is_silence=lambda: False,
                payload=120,
                sequence=10,
                timestamp=960,
            )

            deferred_data = packet_decoder._process_packet(packet)

            self.assertEqual(deferred_data.pcm, b"")
            self.assertEqual(packet_decoder.processed_packets, [])
            self.assertEqual(packet_decoder.write_calls, [])

            packet_decoder.set_user_id(123)

        self.assertEqual(packet_decoder.processed_packets, [packet])
        self.assertEqual(len(packet_decoder.write_calls), 1)
        self.assertEqual(packet.decrypted_data, b"decoded-opus")
