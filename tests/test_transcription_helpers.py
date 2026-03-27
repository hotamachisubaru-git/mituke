from __future__ import annotations

import unittest
from array import array

from mituke.transcription.audio import convert_pcm_48khz_stereo_to_16khz_mono
from mituke.transcription.text import join_transcript_parts, normalize_transcript


class NormalizeTranscriptTests(unittest.TestCase):
    def test_removes_extra_whitespace(self) -> None:
        self.assertEqual(normalize_transcript("  hello   world  "), "hello world")

    def test_joins_japanese_words_without_spaces(self) -> None:
        self.assertEqual(normalize_transcript("  今日は  いい 天気  "), "今日はいい天気")

    def test_keeps_spaces_when_latin_text_is_present(self) -> None:
        self.assertEqual(
            normalize_transcript("  hello   世界  "),
            "hello 世界",
        )

    def test_joins_transcript_parts_and_normalizes_result(self) -> None:
        self.assertEqual(
            join_transcript_parts(["  今日 は ", "", "  いい 天気  "]),
            "今日はいい天気",
        )


class ConvertPcmTests(unittest.TestCase):
    def test_returns_empty_bytes_for_empty_pcm(self) -> None:
        self.assertEqual(convert_pcm_48khz_stereo_to_16khz_mono(b""), b"")

    def test_converts_48khz_stereo_pcm_to_16khz_mono(self) -> None:
        stereo_samples = array(
            "h",
            [
                3000,
                9000,
                6000,
                12000,
                9000,
                15000,
            ],
        )

        expected = array("h", [9000]).tobytes()

        self.assertEqual(
            convert_pcm_48khz_stereo_to_16khz_mono(stereo_samples.tobytes()),
            expected,
        )
