"""Tests for embedding service."""

from __future__ import annotations

import pytest

from amon_hen.enrichment.embeddings import EmbeddingService
from amon_hen.models import EnrichmentResult, Entity, EntityRole, EntityType
from amon_hen.storage.vectors import VECTOR_SIZE


@pytest.fixture(scope="module")
def embedder():
    """Shared embedding service (model loading is slow)."""
    return EmbeddingService()


def test_embed_enrichment_returns_correct_dim(embedder: EmbeddingService):
    result = EnrichmentResult(
        summary="Climate policy shifts in Europe",
        entities=[
            Entity(name="EU", type=EntityType.ORG, role=EntityRole.SUBJECT)
        ],
        claims=["EU pledges carbon neutrality by 2050"],
        framing="progress narrative",
        sentiment=0.3,
        topic_tags=["climate", "EU"],
    )
    vector = embedder.embed_enrichment(result)
    assert len(vector) == VECTOR_SIZE
    assert isinstance(vector[0], float)


def test_embed_enrichment_is_normalized(embedder: EmbeddingService):
    result = EnrichmentResult(
        summary="Test summary",
        entities=[],
        claims=["test claim"],
        framing="neutral",
        sentiment=0.0,
        topic_tags=[],
    )
    vector = embedder.embed_enrichment(result)
    norm = sum(x * x for x in vector) ** 0.5
    assert abs(norm - 1.0) < 0.01


def test_embed_query(embedder: EmbeddingService):
    vector = embedder.embed_query("climate change policy")
    assert len(vector) == VECTOR_SIZE


def test_embed_batch(embedder: EmbeddingService):
    texts = ["first text", "second text", "third text"]
    vectors = embedder.embed_batch(texts)
    assert len(vectors) == 3
    assert all(len(v) == VECTOR_SIZE for v in vectors)


def test_similar_content_has_higher_similarity(embedder: EmbeddingService):
    """Semantically similar texts should have higher cosine similarity."""
    v_climate = embedder.embed_query("global warming and climate change effects")
    v_climate2 = embedder.embed_query("rising temperatures and environmental impact")
    v_sports = embedder.embed_query("football championship final match results")

    # Cosine similarity (vectors are already normalized)
    sim_same_topic = sum(a * b for a, b in zip(v_climate, v_climate2))
    sim_diff_topic = sum(a * b for a, b in zip(v_climate, v_sports))

    assert sim_same_topic > sim_diff_topic
