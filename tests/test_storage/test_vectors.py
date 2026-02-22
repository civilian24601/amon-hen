"""Tests for VectorStore (in-memory Qdrant)."""

from __future__ import annotations

import random
from uuid import uuid4

import pytest

from amon_hen.config import Settings
from amon_hen.storage.vectors import COLLECTION_NAME, VECTOR_SIZE, VectorStore


def _uid() -> str:
    return str(uuid4())


def _random_vector(dim: int = VECTOR_SIZE) -> list[float]:
    """Generate a random unit-ish vector."""
    vec = [random.gauss(0, 1) for _ in range(dim)]
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm for x in vec]


def _biased_vector(dim: int = VECTOR_SIZE, bias: float = 1.0) -> list[float]:
    """Generate a vector biased toward positive values — will be similar to other biased vectors."""
    vec = [abs(random.gauss(0, 1)) + bias for _ in range(dim)]
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm for x in vec]


# ─── Collection ───


def test_collection_created(vector_store: VectorStore):
    """Collection exists after init."""
    collections = [
        c.name for c in vector_store.client.get_collections().collections
    ]
    assert COLLECTION_NAME in collections


def test_collection_info(vector_store: VectorStore):
    info = vector_store.get_collection_info()
    assert info["name"] == COLLECTION_NAME
    assert info["points_count"] == 0


# ─── Upsert + Retrieve ───


def test_upsert_single_item(vector_store: VectorStore):
    pid = _uid()
    vec = _random_vector()
    vector_store.upsert_item(pid, vec, {"source_type": "rss", "title": "Test"})
    info = vector_store.get_collection_info()
    assert info["points_count"] == 1


def test_upsert_multiple_items(vector_store: VectorStore):
    for _ in range(5):
        vector_store.upsert_item(
            _uid(), _random_vector(), {"source_type": "rss"}
        )
    info = vector_store.get_collection_info()
    assert info["points_count"] == 5


def test_upsert_same_id_overwrites(vector_store: VectorStore):
    pid = _uid()
    vector_store.upsert_item(pid, _random_vector(), {"title": "v1"})
    vector_store.upsert_item(pid, _random_vector(), {"title": "v2"})
    info = vector_store.get_collection_info()
    assert info["points_count"] == 1


# ─── Search ───


def test_search_returns_results(vector_store: VectorStore):
    vecs = [_random_vector() for _ in range(10)]
    for v in vecs:
        vector_store.upsert_item(_uid(), v, {"source_type": "rss"})
    results = vector_store.search(vecs[0], limit=5)
    assert len(results) == 5
    # First result should be the exact match (highest score)
    assert results[0].score > 0.9


def test_search_empty_collection(vector_store: VectorStore):
    results = vector_store.search(_random_vector(), limit=5)
    assert results == []


def test_search_limit(vector_store: VectorStore):
    for _ in range(20):
        vector_store.upsert_item(
            _uid(), _random_vector(), {"source_type": "rss"}
        )
    results = vector_store.search(_random_vector(), limit=3)
    assert len(results) == 3


def test_search_source_type_filter(vector_store: VectorStore):
    for _ in range(5):
        vector_store.upsert_item(
            _uid(), _random_vector(), {"source_type": "rss"}
        )
    for _ in range(5):
        vector_store.upsert_item(
            _uid(), _random_vector(), {"source_type": "gdelt"}
        )
    results = vector_store.search(
        _random_vector(), limit=20, source_type="rss"
    )
    assert all(r.payload["source_type"] == "rss" for r in results)
    assert len(results) == 5


def test_search_since_filter(vector_store: VectorStore):
    vector_store.upsert_item(
        _uid(),
        _random_vector(),
        {"source_type": "rss", "published_at": "2024-01-01T00:00:00"},
    )
    vector_store.upsert_item(
        _uid(),
        _random_vector(),
        {"source_type": "rss", "published_at": "2025-06-01T00:00:00"},
    )
    results = vector_store.search(
        _random_vector(), limit=20, since="2025-01-01T00:00:00"
    )
    assert len(results) == 1
    assert results[0].payload["published_at"] == "2025-06-01T00:00:00"


# ─── Get All Vectors (scroll) ───


def test_get_all_vectors(vector_store: VectorStore):
    expected_ids = []
    for _ in range(15):
        pid = _uid()
        expected_ids.append(pid)
        vector_store.upsert_item(pid, _random_vector(), {"source_type": "rss"})
    ids, vectors = vector_store.get_all_vectors()
    assert len(ids) == 15
    assert len(vectors) == 15
    assert set(ids) == set(expected_ids)
    assert all(len(v) == VECTOR_SIZE for v in vectors)


def test_get_all_vectors_empty(vector_store: VectorStore):
    ids, vectors = vector_store.get_all_vectors()
    assert ids == []
    assert vectors == []


def test_get_all_vectors_since_filter(vector_store: VectorStore):
    vector_store.upsert_item(
        _uid(),
        _random_vector(),
        {"published_at": "2024-01-01T00:00:00"},
    )
    pid_new = _uid()
    vector_store.upsert_item(
        pid_new,
        _random_vector(),
        {"published_at": "2025-06-01T00:00:00"},
    )
    ids, vectors = vector_store.get_all_vectors(since="2025-01-01T00:00:00")
    assert len(ids) == 1
    assert ids[0] == pid_new


# ─── Get Vectors by IDs ───


def test_get_vectors_by_ids(vector_store: VectorStore):
    pids = [_uid() for _ in range(3)]
    vecs = [_random_vector() for _ in range(3)]
    for pid, vec in zip(pids, vecs):
        vector_store.upsert_item(pid, vec, {"source_type": "rss"})
    result = vector_store.get_vectors_by_ids(pids[:2])
    assert len(result) == 2
    assert set(result.keys()) == set(pids[:2])
    assert all(len(v) == VECTOR_SIZE for v in result.values())


def test_get_vectors_by_ids_empty_list(vector_store: VectorStore):
    assert vector_store.get_vectors_by_ids([]) == {}


# ─── Delete ───


def test_delete_points(vector_store: VectorStore):
    pids = [_uid() for _ in range(5)]
    for pid in pids:
        vector_store.upsert_item(pid, _random_vector(), {"source_type": "rss"})
    assert vector_store.get_collection_info()["points_count"] == 5
    vector_store.delete_points(pids[:3])
    info = vector_store.get_collection_info()
    assert info["points_count"] == 2


def test_delete_empty_list(vector_store: VectorStore):
    """delete_points with empty list should not error."""
    vector_store.delete_points([])


# ─── Semantic similarity sanity ───


def test_similar_vectors_rank_higher(vector_store: VectorStore):
    """Vectors biased the same way should score higher than random ones."""
    # Insert a target biased vector
    target = _biased_vector(bias=2.0)
    target_id = _uid()
    vector_store.upsert_item(target_id, target, {"label": "target"})

    # Insert a similar biased vector
    similar = _biased_vector(bias=2.0)
    similar_id = _uid()
    vector_store.upsert_item(similar_id, similar, {"label": "similar"})

    # Insert some random vectors
    for _ in range(10):
        vector_store.upsert_item(_uid(), _random_vector(), {"label": "random"})

    results = vector_store.search(target, limit=3)
    top_ids = [str(r.id) for r in results]
    # The exact match should be first
    assert top_ids[0] == target_id
    # The similar biased vector should be in top 3
    assert similar_id in top_ids
