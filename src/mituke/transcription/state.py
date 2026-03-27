from __future__ import annotations

from dataclasses import dataclass, field

import discord
from vosk import KaldiRecognizer


@dataclass
class RecognitionState:
    recognizer: KaldiRecognizer
    display_name: str
    committed_texts: list[str] = field(default_factory=list)
    partial_text: str = ""
    last_partial_sent_at: float = 0.0


@dataclass
class MessageState:
    message: discord.Message | None = None
    last_content: str = ""


@dataclass(frozen=True)
class SinkEvent:
    kind: str
    user_id: int
    display_name: str
    text: str = ""
