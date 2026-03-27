from __future__ import annotations

import re

JAPANESE_TEXT_PATTERN = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")
LATIN_TEXT_PATTERN = re.compile(r"[A-Za-z]")
WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_transcript(text: str) -> str:
    normalized = WHITESPACE_PATTERN.sub(" ", text).strip()
    if not normalized:
        return ""

    if JAPANESE_TEXT_PATTERN.search(normalized) and not LATIN_TEXT_PATTERN.search(
        normalized
    ):
        return normalized.replace(" ", "")

    return normalized


def join_transcript_parts(parts: list[str]) -> str:
    return normalize_transcript(" ".join(part for part in parts if part))
