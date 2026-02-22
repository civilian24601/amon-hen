"""Shared test fixtures for Amon Hen."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from amon_hen.config import Settings
from amon_hen.models import (
    ClusterStatus,
    CostLogEntry,
    DailyDigest,
    EnrichedItem,
    Entity,
    EntityRole,
    EntityType,
    NarrativeCluster,
    RawItem,
    SourceStatus,
    SourceType,
)
from amon_hen.storage.sqlite import SQLiteStore
from amon_hen.storage.vectors import VectorStore


def _uid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Fixtures ---


@pytest.fixture
def sqlite_store(tmp_path: Path) -> SQLiteStore:
    """Ephemeral SQLite store in a temp directory."""
    return SQLiteStore(tmp_path / "test.db")


@pytest.fixture
def vector_store() -> VectorStore:
    """In-memory Qdrant vector store."""
    settings = Settings(qdrant_mode="memory")
    return VectorStore(settings)


# --- Factory helpers ---


def make_enriched_item(
    *,
    id: str | None = None,
    source_type: SourceType = SourceType.RSS,
    source_name: str = "Test Feed",
    source_url: str | None = None,
    title: str = "Test Article",
    published_at: datetime | None = None,
    ingested_at: datetime | None = None,
    summary: str = "A test summary.",
    entities: list[Entity] | None = None,
    claims: list[str] | None = None,
    framing: str = "neutral reporting",
    sentiment: float = 0.1,
    topic_tags: list[str] | None = None,
    embedding_id: str | None = None,
    cluster_id: str | None = None,
    cluster_label: str | None = None,
    enrichment_model: str = "claude-haiku-4-5-20251001",
    enrichment_cost_usd: float = 0.001,
) -> EnrichedItem:
    now = _now()
    return EnrichedItem(
        id=id or _uid(),
        source_type=source_type,
        source_name=source_name,
        source_url=source_url or f"https://example.com/article/{_uid()}",
        title=title,
        published_at=published_at or now,
        ingested_at=ingested_at or now,
        summary=summary,
        entities=entities
        or [
            Entity(
                name="Test Org",
                type=EntityType.ORG,
                role=EntityRole.SUBJECT,
                aliases=["TO"],
            )
        ],
        claims=claims or ["Test claim one", "Test claim two"],
        framing=framing,
        sentiment=sentiment,
        topic_tags=topic_tags or ["testing", "demo"],
        embedding_id=embedding_id or _uid(),
        cluster_id=cluster_id,
        cluster_label=cluster_label,
        enrichment_model=enrichment_model,
        enrichment_cost_usd=enrichment_cost_usd,
    )


def make_cluster(
    *,
    id: str | None = None,
    label: str = "Test Cluster",
    summary: str = "A test cluster summary.",
    item_count: int = 5,
    centroid: list[float] | None = None,
    status: ClusterStatus = ClusterStatus.ACTIVE,
) -> NarrativeCluster:
    now = _now()
    return NarrativeCluster(
        id=id or _uid(),
        label=label,
        summary=summary,
        item_count=item_count,
        first_seen=now,
        last_updated=now,
        centroid=centroid or [0.1] * 10,
        source_distribution={"rss": 3, "gdelt": 2},
        sentiment_distribution={"positive": 2, "neutral": 2, "negative": 1},
        key_entities=["Entity A", "Entity B"],
        key_claims=["Claim 1"],
        status=status,
    )


def make_cost_entry(
    *,
    item_id: str | None = None,
    cost_usd: float = 0.001,
    timestamp: datetime | None = None,
) -> CostLogEntry:
    return CostLogEntry(
        item_id=item_id or _uid(),
        model="claude-haiku-4-5-20251001",
        input_tokens=500,
        output_tokens=200,
        cost_usd=cost_usd,
        timestamp=timestamp or _now(),
    )
