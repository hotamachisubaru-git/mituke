from pathlib import Path
from typing import Any, Protocol

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
