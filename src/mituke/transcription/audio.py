from __future__ import annotations

import audioop

from discord.opus import Decoder

PCM_SAMPLE_WIDTH_BYTES = 2
VOSK_SAMPLE_RATE = 16000


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
        self._ratecv_state: object | None = None

    def convert(self, pcm: bytes) -> bytes:
        if not pcm:
            return b""

        mono_pcm = self._to_mono(pcm)
        if self.input_sample_rate == self.output_sample_rate:
            return mono_pcm

        converted_pcm, self._ratecv_state = audioop.ratecv(
            mono_pcm,
            PCM_SAMPLE_WIDTH_BYTES,
            1,
            self.input_sample_rate,
            self.output_sample_rate,
            self._ratecv_state,
        )
        return converted_pcm

    def _to_mono(self, pcm: bytes) -> bytes:
        if self.input_channels == 1:
            return pcm
        if self.input_channels != 2:
            raise ValueError(
                f"unsupported PCM channel count: expected 1 or 2, got {self.input_channels}"
            )

        return audioop.tomono(pcm, PCM_SAMPLE_WIDTH_BYTES, 0.5, 0.5)


def convert_pcm_48khz_stereo_to_16khz_mono(pcm: bytes) -> bytes:
    return DiscordPcmConverter().convert(pcm)
