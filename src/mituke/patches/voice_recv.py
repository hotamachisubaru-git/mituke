from __future__ import annotations

import logging
import time
from typing import Any

from discord.opus import Decoder, OpusError
from discord.ext.voice_recv.opus import PacketDecoder
from rich.console import Console

log = logging.getLogger(__name__)

PATCH_FLAG = "__mituke_packet_decoder_guard_installed__"
WARNING_INTERVAL_SECONDS = 5.0
FALLBACK_PCM = b"\x00\x00" * Decoder.SAMPLES_PER_FRAME * Decoder.CHANNELS
_last_warning_at = 0.0


def install_packet_decoder_guard(console: Console) -> None:
    if getattr(PacketDecoder, PATCH_FLAG, False):
        return

    original_decode_packet = PacketDecoder._decode_packet

    def safe_decode_packet(self: PacketDecoder, packet: Any):
        try:
            return original_decode_packet(self, packet)
        except OpusError as error:
            _log_corrupted_packet(console, error)
            pcm = _decode_missing_pcm(self)
            _reset_decoder(self)
            return packet, pcm

    PacketDecoder._decode_packet = safe_decode_packet  # type: ignore[method-assign]
    setattr(PacketDecoder, PATCH_FLAG, True)


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


def _log_corrupted_packet(console: Console, error: OpusError) -> None:
    global _last_warning_at

    now = time.monotonic()
    if now - _last_warning_at < WARNING_INTERVAL_SECONDS:
        return

    _last_warning_at = now
    message = (
        "壊れた音声パケットを検知したため、その区間を無音補完して受信を続けます。"
    )
    log.warning("%s detail=%s", message, error)
    console.log(message)
