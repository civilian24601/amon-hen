"""Tests for SQLiteStore."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from amon_hen.models import (
    ClusterStatus,
    DailyDigest,
    SourceStatus,
    SourceType,
)
from amon_hen.storage.sqlite import SQLiteStore
from tests.conftest import (
    make_cluster,
    make_cost_entry,
    make_enriched_item,
)


# ─── Schema ───


def test_schema_creates_tables(sqlite_store: SQLiteStore):
    """All expected tables exist after init."""
    with sqlite_store._connect() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    tables = {r["name"] for r in rows}
    assert tables >= {
        "items",
        "clusters",
        "cluster_membership",
        "digests",
        "source_status",
        "cost_log",
    }


def test_wal_journal_mode(sqlite_store: SQLiteStore):
    with sqlite_store._connect() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"


# ─── Items CRUD ───


def test_insert_and_get_item(sqlite_store: SQLiteStore):
    item = make_enriched_item()
    sqlite_store.insert_item(item)
    got = sqlite_store.get_item(item.id)
    assert got is not None
    assert got.id == item.id
    assert got.source_type == item.source_type
    assert got.summary == item.summary
    assert got.sentiment == item.sentiment


def test_get_nonexistent_item(sqlite_store: SQLiteStore):
    assert sqlite_store.get_item("nonexistent") is None


def test_entities_json_roundtrip(sqlite_store: SQLiteStore):
    """Entities survive JSON serialization/deserialization."""
    item = make_enriched_item()
    sqlite_store.insert_item(item)
    got = sqlite_store.get_item(item.id)
    assert len(got.entities) == 1
    assert got.entities[0].name == "Test Org"
    assert got.entities[0].aliases == ["TO"]


def test_claims_json_roundtrip(sqlite_store: SQLiteStore):
    item = make_enriched_item(claims=["Claim A", "Claim B", "Claim C"])
    sqlite_store.insert_item(item)
    got = sqlite_store.get_item(item.id)
    assert got.claims == ["Claim A", "Claim B", "Claim C"]


def test_topic_tags_roundtrip(sqlite_store: SQLiteStore):
    item = make_enriched_item(topic_tags=["politics", "economy", "health"])
    sqlite_store.insert_item(item)
    got = sqlite_store.get_item(item.id)
    assert got.topic_tags == ["politics", "economy", "health"]


def test_duplicate_source_url_rejected(sqlite_store: SQLiteStore):
    url = "https://example.com/unique-article"
    item1 = make_enriched_item(source_url=url)
    item2 = make_enriched_item(source_url=url)
    sqlite_store.insert_item(item1)
    with pytest.raises(sqlite3.IntegrityError):
        sqlite_store.insert_item(item2)


def test_item_url_exists(sqlite_store: SQLiteStore):
    url = "https://example.com/check-me"
    assert not sqlite_store.item_url_exists(url)
    sqlite_store.insert_item(make_enriched_item(source_url=url))
    assert sqlite_store.item_url_exists(url)


def test_get_items_default(sqlite_store: SQLiteStore):
    for i in range(5):
        sqlite_store.insert_item(make_enriched_item(title=f"Item {i}"))
    items = sqlite_store.get_items()
    assert len(items) == 5


def test_get_items_with_limit(sqlite_store: SQLiteStore):
    for _ in range(10):
        sqlite_store.insert_item(make_enriched_item())
    items = sqlite_store.get_items(limit=3)
    assert len(items) == 3


def test_get_items_since_filter(sqlite_store: SQLiteStore):
    old = datetime(2024, 1, 1, tzinfo=timezone.utc)
    new = datetime(2025, 6, 1, tzinfo=timezone.utc)
    sqlite_store.insert_item(make_enriched_item(published_at=old, title="Old"))
    sqlite_store.insert_item(make_enriched_item(published_at=new, title="New"))
    cutoff = datetime(2025, 1, 1, tzinfo=timezone.utc)
    items = sqlite_store.get_items(since=cutoff)
    assert len(items) == 1
    assert items[0].title == "New"


def test_get_items_source_type_filter(sqlite_store: SQLiteStore):
    sqlite_store.insert_item(make_enriched_item(source_type=SourceType.RSS))
    sqlite_store.insert_item(make_enriched_item(source_type=SourceType.GDELT))
    sqlite_store.insert_item(make_enriched_item(source_type=SourceType.RSS))
    items = sqlite_store.get_items(source_type="rss")
    assert len(items) == 2
    assert all(i.source_type == SourceType.RSS for i in items)


def test_update_item_cluster(sqlite_store: SQLiteStore):
    item = make_enriched_item()
    sqlite_store.insert_item(item)
    sqlite_store.update_item_cluster(item.id, "cluster-1", "Test Cluster")
    got = sqlite_store.get_item(item.id)
    assert got.cluster_id == "cluster-1"
    assert got.cluster_label == "Test Cluster"


def test_get_items_by_cluster(sqlite_store: SQLiteStore):
    item1 = make_enriched_item(cluster_id="c1", cluster_label="C1")
    item2 = make_enriched_item(cluster_id="c1", cluster_label="C1")
    item3 = make_enriched_item(cluster_id="c2", cluster_label="C2")
    for item in [item1, item2, item3]:
        sqlite_store.insert_item(item)
    by_c1 = sqlite_store.get_items_by_cluster("c1")
    assert len(by_c1) == 2


def test_archive_old_items(sqlite_store: SQLiteStore):
    old = datetime(2024, 1, 1, tzinfo=timezone.utc)
    new = datetime(2025, 6, 1, tzinfo=timezone.utc)
    sqlite_store.insert_item(make_enriched_item(published_at=old))
    sqlite_store.insert_item(make_enriched_item(published_at=new))
    cutoff = datetime(2025, 1, 1, tzinfo=timezone.utc)
    archived = sqlite_store.archive_old_items(cutoff)
    assert archived == 1
    # Archived items are excluded from get_items
    items = sqlite_store.get_items()
    assert len(items) == 1


def test_get_item_count(sqlite_store: SQLiteStore):
    assert sqlite_store.get_item_count() == 0
    sqlite_store.insert_item(make_enriched_item())
    assert sqlite_store.get_item_count() == 1


# ─── Clusters ───


def test_upsert_and_get_cluster(sqlite_store: SQLiteStore):
    cluster = make_cluster()
    sqlite_store.upsert_cluster(cluster)
    got = sqlite_store.get_cluster(cluster.id)
    assert got is not None
    assert got.label == cluster.label
    assert got.centroid == cluster.centroid
    assert got.source_distribution == cluster.source_distribution


def test_get_nonexistent_cluster(sqlite_store: SQLiteStore):
    assert sqlite_store.get_cluster("nonexistent") is None


def test_upsert_cluster_overwrites(sqlite_store: SQLiteStore):
    cluster = make_cluster(label="v1")
    sqlite_store.upsert_cluster(cluster)
    cluster.label = "v2"
    cluster.item_count = 10
    sqlite_store.upsert_cluster(cluster)
    got = sqlite_store.get_cluster(cluster.id)
    assert got.label == "v2"
    assert got.item_count == 10


def test_get_active_clusters(sqlite_store: SQLiteStore):
    sqlite_store.upsert_cluster(make_cluster(status=ClusterStatus.ACTIVE))
    sqlite_store.upsert_cluster(make_cluster(status=ClusterStatus.EMERGING))
    sqlite_store.upsert_cluster(make_cluster(status=ClusterStatus.DEAD))
    sqlite_store.upsert_cluster(make_cluster(status=ClusterStatus.FADING))
    active = sqlite_store.get_active_clusters()
    assert len(active) == 2
    statuses = {c.status for c in active}
    assert statuses == {ClusterStatus.ACTIVE, ClusterStatus.EMERGING}


def test_update_cluster_status(sqlite_store: SQLiteStore):
    cluster = make_cluster(status=ClusterStatus.EMERGING)
    sqlite_store.upsert_cluster(cluster)
    sqlite_store.update_cluster_status(cluster.id, "active")
    got = sqlite_store.get_cluster(cluster.id)
    assert got.status == ClusterStatus.ACTIVE


def test_get_cluster_count(sqlite_store: SQLiteStore):
    assert sqlite_store.get_cluster_count() == 0
    sqlite_store.upsert_cluster(make_cluster())
    assert sqlite_store.get_cluster_count() == 1


# ─── Cluster Membership ───


def test_set_and_clear_membership(sqlite_store: SQLiteStore):
    item = make_enriched_item()
    cluster = make_cluster()
    sqlite_store.insert_item(item)
    sqlite_store.upsert_cluster(cluster)
    sqlite_store.set_cluster_membership(item.id, cluster.id)
    # Verify it's in the table
    with sqlite_store._connect() as conn:
        row = conn.execute(
            "SELECT * FROM cluster_membership WHERE item_id = ? AND cluster_id = ?",
            (item.id, cluster.id),
        ).fetchone()
    assert row is not None
    # Clear all
    sqlite_store.clear_cluster_memberships()
    with sqlite_store._connect() as conn:
        count = conn.execute("SELECT COUNT(*) as cnt FROM cluster_membership").fetchone()
    assert count["cnt"] == 0


# ─── Digests ───


def test_insert_and_get_digest(sqlite_store: SQLiteStore):
    digest = DailyDigest(
        generated_at=datetime.now(timezone.utc),
        content="Today's intelligence digest...",
        cluster_count=5,
        item_count=42,
        model="claude-haiku-4-5-20251001",
    )
    sqlite_store.insert_digest(digest)
    got = sqlite_store.get_latest_digest()
    assert got is not None
    assert got.content == digest.content
    assert got.cluster_count == 5


def test_get_latest_digest_empty(sqlite_store: SQLiteStore):
    assert sqlite_store.get_latest_digest() is None


def test_get_latest_digest_returns_newest(sqlite_store: SQLiteStore):
    older = DailyDigest(
        generated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        content="Old digest",
        cluster_count=3,
        item_count=20,
        model="claude-haiku-4-5-20251001",
    )
    newer = DailyDigest(
        generated_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        content="New digest",
        cluster_count=5,
        item_count=50,
        model="claude-haiku-4-5-20251001",
    )
    sqlite_store.insert_digest(older)
    sqlite_store.insert_digest(newer)
    got = sqlite_store.get_latest_digest()
    assert got.content == "New digest"


# ─── Source Status ───


def test_update_and_get_source_status(sqlite_store: SQLiteStore):
    now = datetime.now(timezone.utc)
    status = SourceStatus(
        source_name="Reuters Wire",
        source_type=SourceType.RSS,
        last_fetch_at=now,
        last_success_at=now,
        items_fetched=15,
        error_count=0,
    )
    sqlite_store.update_source_status(status)
    all_status = sqlite_store.get_all_source_status()
    assert len(all_status) == 1
    assert all_status[0].source_name == "Reuters Wire"
    assert all_status[0].items_fetched == 15


def test_source_status_upsert(sqlite_store: SQLiteStore):
    now = datetime.now(timezone.utc)
    s1 = SourceStatus(
        source_name="Feed A",
        source_type=SourceType.RSS,
        items_fetched=5,
    )
    sqlite_store.update_source_status(s1)
    s2 = SourceStatus(
        source_name="Feed A",
        source_type=SourceType.RSS,
        items_fetched=10,
        last_fetch_at=now,
    )
    sqlite_store.update_source_status(s2)
    all_status = sqlite_store.get_all_source_status()
    assert len(all_status) == 1
    assert all_status[0].items_fetched == 10


# ─── Cost Tracking ───


def test_log_and_get_daily_cost(sqlite_store: SQLiteStore):
    today = datetime.now(timezone.utc)
    sqlite_store.log_cost(make_cost_entry(cost_usd=0.01, timestamp=today))
    sqlite_store.log_cost(make_cost_entry(cost_usd=0.02, timestamp=today))
    daily = sqlite_store.get_daily_cost(today)
    assert abs(daily - 0.03) < 1e-9


def test_get_daily_cost_empty(sqlite_store: SQLiteStore):
    assert sqlite_store.get_daily_cost(datetime.now(timezone.utc)) == 0.0


def test_get_daily_cost_excludes_other_days(sqlite_store: SQLiteStore):
    today = datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc)
    yesterday = datetime(2025, 6, 14, 12, 0, tzinfo=timezone.utc)
    sqlite_store.log_cost(make_cost_entry(cost_usd=0.01, timestamp=today))
    sqlite_store.log_cost(make_cost_entry(cost_usd=0.05, timestamp=yesterday))
    assert abs(sqlite_store.get_daily_cost(today) - 0.01) < 1e-9
    assert abs(sqlite_store.get_daily_cost(yesterday) - 0.05) < 1e-9


def test_get_total_cost(sqlite_store: SQLiteStore):
    sqlite_store.log_cost(make_cost_entry(cost_usd=0.01))
    sqlite_store.log_cost(make_cost_entry(cost_usd=0.02))
    sqlite_store.log_cost(make_cost_entry(cost_usd=0.03))
    total = sqlite_store.get_total_cost()
    assert abs(total - 0.06) < 1e-9


def test_get_total_cost_empty(sqlite_store: SQLiteStore):
    assert sqlite_store.get_total_cost() == 0.0


# ─── Edge cases ───


def test_empty_db_queries(sqlite_store: SQLiteStore):
    """All queries on an empty DB return sensible defaults."""
    assert sqlite_store.get_items() == []
    assert sqlite_store.get_active_clusters() == []
    assert sqlite_store.get_all_source_status() == []
    assert sqlite_store.get_item_count() == 0
    assert sqlite_store.get_cluster_count() == 0
    assert sqlite_store.get_total_cost() == 0.0
    assert sqlite_store.get_latest_digest() is None


def test_item_with_null_optional_fields(sqlite_store: SQLiteStore):
    """Items with None title, cluster_id, cluster_label work fine."""
    item = make_enriched_item(title=None, cluster_id=None, cluster_label=None)
    sqlite_store.insert_item(item)
    got = sqlite_store.get_item(item.id)
    assert got.title is None
    assert got.cluster_id is None
    assert got.cluster_label is None
