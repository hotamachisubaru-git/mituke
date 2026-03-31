from pathlib import Path
from typing import Any, Protocol

import numpy as np
from faster_whisper import WhisperModel
from vosk import KaldiRecognizer

from mituke.transcription.model import load_vosk_model


class SpeechRecognizer(Protocol):
    def create(self) -> Any:
        """話者ごとの新しい認識インスタンスを作成"""


class VoskRecognizer:
    """Vosk の speech recognizer factory"""

    def __init__(self, model_path: Path) -> None:
        self.model = load_vosk_model(str(model_path.resolve()))

    def create(self) -> KaldiRecognizer:
        """KaldiRecognizer instance を作成する (ユーザーごと)"""
        return KaldiRecognizer(self.model, 16000)


class WhisperInstance:
    """Stateful wrapper for faster-whisper"""

    def __init__(self, model: WhisperModel) -> None:
        self.model = model
        self.buffer = bytearray()

    def accept_waveform(self, pcm: bytes) -> bool:
        """Append audio and decide when to run inference"""
        self.buffer.extend(pcm)

        # 約1秒ごとに処理（16kHz, mono, 16bit）
        return len(self.buffer) >= 16000 * 2

    def result(self) -> str:
        """Run transcription on current buffer"""
        audio = np.frombuffer(self.buffer, dtype=np.int16).astype(np.float32) / 32768.0

        segments, _ = self.model.transcribe(audio, language="ja")

        text = "".join(seg.text for seg in segments)

        self.buffer.clear()
        return text

    def partial_result(self) -> str:
        """Optional partial (same as result for now)"""
        return self.result()

    def final_result(self) -> str:
        """Flush remaining audio"""
        if not self.buffer:
            return ""

        return self.result()


class WhisperRecognizer:
    """faster-whisper recognizer factory"""

    def __init__(self, model: WhisperModel) -> None:
        self.model = model

    def create(self) -> WhisperInstance:
        return WhisperInstance(self.model)
