"""Tests for the REST API."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from amon_hen.config import Settings
from amon_hen.models import DailyDigest
from amon_hen.storage.sqlite import SQLiteStore
from amon_hen.storage.vectors import VectorStore
from tests.conftest import make_cluster, make_enriched_item


@pytest.fixture
def app(tmp_path):
    """Create a test app with ephemeral storage."""
    settings = Settings(
        sqlite_path=tmp_path / "test.db",
        qdrant_mode="memory",
    )
    # Patch get_settings so the server uses our test settings
    with patch("amon_hen.api.server.get_settings", return_value=settings):
        # Also patch scheduler to not start
        with patch("amon_hen.scheduler.PipelineScheduler", side_effect=Exception("skip")):
            from amon_hen.api.server import create_app
            yield create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def seeded_app(tmp_path):
    """Create a test app seeded with data."""
    settings = Settings(
        sqlite_path=tmp_path / "test.db",
        qdrant_mode="memory",
    )
    with patch("amon_hen.api.server.get_settings", return_value=settings):
        with patch("amon_hen.scheduler.PipelineScheduler", side_effect=Exception("skip")):
            from amon_hen.api.server import create_app
            app = create_app()

    # Seed data
    from amon_hen.storage import get_stores
    sqlite, vectors = get_stores(settings)

    for _ in range(5):
        item = make_enriched_item(cluster_id="c1", cluster_label="Test Cluster")
        sqlite.insert_item(item)

    cluster = make_cluster(id="c1", label="Test Cluster", item_count=5)
    sqlite.upsert_cluster(cluster)

    digest = DailyDigest(
        generated_at=datetime.now(timezone.utc),
        content="Test digest content.",
        cluster_count=1,
        item_count=5,
        model="test-model",
    )
    sqlite.insert_digest(digest)

    return app


@pytest.fixture
def seeded_client(seeded_app):
    return TestClient(seeded_app)


# ─── Endpoint tests ───


def test_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "items_count" in data
    assert "clusters_counts" in data or "clusters_count" in data or "clusters_count" in str(data)


def test_clusters_empty(client):
    resp = client.get("/api/clusters")
    assert resp.status_code == 200
    assert resp.json() == []


def test_clusters_with_data(seeded_client):
    resp = seeded_client.get("/api/clusters")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["label"] == "Test Cluster"


def test_cluster_detail(seeded_client):
    resp = seeded_client.get("/api/clusters/c1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "c1"
    assert data["label"] == "Test Cluster"
    assert "items" in data


def test_items_endpoint(seeded_client):
    resp = seeded_client.get("/api/items")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 5


def test_items_with_limit(seeded_client):
    resp = seeded_client.get("/api/items?limit=2")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_digest_endpoint(seeded_client):
    resp = seeded_client.get("/api/digest/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "Test digest content."


def test_digest_empty(client):
    resp = client.get("/api/digest/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert "message" in data
