"""Shared Chinese lexical normalization for BM25; vectors are optional."""

import hashlib
import re
import sqlite3
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path
from typing import Any

from app.values import digest


@lru_cache(maxsize=1)
def _lexical_tokenizer() -> Any:
    import jieba  # type: ignore[import-untyped]

    return jieba.Tokenizer()


def lexical_version() -> str:
    import jieba

    dictionary = Path(jieba.__file__).with_name("dict.txt")
    return digest(
        [
            "poc-lexical-v1",
            version("jieba"),
            hashlib.sha256(dictionary.read_bytes()).hexdigest(),
            sqlite3.sqlite_version,
        ]
    )


def lexical_terms(text: str) -> tuple[str, ...]:
    return tuple(
        word
        for word in _lexical_tokenizer().cut(text.casefold(), HMM=False)
        if re.search(r"\w", word)
    )
