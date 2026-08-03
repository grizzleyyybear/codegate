"""Retrieval service — the RAG half of the JD's "RAG pipelines, vector
stores, and knowledge bases" bullet.

/index    walks a target repo, chunks it, embeds it, writes to pgvector
/retrieve given a query, returns the top-k most relevant chunks
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from shared.otel_setup import setup_otel
from shared.schemas import RetrievedChunk

from .indexer import index_repository
from .retriever import retrieve_chunks
from .vector_store import ensure_schema

setup_otel("codegate-retrieval")


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_schema()
    yield


app = FastAPI(title="Codegate Retrieval", lifespan=lifespan)


class IndexRequest(BaseModel):
    repo: str
    repo_path: str  # local checkout path or git URL


class RetrieveRequest(BaseModel):
    repo: str
    query: str
    top_k: int = 8


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/index")
async def index(req: IndexRequest):
    chunks_written = await index_repository(req.repo, req.repo_path)
    return {"repo": req.repo, "chunks_indexed": chunks_written}


@app.post("/retrieve")
async def retrieve(req: RetrieveRequest) -> dict[str, list[RetrievedChunk]]:
    chunks = await retrieve_chunks(req.repo, req.query, req.top_k)
    return {"chunks": chunks}
