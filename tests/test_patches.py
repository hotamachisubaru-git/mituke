from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from mituke.patches import voice_recv as voice_recv_patch


class VoiceRecvPatchTests(unittest.TestCase):
    def test_ensure_dave_passthrough_sets_flag_once(self) -> None:
        dave_session = Mock()
        connection = SimpleNamespace(dave_session=dave_session)
        decoder = SimpleNamespace(
            sink=SimpleNamespace(voice_client=SimpleNamespace(_connection=connection))
        )

        voice_recv_patch._ensure_dave_passthrough(decoder)
        voice_recv_patch._ensure_dave_passthrough(decoder)

        dave_session.set_passthrough_mode.assert_called_once_with(True, 10)
        self.assertTrue(
            getattr(connection, voice_recv_patch.DAVE_PASSTHROUGH_FLAG, False)
        )

    def test_is_non_audio_packet_checks_payload_type(self) -> None:
        self.assertFalse(
            voice_recv_patch._is_non_audio_packet(SimpleNamespace(payload=120))
        )
        self.assertTrue(
            voice_recv_patch._is_non_audio_packet(SimpleNamespace(payload=96))
        )
        self.assertFalse(voice_recv_patch._is_non_audio_packet(SimpleNamespace()))

    def test_prepare_dave_audio_packet_decrypts_when_session_is_ready(self) -> None:
        console = Mock()
        dave_session = Mock(ready=True)
        dave_session.decrypt.return_value = b"decoded-opus"
        decoder = SimpleNamespace(
            sink=SimpleNamespace(
                voice_client=SimpleNamespace(
                    _connection=SimpleNamespace(dave_session=dave_session)
                )
            )
        )
        packet = SimpleNamespace(
            decrypted_data=b"encrypted-opus",
            is_silence=lambda: False,
        )
        member = SimpleNamespace(id=123)

        result = voice_recv_patch._prepare_dave_audio_packet(
            decoder,
            packet,
            member,
            console,
        )

        self.assertTrue(result)
        dave_session.decrypt.assert_called_once_with(
            123,
            voice_recv_patch.MediaType.audio,
            b"encrypted-opus",
        )
        self.assertEqual(packet.decrypted_data, b"decoded-opus")
        console.log.assert_not_called()

    def test_prepare_dave_audio_packet_skips_when_member_is_missing(self) -> None:
        console = Mock()
        dave_session = Mock(ready=True)
        decoder = SimpleNamespace(
            sink=SimpleNamespace(
                voice_client=SimpleNamespace(
                    _connection=SimpleNamespace(dave_session=dave_session)
                )
            )
        )
        packet = SimpleNamespace(
            decrypted_data=b"encrypted-opus",
            is_silence=lambda: False,
        )

        result = voice_recv_patch._prepare_dave_audio_packet(
            decoder,
            packet,
            None,
            console,
        )

        self.assertFalse(result)
        dave_session.decrypt.assert_not_called()
        console.log.assert_called_once()

    def test_remember_packet_position_updates_decoder_state(self) -> None:
        decoder = SimpleNamespace(_last_seq=-1, _last_ts=-1)
        packet = SimpleNamespace(sequence=77, timestamp=8800)

        voice_recv_patch._remember_packet_position(decoder, packet)

        self.assertEqual(decoder._last_seq, 77)
        self.assertEqual(decoder._last_ts, 8800)
