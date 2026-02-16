"""Embedding providers and vector math for semantic search.

Provider abstraction with Protocol interface. NullEmbeddingProvider as fallback.
Pure Python cosine similarity — no numpy dependency.
"""

from __future__ import annotations

import hashlib
import math
import struct
from typing import Protocol


class EmbeddingProvider(Protocol):
    """Protocol for embedding providers."""

    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    async def embed(self, text: str) -> list[float]: ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class NullEmbeddingProvider:
    """Fallback when no embedding provider is configured. All operations return empty."""

    @property
    def provider_name(self) -> str:
        return ""

    @property
    def model_name(self) -> str:
        return ""

    @property
    def dimensions(self) -> int:
        return 0

    async def embed(self, text: str) -> list[float]:
        return []

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[] for _ in texts]


class OpenAIEmbeddingProvider:
    """OpenAI embedding provider using text-embedding-3-small by default."""

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
    ):
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._client = None

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=self._api_key)
            except ImportError:
                raise ImportError(
                    "openai package required for OpenAI embeddings. "
                    "Install with: pip install sayou[ai]"
                )
        return self._client

    async def embed(self, text: str) -> list[float]:
        client = self._get_client()
        response = await client.embeddings.create(
            model=self._model,
            input=text,
            dimensions=self._dimensions,
        )
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._get_client()
        response = await client.embeddings.create(
            model=self._model,
            input=texts,
            dimensions=self._dimensions,
        )
        return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]


def pack_embedding(embedding: list[float]) -> bytes:
    """Pack a float list into bytes (float32 format)."""
    return struct.pack(f"{len(embedding)}f", *embedding)


def unpack_embedding(data: bytes) -> list[float]:
    """Unpack bytes back into a float list."""
    count = len(data) // 4  # 4 bytes per float32
    return list(struct.unpack(f"{count}f", data))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors. Pure Python, no numpy."""
    if not a or not b or len(a) != len(b):
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (norm_a * norm_b)


def content_hash(text: str) -> str:
    """SHA256 hash of text content for dedup."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prepare_embedding_input(frontmatter: dict | None, body: str) -> str:
    """Prepare text for embedding: prepend frontmatter keys to body.

    This makes similarity metadata-aware (e.g., two files about "setup"
    with tag "tutorial" will be more similar than without tags).
    """
    parts = []
    if frontmatter:
        for key, value in frontmatter.items():
            if isinstance(value, list):
                parts.append(f"{key}: {', '.join(str(v) for v in value)}")
            elif value is not None:
                parts.append(f"{key}: {value}")
    if body:
        parts.append(body)
    return "\n".join(parts)


def get_embedding_provider(
    provider: str = "",
    api_key: str = "",
    model: str = "",
) -> EmbeddingProvider:
    """Factory: return the configured embedding provider or NullProvider."""
    if not provider or not api_key:
        return NullEmbeddingProvider()

    if provider == "openai":
        return OpenAIEmbeddingProvider(
            api_key=api_key,
            model=model or "text-embedding-3-small",
        )

    return NullEmbeddingProvider()
