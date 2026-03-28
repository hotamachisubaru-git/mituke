from __future__ import annotations

from typing import Any

try:
    import audioop
except ModuleNotFoundError:
    import audioop_lts as audioop


def convert_pcm_48khz_stereo_to_16khz_mono(
    pcm: bytes,
    state: Any = None,
) -> tuple[bytes, Any]:
    if not pcm:
        return b"", state

    mono_48khz_pcm = audioop.tomono(pcm, 2, 0.5, 0.5)
    mono_16khz_pcm, next_state = audioop.ratecv(
        mono_48khz_pcm,
        2,
        1,
        48000,
        16000,
        state,
    )
    return mono_16khz_pcm, next_state
