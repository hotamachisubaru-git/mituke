from __future__ import annotations

from typing import Any

try:
    import audioop
except ModuleNotFoundError:
    import audioop_lts as audioop

from discord.opus import Decoder

PCM_SAMPLE_WIDTH_BYTES = 2
VOSK_SAMPLE_RATE = 16000


def _to_mono_pcm(pcm: bytes, channels: int) -> bytes:
    if channels == 1:
        return pcm
    if channels != 2:
        raise ValueError(
            f"unsupported PCM channel count: expected 1 or 2, got {channels}"
        )

    return audioop.tomono(pcm, PCM_SAMPLE_WIDTH_BYTES, 0.5, 0.5)


def _resample_pcm(
    mono_pcm: bytes,
    *,
    input_sample_rate: int,
    output_sample_rate: int,
    state: Any | None,
) -> tuple[bytes, Any | None]:
    if not mono_pcm:
        return b"", state

    if input_sample_rate == output_sample_rate:
        return mono_pcm, state

    return audioop.ratecv(
        mono_pcm,
        PCM_SAMPLE_WIDTH_BYTES,
        1,
        input_sample_rate,
        output_sample_rate,
        state,
    )


class DiscordPcmConverter:
    def __init__(
        self,
        *,
        input_sample_rate: int = Decoder.SAMPLING_RATE,
        input_channels: int = Decoder.CHANNELS,
        output_sample_rate: int = VOSK_SAMPLE_RATE,
    ) -> None:
        self.input_sample_rate = input_sample_rate
        self.input_channels = input_channels
        self.output_sample_rate = output_sample_rate
        self._ratecv_state: Any | None = None

    def convert(self, pcm: bytes) -> bytes:
        if not pcm:
            return b""

        mono_pcm = _to_mono_pcm(pcm, self.input_channels)
        converted_pcm, self._ratecv_state = _resample_pcm(
            mono_pcm,
            input_sample_rate=self.input_sample_rate,
            output_sample_rate=self.output_sample_rate,
            state=self._ratecv_state,
        )
        return converted_pcm


def convert_pcm_48khz_stereo_to_16khz_mono(
    pcm: bytes,
    state: Any | None = None,
) -> tuple[bytes, Any | None]:
    if not pcm:
        return b"", state

    mono_pcm = _to_mono_pcm(pcm, Decoder.CHANNELS)
    return _resample_pcm(
        mono_pcm,
        input_sample_rate=Decoder.SAMPLING_RATE,
        output_sample_rate=VOSK_SAMPLE_RATE,
        state=state,
    )
