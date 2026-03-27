from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from mituke.config import Settings, configure_opus, load_settings


class LoadSettingsTests(unittest.TestCase):
    def test_requires_discord_token(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with (
                patch("mituke.config.load_dotenv"),
                patch.dict(os.environ, {"VOSK_MODEL_PATH": temp_dir}, clear=True),
            ):
                with self.assertRaisesRegex(RuntimeError, "DISCORD_TOKEN"):
                    load_settings()

    def test_uses_vosk_model_and_optional_opus_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "model"
            opus_path = Path(temp_dir) / "libopus-0.dll"
            model_path.mkdir()
            opus_path.write_bytes(b"opus")

            with (
                patch("mituke.config.load_dotenv"),
                patch.dict(
                    os.environ,
                    {
                        "DISCORD_TOKEN": "test-token",
                        "VOSK_MODEL_PATH": str(model_path),
                        "DISCORD_OPUS_PATH": str(opus_path),
                    },
                    clear=True,
                ),
            ):
                settings = load_settings()

        self.assertEqual(
            settings,
            Settings(
                discord_token="test-token",
                vosk_model_path=model_path,
                discord_opus_path=opus_path,
            ),
        )

    def test_falls_back_to_legacy_model_path_variable(self) -> None:
        with TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "legacy-model"
            model_path.mkdir()

            with (
                patch("mituke.config.load_dotenv"),
                patch.dict(
                    os.environ,
                    {
                        "DISCORD_TOKEN": "test-token",
                        "MODEL_PATH": str(model_path),
                    },
                    clear=True,
                ),
            ):
                settings = load_settings()

        self.assertEqual(settings.vosk_model_path, model_path)
        self.assertIsNone(settings.discord_opus_path)

    def test_requires_existing_model_directory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            missing_model_path = Path(temp_dir) / "missing-model"

            with (
                patch("mituke.config.load_dotenv"),
                patch.dict(
                    os.environ,
                    {
                        "DISCORD_TOKEN": "test-token",
                        "VOSK_MODEL_PATH": str(missing_model_path),
                    },
                    clear=True,
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "Vosk モデルが見つかりません"):
                    load_settings()

    def test_requires_existing_opus_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "model"
            missing_opus_path = Path(temp_dir) / "missing-opus.dll"
            model_path.mkdir()

            with (
                patch("mituke.config.load_dotenv"),
                patch.dict(
                    os.environ,
                    {
                        "DISCORD_TOKEN": "test-token",
                        "VOSK_MODEL_PATH": str(model_path),
                        "DISCORD_OPUS_PATH": str(missing_opus_path),
                    },
                    clear=True,
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "DISCORD_OPUS_PATH で指定されたファイルが見つかりません"
                ):
                    load_settings()


class ConfigureOpusTests(unittest.TestCase):
    def test_skips_when_opus_is_already_loaded(self) -> None:
        console = Mock()
        settings = Settings("token", Path("model"), None)

        with (
            patch("mituke.config.discord.opus.is_loaded", return_value=True),
            patch("mituke.config.discord.opus.load_opus") as load_opus,
        ):
            configure_opus(settings, console)

        load_opus.assert_not_called()
        console.log.assert_not_called()

    def test_loads_explicit_opus_path(self) -> None:
        console = Mock()
        settings = Settings("token", Path("model"), Path("C:/opus/libopus-0.dll"))

        with (
            patch(
                "mituke.config.discord.opus.is_loaded",
                side_effect=[False, True],
            ),
            patch("mituke.config.discord.opus.load_opus") as load_opus,
        ):
            configure_opus(settings, console)

        load_opus.assert_called_once_with(str(settings.discord_opus_path))
        console.log.assert_not_called()

    def test_raises_when_explicit_opus_path_cannot_be_loaded(self) -> None:
        console = Mock()
        settings = Settings("token", Path("model"), Path("C:/opus/libopus-0.dll"))

        with (
            patch(
                "mituke.config.discord.opus.is_loaded",
                side_effect=[False, False],
            ),
            patch("mituke.config.discord.opus.load_opus"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Opus の読み込みに失敗しました"):
                configure_opus(settings, console)

    def test_logs_windows_hint_without_explicit_path(self) -> None:
        console = Mock()
        settings = Settings("token", Path("model"), None)

        with (
            patch("mituke.config.discord.opus.is_loaded", return_value=False),
            patch("mituke.config.os.name", "nt"),
        ):
            configure_opus(settings, console)

        console.log.assert_called_once()
