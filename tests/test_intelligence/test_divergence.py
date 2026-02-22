"""Tests for divergence detection."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from amon_hen.config import Settings
from amon_hen.intelligence.divergence import DivergenceDetector
from amon_hen.models import ClusterStatus, NarrativeCluster, SourceType
from amon_hen.storage.sqlite import SQLiteStore
from amon_hen.storage.vectors import VECTOR_SIZE, VectorStore
from tests.conftest import make_enriched_item


def _uid():
    return str(uuid4())


@pytest.fixture
def stores(tmp_path):
    sqlite = SQLiteStore(tmp_path / "test.db")
    settings = Settings(qdrant_mode="memory")
    return sqlite, VectorStore(settings)


def test_divergence_detected_between_sources(stores):
    """Sources with very different vectors in same cluster should flag divergence."""
    sqlite, vectors = stores
    now = datetime.now(timezone.utc)
    cluster_id = _uid()

    # RSS items with positive-biased vectors
    for _ in range(5):
        item_id = _uid()
        vec = [1.0 / (VECTOR_SIZE ** 0.5)] * VECTOR_SIZE
        item = make_enriched_item(
            id=item_id,
            embedding_id=item_id,
            source_type=SourceType.RSS,
            cluster_id=cluster_id,
            cluster_label="Test Cluster",
        )
        sqlite.insert_item(item)
        vectors.upsert_item(item_id, vec, {"source_type": "rss"})

    # GDELT items with negative-biased vectors (very different direction)
    for _ in range(5):
        item_id = _uid()
        vec = [-1.0 / (VECTOR_SIZE ** 0.5)] * VECTOR_SIZE
        item = make_enriched_item(
            id=item_id,
            embedding_id=item_id,
            source_type=SourceType.GDELT,
            cluster_id=cluster_id,
            cluster_label="Test Cluster",
        )
        sqlite.insert_item(item)
        vectors.upsert_item(item_id, vec, {"source_type": "gdelt"})

    cluster = NarrativeCluster(
        id=cluster_id,
        label="Test Cluster",
        summary="Test",
        item_count=10,
        first_seen=now,
        last_updated=now,
        centroid=[0.0] * VECTOR_SIZE,
        status=ClusterStatus.ACTIVE,
    )

    detector = DivergenceDetector(threshold=0.3)
    divergences = detector.detect([cluster], sqlite, vectors)

    assert len(divergences) >= 1
    assert divergences[0]["cluster_id"] == cluster_id
    assert divergences[0]["cosine_distance"] > 0.3


def test_no_divergence_with_similar_vectors(stores):
    """Sources with similar vectors shouldn't flag divergence."""
    sqlite, vectors = stores
    now = datetime.now(timezone.utc)
    cluster_id = _uid()

    base_vec = [1.0 / (VECTOR_SIZE ** 0.5)] * VECTOR_SIZE

    for source in [SourceType.RSS, SourceType.GDELT]:
        for _ in range(5):
            item_id = _uid()
            # Add small noise to keep them similar
            vec = [v + random.gauss(0, 0.01) for v in base_vec]
            norm = sum(x * x for x in vec) ** 0.5
            vec = [x / norm for x in vec]
            item = make_enriched_item(
                id=item_id,
                embedding_id=item_id,
                source_type=source,
                cluster_id=cluster_id,
                cluster_label="Test",
            )
            sqlite.insert_item(item)
            vectors.upsert_item(item_id, vec, {"source_type": source.value})

    cluster = NarrativeCluster(
        id=cluster_id, label="Test", summary="Test", item_count=10,
        first_seen=now, last_updated=now, centroid=base_vec,
        status=ClusterStatus.ACTIVE,
    )

    detector = DivergenceDetector(threshold=0.3)
    divergences = detector.detect([cluster], sqlite, vectors)
    assert len(divergences) == 0


def test_divergence_skips_single_source(stores):
    """Clusters with only one source type can't diverge."""
    sqlite, vectors = stores
    now = datetime.now(timezone.utc)
    cluster_id = _uid()

    for _ in range(5):
        item_id = _uid()
        vec = [1.0 / (VECTOR_SIZE ** 0.5)] * VECTOR_SIZE
        item = make_enriched_item(
            id=item_id, embedding_id=item_id,
            source_type=SourceType.RSS,
            cluster_id=cluster_id, cluster_label="Test",
        )
        sqlite.insert_item(item)
        vectors.upsert_item(item_id, vec, {"source_type": "rss"})

    cluster = NarrativeCluster(
        id=cluster_id, label="Test", summary="Test", item_count=5,
        first_seen=now, last_updated=now, centroid=[0.0] * VECTOR_SIZE,
        status=ClusterStatus.ACTIVE,
    )

    detector = DivergenceDetector(threshold=0.3)
    divergences = detector.detect([cluster], sqlite, vectors)
    assert len(divergences) == 0
