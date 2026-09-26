from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter


TOKEN_RE = re.compile(r"[^\W\d_]{2,}", re.UNICODE)
RO_SUFFIXES = (
    "iilor", "urilor", "elor", "ilor", "ului", "itate", "ități", "ație", "ații",
    "mente", "ment", "elor", "urile", "ului", "ul", "le", "lor", "ii", "i", "e", "a",
)


def normalize_token(token: str) -> str:
    value = unicodedata.normalize("NFC", token.casefold())
    for suffix in RO_SUFFIXES:
        if len(value) - len(suffix) >= 4 and value.endswith(suffix):
            return value[: -len(suffix)]
    return value


def tokenize(text: str) -> list[str]:
    return [normalize_token(item) for item in TOKEN_RE.findall(text)]


def term_index(term: str) -> int:
    return int.from_bytes(hashlib.blake2s(term.encode("utf-8"), digest_size=4).digest(), "big")


def bm25_sparse(text: str) -> tuple[list[int], list[float]]:
    """Stable BM25 term-frequency vector; Qdrant applies collection IDF."""
    counts = Counter(tokenize(text))
    length = max(1, sum(counts.values()))
    k1, b, nominal_length = 1.2, 0.75, 120.0
    pairs = []
    for term, frequency in counts.items():
        weight = frequency * (k1 + 1) / (frequency + k1 * (1 - b + b * length / nominal_length))
        pairs.append((term_index(term), float(weight)))
    pairs.sort()
    return [p[0] for p in pairs], [p[1] for p in pairs]

