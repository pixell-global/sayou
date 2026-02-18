"""ChromaDB RAG baseline adapter."""

from __future__ import annotations

import time
import uuid

from benchmarks.runner.adapter import (
    IngestMetrics,
    MemoryAdapter,
    RetrievalResult,
    SessionData,
)


class ChromaDBAdapter(MemoryAdapter):
    """ChromaDB with default sentence-transformer embeddings.

    Ingestion: Split messages into ~500-char chunks, embed and store.
    Retrieval: collection.query() with n_results=k.
    """

    name = "chromadb"

    def __init__(self):
        self._client = None
        self._collections: dict[str, object] = {}

    @classmethod
    def available(cls) -> bool:
        try:
            import chromadb  # noqa: F401
            return True
        except ImportError:
            return False

    async def setup(self) -> None:
        import chromadb
        self._client = chromadb.EphemeralClient()

    async def ingest_session(self, scenario_id: str, session: SessionData) -> IngestMetrics:
        start = time.perf_counter()

        collection = self._get_or_create_collection(scenario_id)
        chunks = _split_session_into_chunks(session)

        if chunks:
            ids = [str(uuid.uuid4()) for _ in chunks]
            documents = [c["text"] for c in chunks]
            metadatas = [{"session_id": c["session_id"], "role": c["role"]} for c in chunks]

            collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
            )

        elapsed_ms = (time.perf_counter() - start) * 1000
        storage_bytes = sum(len(c["text"].encode("utf-8")) for c in chunks)

        return IngestMetrics(time_ms=elapsed_ms, storage_bytes=storage_bytes)

    async def retrieve(self, scenario_id: str, query: str, k: int = 10) -> RetrievalResult:
        # Strip oracle format if present
        if query.startswith("EVIDENCE:"):
            parts = query.split("|QUERY:", 1)
            query = parts[1] if len(parts) > 1 else query

        start = time.perf_counter()

        collection = self._get_or_create_collection(scenario_id)

        # ChromaDB query is synchronous
        results = collection.query(
            query_texts=[query],
            n_results=min(k, collection.count()) if collection.count() > 0 else 1,
        )

        chunks = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        context = "\n\n---\n\n".join(chunks) if chunks else ""
        source_sessions = []
        seen = set()
        for meta in metadatas:
            sid = meta.get("session_id", "")
            if sid and sid not in seen:
                source_sessions.append(sid)
                seen.add(sid)

        elapsed_ms = (time.perf_counter() - start) * 1000

        return RetrievalResult(
            context=context,
            source_sessions=source_sessions,
            retrieval_time_ms=elapsed_ms,
            num_results=len(chunks),
            context_tokens=len(context) // 4,
        )

    async def reset(self, scenario_id: str) -> None:
        col_name = _collection_name(scenario_id)
        if col_name in self._collections:
            try:
                self._client.delete_collection(col_name)
            except Exception:
                pass
            del self._collections[col_name]

    async def teardown(self) -> None:
        # Clean up all collections
        for col_name in list(self._collections.keys()):
            try:
                self._client.delete_collection(col_name)
            except Exception:
                pass
        self._collections.clear()
        self._client = None

    def _get_or_create_collection(self, scenario_id: str):
        col_name = _collection_name(scenario_id)
        if col_name not in self._collections:
            self._collections[col_name] = self._client.get_or_create_collection(
                name=col_name
            )
        return self._collections[col_name]


def _collection_name(scenario_id: str) -> str:
    """Create a valid ChromaDB collection name from scenario ID."""
    # ChromaDB names: 3-63 chars, alphanumeric + underscores/hyphens
    return scenario_id.replace("/", "_")[:63]


def _split_session_into_chunks(
    session: SessionData,
    max_chunk_chars: int = 500,
) -> list[dict]:
    """Split a session's messages into ~500-char chunks.

    Each chunk includes session context and preserves message boundaries
    where possible.
    """
    chunks = []
    header = f"[Session {session.session_id}, Day {session.day or '?'}]"
    if session.request:
        header += f" Topic: {session.request}"

    for msg in session.messages:
        role_label = "User" if msg.role == "user" else "Assistant"
        text = f"{header}\n{role_label}: {msg.content}"

        if len(text) <= max_chunk_chars:
            chunks.append({
                "text": text,
                "session_id": session.session_id,
                "role": msg.role,
            })
        else:
            # Split long messages at paragraph/sentence boundaries
            paragraphs = text.split("\n\n")
            current = ""
            for para in paragraphs:
                if len(current) + len(para) + 2 > max_chunk_chars and current:
                    chunks.append({
                        "text": current.strip(),
                        "session_id": session.session_id,
                        "role": msg.role,
                    })
                    current = header + "\n" + para
                else:
                    current = current + "\n\n" + para if current else para

            if current.strip():
                chunks.append({
                    "text": current.strip(),
                    "session_id": session.session_id,
                    "role": msg.role,
                })

    return chunks
