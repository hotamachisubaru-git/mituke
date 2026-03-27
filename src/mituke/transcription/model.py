from __future__ import annotations

from functools import lru_cache

from rich.console import Console
from vosk import Model

console = Console()


@lru_cache(maxsize=4)
def load_vosk_model(model_path: str) -> Model:
    console.log(f"Vosk モデルを読み込みます: {model_path}")
    return Model(model_path)
