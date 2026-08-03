"""Wraps whatever embedding model backs the vector store.

Start with a local sentence-transformers model for zero API cost while
you're iterating; swap for an API embedding model later if quality on
code-specific chunks needs it.
"""
from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import (  # type: ignore[import-not-found]
        SentenceTransformer,
    )

    return SentenceTransformer("BAAI/bge-small-en-v1.5")


def embed(texts: list[str]) -> list[list[float]]:
    return _model().encode(texts, normalize_embeddings=True).tolist()
