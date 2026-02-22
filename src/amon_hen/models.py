"""Data models for Amon Hen narrative intelligence platform."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


# --- Enums ---


class SourceType(str, Enum):
    RSS = "rss"
    GDELT = "gdelt"
    BLUESKY = "bluesky"
    REDDIT = "reddit"


class EntityType(str, Enum):
    PERSON = "person"
    ORG = "org"
    PLACE = "place"
    EVENT = "event"


class EntityRole(str, Enum):
    SUBJECT = "subject"
    TARGET = "target"
    SOURCE = "source"
    LOCATION = "location"
    MENTIONED = "mentioned"


class ClusterStatus(str, Enum):
    EMERGING = "emerging"
    ACTIVE = "active"
    FADING = "fading"
    DEAD = "dead"


# --- Core Models ---


class Entity(BaseModel):
    name: str
    type: EntityType
    role: EntityRole
    aliases: list[str] = Field(default_factory=list)


class RawItem(BaseModel):
    id: str = Field(default_factory=_new_id)
    source_type: SourceType
    source_name: str
    source_url: str
    title: str | None = None
    content_text: str
    author: str | None = None
    published_at: datetime
    ingested_at: datetime = Field(default_factory=_utcnow)
    language: str = "en"
    raw_metadata: dict = Field(default_factory=dict)


class EnrichmentResult(BaseModel):
    """Parsed LLM output for a single item."""

    summary: str
    entities: list[Entity]
    claims: list[str]
    framing: str
    sentiment: float = Field(ge=-1.0, le=1.0)
    topic_tags: list[str]


class EnrichedItem(BaseModel):
    id: str
    source_type: SourceType
    source_name: str
    source_url: str
    title: str | None = None
    published_at: datetime
    ingested_at: datetime
    language: str = "en"

    # LLM-extracted intelligence
    summary: str
    entities: list[Entity]
    claims: list[str]
    framing: str
    sentiment: float = Field(ge=-1.0, le=1.0)
    topic_tags: list[str]

    # Embedding
    embedding_id: str
    embedding_model: str = "all-MiniLM-L6-v2"

    # Cluster assignment (updated by clustering pipeline)
    cluster_id: str | None = None
    cluster_label: str | None = None

    # Metadata
    enrichment_model: str
    enrichment_cost_usd: float = 0.0


class NarrativeCluster(BaseModel):
    id: str = Field(default_factory=_new_id)
    label: str
    summary: str
    item_count: int = 0
    first_seen: datetime
    last_updated: datetime
    centroid: list[float]
    source_distribution: dict[str, int] = Field(default_factory=dict)
    sentiment_distribution: dict[str, int] = Field(default_factory=dict)
    key_entities: list[str] = Field(default_factory=list)
    key_claims: list[str] = Field(default_factory=list)
    status: ClusterStatus = ClusterStatus.EMERGING
    parent_cluster_id: str | None = None


class DailyDigest(BaseModel):
    id: str = Field(default_factory=_new_id)
    generated_at: datetime
    content: str
    cluster_count: int
    item_count: int
    model: str


class SourceStatus(BaseModel):
    source_name: str
    source_type: SourceType
    last_fetch_at: datetime | None = None
    last_success_at: datetime | None = None
    items_fetched: int = 0
    error_count: int = 0
    last_error: str | None = None


class CostLogEntry(BaseModel):
    item_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: datetime = Field(default_factory=_utcnow)
