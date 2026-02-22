"""Embedding service using sentence-transformers."""

from __future__ import annotations

import logging

from sentence_transformers import SentenceTransformer

from amon_hen.models import EnrichmentResult

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "all-MiniLM-L6-v2"


class EmbeddingService:
    """Generate embeddings from enrichment intelligence."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name
        self._model = SentenceTransformer(model_name)

    def embed_enrichment(self, result: EnrichmentResult) -> list[float]:
        """Embed the intelligence signal: summary + framing + claims."""
        text = f"{result.summary} {result.framing} {' '.join(result.claims)}"
        vector = self._model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def embed_query(self, query: str) -> list[float]:
        """Embed a search query."""
        vector = self._model.encode(query, normalize_embeddings=True)
        return vector.tolist()

    def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """Embed a batch of texts."""
        vectors = self._model.encode(
            texts, normalize_embeddings=True, batch_size=batch_size
        )
        return [v.tolist() for v in vectors]
