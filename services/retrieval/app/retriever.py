from __future__ import annotations

from shared.schemas import RetrievedChunk

from .embedder import embed
from .vector_store import similarity_search


async def retrieve_chunks(repo: str, query: str, top_k: int) -> list[RetrievedChunk]:
    query_embedding = embed([query])[0]
    rows = similarity_search(repo, query_embedding, top_k)
    return [
        RetrievedChunk(file_path=fp, content=content, similarity=sim)
        for fp, content, sim in rows
    ]
