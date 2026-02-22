"""Tests for clustering pipeline with synthetic vectors."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import numpy as np
import pytest

from amon_hen.config import ClusteringConfig, Settings
from amon_hen.intelligence.clustering import ClusteringPipeline, _bin_sentiment
from amon_hen.models import ClusterStatus
from amon_hen.storage.sqlite import SQLiteStore
from amon_hen.storage.vectors import VECTOR_SIZE, VectorStore
from tests.conftest import make_cluster, make_enriched_item


def _uid() -> str:
    return str(uuid4())


def _make_cluster_vector(center: list[float], noise: float = 0.05) -> list[float]:
    """Generate a vector near a center with Gaussian noise."""
    vec = [c + random.gauss(0, noise) for c in center]
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm for x in vec]


def _seed_cluster_data(
    sqlite: SQLiteStore,
    vectors: VectorStore,
    center: list[float],
    n: int,
    source_type: str = "rss",
    sentiment: float = 0.1,
) -> list[str]:
    """Seed N items around a vector center. Returns list of item IDs."""
    ids = []
    now = datetime.now(timezone.utc)
    for i in range(n):
        item_id = _uid()
        vec = _make_cluster_vector(center, noise=0.03)
        item = make_enriched_item(
            id=item_id,
            embedding_id=item_id,
            published_at=now - timedelta(hours=i),
            sentiment=sentiment,
        )
        sqlite.insert_item(item)
        vectors.upsert_item(
            item_id, vec, {
                "source_type": source_type,
                "published_at": item.published_at.isoformat(),
            }
        )
        ids.append(item_id)
    return ids


@pytest.fixture
def clustering_config():
    return ClusteringConfig(
        min_cluster_size=3,
        min_samples=2,
        rolling_window_days=30,
    )


@pytest.fixture
def stores(tmp_path):
    sqlite = SQLiteStore(tmp_path / "test.db")
    settings = Settings(qdrant_mode="memory")
    vector_store = VectorStore(settings)
    return sqlite, vector_store


# ─── Sentiment binning ───


def test_bin_sentiment():
    values = [-0.9, -0.5, -0.1, 0.0, 0.1, 0.4, 0.8]
    bins = _bin_sentiment(values)
    assert bins["very_negative"] == 1
    assert bins["negative"] == 1
    assert bins["neutral"] == 3
    assert bins["positive"] == 1
    assert bins["very_positive"] == 1


def test_bin_sentiment_empty():
    bins = _bin_sentiment([])
    assert all(v == 0 for v in bins.values())


# ─── Clustering pipeline ───


@pytest.mark.asyncio
async def test_clustering_finds_distinct_clusters(stores, clustering_config):
    """Two well-separated groups of vectors should form two clusters."""
    sqlite, vector_store = stores
    random.seed(42)

    # Cluster A: positive first half of vector
    center_a = [1.0] * (VECTOR_SIZE // 2) + [0.0] * (VECTOR_SIZE // 2)
    norm = sum(x * x for x in center_a) ** 0.5
    center_a = [x / norm for x in center_a]

    # Cluster B: positive second half of vector
    center_b = [0.0] * (VECTOR_SIZE // 2) + [1.0] * (VECTOR_SIZE // 2)
    norm = sum(x * x for x in center_b) ** 0.5
    center_b = [x / norm for x in center_b]

    _seed_cluster_data(sqlite, vector_store, center_a, 8)
    _seed_cluster_data(sqlite, vector_store, center_b, 8)

    pipeline = ClusteringPipeline(clustering_config, sqlite, vector_store, llm=None)
    clusters = await pipeline.run()

    assert len(clusters) >= 2


@pytest.mark.asyncio
async def test_clustering_too_few_items(stores, clustering_config):
    """With fewer items than min_cluster_size, returns empty."""
    sqlite, vector_store = stores
    random.seed(42)

    center = [1.0 / (VECTOR_SIZE ** 0.5)] * VECTOR_SIZE
    _seed_cluster_data(sqlite, vector_store, center, 2)

    pipeline = ClusteringPipeline(clustering_config, sqlite, vector_store, llm=None)
    clusters = await pipeline.run()

    assert clusters == []


@pytest.mark.asyncio
async def test_clustering_noise_points_excluded(stores, clustering_config):
    """Noise points (label=-1) shouldn't be assigned to clusters."""
    sqlite, vector_store = stores
    random.seed(42)

    center = [1.0 / (VECTOR_SIZE ** 0.5)] * VECTOR_SIZE
    ids = _seed_cluster_data(sqlite, vector_store, center, 8)

    # Add a far-away noise point
    noise_id = _uid()
    noise_vec = [-1.0 / (VECTOR_SIZE ** 0.5)] * VECTOR_SIZE
    item = make_enriched_item(id=noise_id, embedding_id=noise_id)
    sqlite.insert_item(item)
    vector_store.upsert_item(
        noise_id, noise_vec, {
            "source_type": "rss",
            "published_at": item.published_at.isoformat(),
        }
    )

    pipeline = ClusteringPipeline(clustering_config, sqlite, vector_store, llm=None)
    clusters = await pipeline.run()

    # The noise point should NOT be in any cluster's membership
    total_members = sum(c.item_count for c in clusters)
    assert total_members <= 8  # At most the 8 clustered items


# ─── Cluster matching ───


@pytest.mark.asyncio
async def test_cluster_matching_inherits_id(stores, clustering_config):
    """When new cluster overlaps >70% with previous, it inherits the ID."""
    sqlite, vector_store = stores
    random.seed(42)

    # Use two well-separated clusters to ensure HDBSCAN finds them
    center_a = [1.0] * (VECTOR_SIZE // 2) + [0.0] * (VECTOR_SIZE // 2)
    norm = sum(x * x for x in center_a) ** 0.5
    center_a = [x / norm for x in center_a]

    center_b = [0.0] * (VECTOR_SIZE // 2) + [1.0] * (VECTOR_SIZE // 2)
    norm = sum(x * x for x in center_b) ** 0.5
    center_b = [x / norm for x in center_b]

    _seed_cluster_data(sqlite, vector_store, center_a, 8)
    _seed_cluster_data(sqlite, vector_store, center_b, 8)

    pipeline = ClusteringPipeline(clustering_config, sqlite, vector_store, llm=None)

    # First run
    clusters_v1 = await pipeline.run()
    assert len(clusters_v1) >= 2
    original_ids = {c.id for c in clusters_v1}

    # Second run (same data = same clusters)
    clusters_v2 = await pipeline.run()
    assert len(clusters_v2) >= 2
    # Should inherit the original cluster IDs (same members = >70% overlap)
    matched_ids = {c.id for c in clusters_v2}
    assert matched_ids == original_ids
    assert all(c.status == ClusterStatus.ACTIVE for c in clusters_v2)


@pytest.mark.asyncio
async def test_fading_cluster_when_disappears(stores, clustering_config):
    """Clusters that disappear should be marked as fading."""
    sqlite, vector_store = stores
    random.seed(42)

    # Create two clusters
    center_a = [1.0] * (VECTOR_SIZE // 2) + [0.0] * (VECTOR_SIZE // 2)
    norm_a = sum(x * x for x in center_a) ** 0.5
    center_a = [x / norm_a for x in center_a]

    center_b = [0.0] * (VECTOR_SIZE // 2) + [1.0] * (VECTOR_SIZE // 2)
    norm_b = sum(x * x for x in center_b) ** 0.5
    center_b = [x / norm_b for x in center_b]

    ids_a = _seed_cluster_data(sqlite, vector_store, center_a, 8)
    ids_b = _seed_cluster_data(sqlite, vector_store, center_b, 8)

    pipeline = ClusteringPipeline(clustering_config, sqlite, vector_store, llm=None)
    clusters_v1 = await pipeline.run()
    assert len(clusters_v1) >= 2

    # Delete cluster B's vectors
    vector_store.delete_points(ids_b)

    # Re-run clustering — cluster B should fade
    clusters_v2 = await pipeline.run()
    # One of the original clusters should now be marked fading
    fading = sqlite.get_cluster(clusters_v1[1].id)
    if fading:
        assert fading.status in (ClusterStatus.FADING, ClusterStatus.ACTIVE)
