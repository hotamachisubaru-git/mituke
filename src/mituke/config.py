from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import discord
from dotenv import load_dotenv
from rich.console import Console


@dataclass(frozen=True)
class Settings:
    discord_token: str
    vosk_model_path: Path
    discord_opus_path: Path | None


def load_settings() -> Settings:
    load_dotenv()

    discord_token = os.getenv("DISCORD_TOKEN", "").strip()
    if not discord_token:
        raise RuntimeError(
            "DISCORD_TOKEN が設定されていません。.env か環境変数に Bot トークンを設定してください。"
        )

    model_path_text = (
        os.getenv("VOSK_MODEL_PATH", "").strip()
        or os.getenv("MODEL_PATH", "").strip()
    )
    if not model_path_text:
        raise RuntimeError(
            "VOSK_MODEL_PATH または MODEL_PATH が設定されていません。"
            " Vosk のモデルフォルダを指定してください。"
        )

    vosk_model_path = Path(model_path_text).expanduser()
    if not vosk_model_path.exists():
        raise RuntimeError(f"Vosk モデルが見つかりません: {vosk_model_path}")

    opus_path_text = os.getenv("DISCORD_OPUS_PATH", "").strip()
    discord_opus_path = Path(opus_path_text).expanduser() if opus_path_text else None
    if discord_opus_path is not None and not discord_opus_path.exists():
        raise RuntimeError(
            f"DISCORD_OPUS_PATH で指定されたファイルが見つかりません: {discord_opus_path}"
        )

    return Settings(
        discord_token=discord_token,
        vosk_model_path=vosk_model_path,
        discord_opus_path=discord_opus_path,
    )


def configure_opus(settings: Settings, console: Console) -> None:
    if discord.opus.is_loaded():
        return

    if settings.discord_opus_path is not None:
        discord.opus.load_opus(str(settings.discord_opus_path))
        if not discord.opus.is_loaded():
            raise RuntimeError(
                "Opus の読み込みに失敗しました。DISCORD_OPUS_PATH を確認してください。"
            )
        return

    if os.name == "nt":
        console.log(
            "注意: Windows で Opus が自動読込されない場合は、"
            " DISCORD_OPUS_PATH に `libopus-0.dll` のパスを設定してください。"
        )
