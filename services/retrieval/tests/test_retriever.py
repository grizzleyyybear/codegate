import asyncio

from app import retriever


def test_retrieve_chunks_builds_results(monkeypatch):
    monkeypatch.setattr(retriever, "embed", lambda texts: [[0.1, 0.2]])
    monkeypatch.setattr(
        retriever,
        "similarity_search",
        lambda repo, emb, top_k: [("a.py", "code", 0.9), ("b.py", "more", 0.7)],
    )
    chunks = asyncio.run(retriever.retrieve_chunks("r", "query", 5))
    assert len(chunks) == 2
    assert chunks[0].file_path == "a.py"
    assert chunks[0].content == "code"
    assert chunks[0].similarity == 0.9


def test_retrieve_chunks_passes_embedding_and_top_k(monkeypatch):
    captured = {}

    def fake_embed(texts):
        captured["texts"] = texts
        return [[0.5]]

    def fake_search(repo, emb, top_k):
        captured["emb"] = emb
        captured["top_k"] = top_k
        return []

    monkeypatch.setattr(retriever, "embed", fake_embed)
    monkeypatch.setattr(retriever, "similarity_search", fake_search)
    asyncio.run(retriever.retrieve_chunks("repo-x", "query-y", 3))
    assert captured["texts"] == ["query-y"]
    assert captured["emb"] == [0.5]
    assert captured["top_k"] == 3
