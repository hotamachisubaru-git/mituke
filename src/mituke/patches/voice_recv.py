from __future__ import annotations

import logging
import time
from typing import Any

from discord.opus import Decoder, OpusError
from discord.ext.voice_recv.opus import PacketDecoder, VoiceData
from rich.console import Console

try:
    from davey import MediaType

    HAS_DAVE = True
except ImportError:
    MediaType = None
    HAS_DAVE = False

log = logging.getLogger(__name__)

PATCH_FLAG = "__mituke_packet_decoder_guard_installed__"
DAVE_PASSTHROUGH_FLAG = "__mituke_dave_passthrough_enabled__"
FLUSH_WARNING_FILTER_FLAG = "__mituke_decoder_flush_warning_filter__"
OPUS_AUDIO_PAYLOAD_TYPE = 120
WARNING_INTERVAL_SECONDS = 5.0
WARNING_INTERVALS_BY_KEY = {
    "decoder_flush_loss": 30.0,
    "missing_member_for_dave": 30.0,
}
SSRC_MAPPING_WAIT_SECONDS = 0.1
SSRC_MAPPING_POLL_SECONDS = 0.01
FALLBACK_PCM = b"\x00\x00" * Decoder.SAMPLES_PER_FRAME * Decoder.CHANNELS
DECODER_FLUSH_WARNING_TEXT = "packets were lost being flushed in decoder"
_last_warning_at: dict[str, float] = {}


def install_packet_decoder_guard(console: Console) -> None:
    _install_decoder_flush_warning_filter(console)
    if getattr(PacketDecoder, PATCH_FLAG, False):
        return

    original_decode_packet = PacketDecoder._decode_packet
    original_process_packet = getattr(PacketDecoder, "_process_packet", None)

    def safe_decode_packet(self: PacketDecoder, packet: Any):
        try:
            return original_decode_packet(self, packet)
        except OpusError as error:
            _log_corrupted_packet(console, error)
            pcm = _decode_missing_pcm(self)
            _reset_decoder(self)
            return packet, pcm

    PacketDecoder._decode_packet = safe_decode_packet  # type: ignore[method-assign]
    if original_process_packet is not None:

        def safe_process_packet(self: PacketDecoder, packet: Any):
            _ensure_dave_passthrough(self)
            member = _resolve_member(self)

            if _is_non_audio_packet(packet):
                _remember_packet_position(self, packet)
                _log_non_audio_packet(console, packet)
                return VoiceData(packet, member, pcm=b"")

            if not _prepare_dave_audio_packet(self, packet, member, console):
                _remember_packet_position(self, packet)
                return VoiceData(packet, member, pcm=b"")

            return original_process_packet(self, packet)

        PacketDecoder._process_packet = safe_process_packet  # type: ignore[method-assign]
    setattr(PacketDecoder, PATCH_FLAG, True)


def _install_decoder_flush_warning_filter(console: Console) -> None:
    logger = logging.getLogger("discord.ext.voice_recv.opus")
    if any(getattr(flt, FLUSH_WARNING_FILTER_FLAG, False) for flt in logger.filters):
        return

    class DecoderFlushWarningFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            if DECODER_FLUSH_WARNING_TEXT not in record.getMessage():
                return True

            if _should_log_warning("decoder_flush_loss"):
                console.log(
                    "VC 受信で一部の音声パケット欠落を検知しました。受信は継続します。"
                )
            return False

    warning_filter = DecoderFlushWarningFilter()
    setattr(warning_filter, FLUSH_WARNING_FILTER_FLAG, True)
    logger.addFilter(warning_filter)


def _decode_missing_pcm(packet_decoder: PacketDecoder) -> bytes:
    decoder = getattr(packet_decoder, "_decoder", None)
    if decoder is None:
        return FALLBACK_PCM

    try:
        return decoder.decode(None, fec=False)
    except OpusError:
        return FALLBACK_PCM


def _reset_decoder(packet_decoder: PacketDecoder) -> None:
    if getattr(packet_decoder, "_decoder", None) is None:
        return

    packet_decoder._decoder = Decoder()


def _ensure_dave_passthrough(decoder: PacketDecoder) -> None:
    voice_client = getattr(decoder.sink, "voice_client", None)
    connection = getattr(voice_client, "_connection", None)
    if connection is None or getattr(connection, DAVE_PASSTHROUGH_FLAG, False):
        return

    dave_session = getattr(connection, "dave_session", None)
    if dave_session is None or not hasattr(dave_session, "set_passthrough_mode"):
        return

    try:
        dave_session.set_passthrough_mode(True, 10)
    except Exception:
        log.debug("DAVE の passthrough mode 設定に失敗しました。", exc_info=True)
        return

    setattr(connection, DAVE_PASSTHROUGH_FLAG, True)


def _resolve_member(decoder: PacketDecoder) -> Any:
    member = decoder._get_cached_member()
    if member is not None:
        return member

    voice_client = getattr(decoder.sink, "voice_client", None)
    if voice_client is None:
        return None

    deadline = time.monotonic() + SSRC_MAPPING_WAIT_SECONDS
    while True:
        try:
            decoder._cached_id = voice_client._get_id_from_ssrc(decoder.ssrc)  # type: ignore[attr-defined]
        except Exception:
            return None

        member = decoder._get_cached_member()
        if member is not None:
            return member

        if time.monotonic() >= deadline:
            return None

        time.sleep(SSRC_MAPPING_POLL_SECONDS)


def _is_non_audio_packet(packet: Any) -> bool:
    payload = getattr(packet, "payload", None)
    return payload is not None and payload != OPUS_AUDIO_PAYLOAD_TYPE


def _prepare_dave_audio_packet(
    decoder: PacketDecoder,
    packet: Any,
    member: Any,
    console: Console,
) -> bool:
    if not HAS_DAVE or MediaType is None or not packet:
        return True

    is_silence = getattr(packet, "is_silence", None)
    if callable(is_silence) and is_silence():
        return True

    decrypted_data = getattr(packet, "decrypted_data", None)
    if decrypted_data is None:
        return True

    voice_client = getattr(decoder.sink, "voice_client", None)
    connection = getattr(voice_client, "_connection", None)
    dave_session = getattr(connection, "dave_session", None)
    if dave_session is None or not getattr(dave_session, "ready", False):
        return True

    if member is None:
        _log_missing_member_for_dave(console)
        return False

    try:
        packet.decrypted_data = dave_session.decrypt(
            member.id,
            MediaType.audio,
            bytes(decrypted_data),
        )
    except Exception as error:
        _log_dave_decrypt_failure(console, error)
        return False

    return True


def _remember_packet_position(decoder: PacketDecoder, packet: Any) -> None:
    sequence = getattr(packet, "sequence", None)
    if sequence is not None:
        decoder._last_seq = sequence

    timestamp = getattr(packet, "timestamp", None)
    if timestamp is not None:
        decoder._last_ts = timestamp


def _should_log_warning(key: str) -> bool:
    now = time.monotonic()
    last_warning_at = _last_warning_at.get(key, 0.0)
    warning_interval = WARNING_INTERVALS_BY_KEY.get(key, WARNING_INTERVAL_SECONDS)
    if now - last_warning_at < warning_interval:
        return False

    _last_warning_at[key] = now
    return True


def _log_corrupted_packet(console: Console, error: OpusError) -> None:
    if not _should_log_warning("corrupted_packet"):
        return

    message = "壊れた音声パケットを検知したため、その区間を無音補完して受信を続けます。"
    log.warning("%s detail=%s", message, error)
    console.log(message)


def _log_non_audio_packet(console: Console, packet: Any) -> None:
    if not _should_log_warning("non_audio_packet"):
        return

    payload = getattr(packet, "payload", None)
    message = "音声以外の RTP パケットを検知したため、そのパケットをスキップして受信を続けます。"
    log.warning("%s payload=%s", message, payload)
    console.log(message)


def _log_missing_member_for_dave(console: Console) -> None:
    if not _should_log_warning("missing_member_for_dave"):
        return

    message = "発話者の対応付け前に暗号化音声を受信したため、そのパケットをスキップして受信を続けます。"
    log.warning(message)
    console.log(message)


def _log_dave_decrypt_failure(console: Console, error: Exception) -> None:
    if not _should_log_warning("dave_decrypt_failure"):
        return

    message = "DAVE 復号に失敗した音声パケットを検知したため、そのパケットだけスキップして受信を続けます。"
    log.warning("%s detail=%s", message, error)
    console.log(message)
