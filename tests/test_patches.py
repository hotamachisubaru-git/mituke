from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

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

    def test_resolve_member_uses_current_ssrc_mapping_without_waiting(self) -> None:
        member = SimpleNamespace(id=123)
        decoder = SimpleNamespace(
            sink=SimpleNamespace(
                voice_client=SimpleNamespace(_get_id_from_ssrc=lambda _ssrc: 123)
            ),
            ssrc=42,
            _cached_id=None,
            _get_cached_member=lambda: member if decoder._cached_id == 123 else None,
        )

        result = voice_recv_patch._resolve_member(decoder)

        self.assertIs(result, member)
        self.assertEqual(decoder._cached_id, 123)

    def test_flush_pending_dave_packets_replays_buffered_audio(self) -> None:
        console = Mock()
        member = SimpleNamespace(id=123)
        dave_session = Mock(ready=True)
        dave_session.decrypt.return_value = b"decoded-opus"
        writes: list[tuple[object, object]] = []
        decoder = SimpleNamespace(
            sink=SimpleNamespace(
                write=lambda user, data: writes.append((user, data)),
                voice_client=SimpleNamespace(
                    _connection=SimpleNamespace(dave_session=dave_session)
                ),
            ),
            _get_cached_member=lambda: member,
        )
        packet = SimpleNamespace(
            decrypted_data=b"encrypted-opus",
            is_silence=lambda: False,
        )
        setattr(decoder, voice_recv_patch.PENDING_DAVE_PACKETS_FLAG, [packet])
        processed_data = SimpleNamespace(source=member, pcm=b"pcm")
        process_packet = Mock(return_value=processed_data)

        voice_recv_patch._flush_pending_dave_packets(
            decoder,
            member,
            process_packet,
            console,
        )

        process_packet.assert_called_once_with(decoder, packet)
        dave_session.decrypt.assert_called_once_with(
            123,
            voice_recv_patch.MediaType.audio,
            b"encrypted-opus",
        )
        self.assertEqual(packet.decrypted_data, b"decoded-opus")
        self.assertEqual(writes, [(member, processed_data)])
        self.assertEqual(
            getattr(decoder, voice_recv_patch.PENDING_DAVE_PACKETS_FLAG),
            [],
        )

    def test_log_missing_member_for_dave_uses_console_only(self) -> None:
        console = Mock()

        with (
            patch("mituke.patches.voice_recv._should_log_warning", return_value=True),
            patch("mituke.patches.voice_recv.log.warning") as log_warning,
        ):
            voice_recv_patch._log_missing_member_for_dave(console)

        log_warning.assert_not_called()
        console.log.assert_called_once_with(
            "発話者の対応付け前に暗号化音声を受信したため、そのパケットをスキップして受信を続けます。"
        )

    def test_remember_packet_position_updates_decoder_state(self) -> None:
        decoder = SimpleNamespace(_last_seq=-1, _last_ts=-1)
        packet = SimpleNamespace(sequence=77, timestamp=8800)

        voice_recv_patch._remember_packet_position(decoder, packet)

        self.assertEqual(decoder._last_seq, 77)
        self.assertEqual(decoder._last_ts, 8800)
