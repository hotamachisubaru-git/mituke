from __future__ import annotations

import sys
from array import array


def convert_pcm_48khz_stereo_to_16khz_mono(pcm: bytes) -> bytes:
    if not pcm:
        return b""

    stereo_samples = array("h")
    stereo_samples.frombytes(pcm)

    if sys.byteorder != "little":
        stereo_samples.byteswap()

    mono_samples: list[int] = []
    for index in range(0, len(stereo_samples) - 1, 2):
        left = stereo_samples[index]
        right = stereo_samples[index + 1]
        mono_samples.append((left + right) // 2)

    reduced_samples = array("h")
    for index in range(0, len(mono_samples), 3):
        chunk = mono_samples[index : index + 3]
        if not chunk:
            continue
        reduced_samples.append(sum(chunk) // len(chunk))

    if sys.byteorder != "little":
        reduced_samples.byteswap()

    return reduced_samples.tobytes()
