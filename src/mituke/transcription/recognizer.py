from pathlib import Path
from typing import Any, Protocol

import numpy as np
from faster_whisper import WhisperModel
from vosk import KaldiRecognizer

from mituke.transcription.model import load_vosk_model


class SpeechRecognizer(Protocol):
    def create(self) -> Any:
        """話者ごとの新しい認識インスタンスを作成する。"""


class VoskRecognizer:
    """Vosk ベースの認識器ファクトリ。"""

    def __init__(self, model_path: Path) -> None:
        self.model = load_vosk_model(str(model_path.resolve()))

    def create(self) -> KaldiRecognizer:
        return KaldiRecognizer(self.model, 16000)


class WhisperInstance:
    """faster-whisper のステートフルなラッパー"""

    def __init__(self, model: WhisperModel) -> None:
        self.model = model
        self.buffer = bytearray()

    def accept_waveform(self, pcm: bytes) -> bool:
        """音声を追加し、推論を実行するタイミングを決定する"""
        self.buffer.extend(pcm)

        # 約1秒ごとに処理（16kHz, mono, 16bit）
        return len(self.buffer) >= 16000 * 2

    def result(self) -> str:
        """現在のバッファで転写を実行する"""
        audio = np.frombuffer(self.buffer, dtype=np.int16).astype(np.float32) / 32768.0

        segments, _ = self.model.transcribe(audio, language="ja")

        text = "".join(seg.text for seg in segments)

        self.buffer.clear()
        return text

    def partial_result(self) -> str:
        """オプションの部分的結果（現時点では結果と同じ）"""
        return self.result()

    def final_result(self) -> str:
        """残りの音声をフラッシュする"""
        if not self.buffer:
            return ""

        return self.result()


class WhisperRecognizer:
    """faster-whisper の認識器ファクトリ"""

    def __init__(self, model: WhisperModel) -> None:
        self.model = model

    def create(self) -> WhisperInstance:
        return WhisperInstance(self.model)
