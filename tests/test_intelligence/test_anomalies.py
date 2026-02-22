"""Tests for anomaly detection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from amon_hen.intelligence.anomalies import AnomalyDetector
from amon_hen.models import ClusterStatus, NarrativeCluster, SourceType
from amon_hen.storage.sqlite import SQLiteStore
from amon_hen.storage.vectors import VECTOR_SIZE
from tests.conftest import make_enriched_item


def _uid():
    return str(uuid4())


@pytest.fixture
def sqlite(tmp_path):
    return SQLiteStore(tmp_path / "test.db")


def _make_cluster(cluster_id: str) -> NarrativeCluster:
    now = datetime.now(timezone.utc)
    return NarrativeCluster(
        id=cluster_id,
        label="Test Cluster",
        summary="Test",
        item_count=10,
        first_seen=now,
        last_updated=now,
        centroid=[0.0] * 10,
        status=ClusterStatus.ACTIVE,
    )


def test_volume_spike_detected(sqlite: SQLiteStore):
    """Volume spike: many items in 6h vs low weekly average."""
    now = datetime.now(timezone.utc)
    cluster_id = _uid()

    # 20 items in last 3 hours (high recent activity)
    for i in range(20):
        sqlite.insert_item(make_enriched_item(
            published_at=now - timedelta(hours=i * 0.1),
            cluster_id=cluster_id,
            cluster_label="Test",
        ))

    # 5 items from days ago (low baseline)
    for i in range(5):
        sqlite.insert_item(make_enriched_item(
            published_at=now - timedelta(days=3 + i),
            cluster_id=cluster_id,
            cluster_label="Test",
        ))

    detector = AnomalyDetector(sqlite)
    spikes = detector.detect_volume_spikes([_make_cluster(cluster_id)])

    assert len(spikes) >= 1
    assert spikes[0]["type"] == "volume_spike"


def test_no_volume_spike_with_steady_rate(sqlite: SQLiteStore):
    """No spike when rate is consistent."""
    now = datetime.now(timezone.utc)
    cluster_id = _uid()

    # Evenly spread items over 7 days
    for i in range(168):  # 1 per hour for 7 days
        sqlite.insert_item(make_enriched_item(
            published_at=now - timedelta(hours=i),
            cluster_id=cluster_id,
            cluster_label="Test",
        ))

    detector = AnomalyDetector(sqlite)
    spikes = detector.detect_volume_spikes([_make_cluster(cluster_id)])

    assert len(spikes) == 0


def test_sentiment_shift_detected(sqlite: SQLiteStore):
    """Detect sentiment shift > 0.5 in 24h."""
    now = datetime.now(timezone.utc)
    cluster_id = _uid()

    # Recent items: very positive
    for i in range(5):
        sqlite.insert_item(make_enriched_item(
            published_at=now - timedelta(hours=i),
            sentiment=0.8,
            cluster_id=cluster_id,
            cluster_label="Test",
        ))

    # Older items (24-48h ago): very negative
    for i in range(5):
        sqlite.insert_item(make_enriched_item(
            published_at=now - timedelta(hours=30 + i),
            sentiment=-0.5,
            cluster_id=cluster_id,
            cluster_label="Test",
        ))

    detector = AnomalyDetector(sqlite)
    shifts = detector.detect_sentiment_shifts([_make_cluster(cluster_id)])

    assert len(shifts) >= 1
    assert shifts[0]["type"] == "sentiment_shift"
    assert shifts[0]["shift"] > 0.5


def test_entity_surge_detected(sqlite: SQLiteStore):
    """Detect entity appearing in >10 items in 6h."""
    now = datetime.now(timezone.utc)

    from amon_hen.models import Entity, EntityRole, EntityType

    surge_entity = Entity(
        name="Breaking Entity", type=EntityType.ORG, role=EntityRole.SUBJECT
    )

    for i in range(15):
        sqlite.insert_item(make_enriched_item(
            published_at=now - timedelta(hours=i * 0.3),
            entities=[surge_entity],
        ))

    detector = AnomalyDetector(sqlite)
    surges = detector.detect_entity_surges()

    assert len(surges) >= 1
    assert surges[0]["type"] == "entity_surge"
    assert surges[0]["entity_name"] == "Breaking Entity"
