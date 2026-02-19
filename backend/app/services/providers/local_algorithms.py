from __future__ import annotations

import hashlib
import math
import re
from collections import Counter


def hash_embedding(text: str, dim: int = 1536) -> list[float]:
    if not text:
        return [0.0] * dim

    vec = [0.0] * dim
    normalized = text.lower()
    for token in re.findall(r"\w+", normalized):
        digest = hashlib.sha256(token.encode('utf-8')).digest()
        for idx, byte in enumerate(digest):
            pos = (idx * 31 + byte) % dim
            vec[pos] += (byte / 255.0) - 0.5

    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def token_overlap_score(query: str, doc: str) -> float:
    q_tokens = re.findall(r"\w+", query.lower())
    d_tokens = re.findall(r"\w+", doc.lower())
    if not q_tokens or not d_tokens:
        return 0.0

    q_counter = Counter(q_tokens)
    d_counter = Counter(d_tokens)
    numerator = sum(min(q_counter[token], d_counter[token]) for token in q_counter)
    denominator = max(len(set(q_tokens)), 1)
    return numerator / denominator
