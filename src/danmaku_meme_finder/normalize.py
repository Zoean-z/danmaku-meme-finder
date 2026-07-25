"""Text normalization used only for matching and aggregation."""

from __future__ import annotations

import re
import unicodedata

_PUNCT_TRANSLATION = str.maketrans({
    "，": ",", "。": ".", "！": "!", "？": "?", "：": ":", "；": ";",
    "（": "(", "）": ")", "【": "[", "】": "]", "「": "\"", "」": "\"",
    "『": "\"", "』": "\"", "、": ",", "～": "~", "…": ".",
    "“": "\"", "”": "\"", "‘": "'", "’": "'", "《": "<", "》": ">",
})
_REPEATED_PUNCT = re.compile(r"([!?.~,])\1{3,}")
_REPEATED_CHAR = re.compile(r"(.)\1{5,}", re.DOTALL)


def normalize_text(text: str) -> str:
    """Return a comparison-friendly version while preserving the actual content."""
    normalized = unicodedata.normalize("NFKC", text).translate(_PUNCT_TRANSLATION)
    normalized = " ".join(normalized.strip().split()).lower()
    normalized = re.sub(r"\s+([,!.?;:)\]\}])", r"\1", normalized)
    normalized = re.sub(r"([([{])\s+", r"\1", normalized)
    # Limit each run of one punctuation mark and each run of any other character.
    normalized = _REPEATED_PUNCT.sub(lambda match: match.group(1) * 3, normalized)
    return _REPEATED_CHAR.sub(lambda match: match.group(1) * 5, normalized)


def has_meaningful_content(text: str) -> bool:
    """Require a letter or number, excluding punctuation- and emoji-only text."""
    return any(unicodedata.category(char)[0] in {"L", "N"} for char in text)
