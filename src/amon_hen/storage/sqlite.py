"""SQLite metadata store for Amon Hen."""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from amon_hen.models import (
    ClusterStatus,
    CostLogEntry,
    DailyDigest,
    EnrichedItem,
    Entity,
    EntityRole,
    EntityType,
    NarrativeCluster,
    SourceStatus,
    SourceType,
)

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL UNIQUE,
    title TEXT,
    published_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    language TEXT DEFAULT 'en',
    summary TEXT NOT NULL,
    entities_json TEXT NOT NULL,
    claims_json TEXT NOT NULL,
    framing TEXT NOT NULL,
    sentiment REAL NOT NULL,
    topic_tags_json TEXT NOT NULL,
    embedding_id TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    cluster_id TEXT,
    cluster_label TEXT,
    enrichment_model TEXT NOT NULL,
    enrichment_cost_usd REAL DEFAULT 0.0,
    archived INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_items_published_at ON items(published_at);
CREATE INDEX IF NOT EXISTS idx_items_source_type ON items(source_type);
CREATE INDEX IF NOT EXISTS idx_items_cluster_id ON items(cluster_id);

CREATE TABLE IF NOT EXISTS clusters (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    summary TEXT NOT NULL,
    item_count INTEGER DEFAULT 0,
    first_seen TEXT NOT NULL,
    last_updated TEXT NOT NULL,
    centroid_json TEXT NOT NULL,
    source_distribution_json TEXT NOT NULL,
    sentiment_distribution_json TEXT NOT NULL,
    key_entities_json TEXT NOT NULL,
    key_claims_json TEXT NOT NULL,
    status TEXT DEFAULT 'emerging',
    parent_cluster_id TEXT
);

CREATE TABLE IF NOT EXISTS cluster_membership (
    item_id TEXT NOT NULL,
    cluster_id TEXT NOT NULL,
    assigned_at TEXT NOT NULL,
    PRIMARY KEY (item_id, cluster_id),
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (cluster_id) REFERENCES clusters(id)
);

CREATE TABLE IF NOT EXISTS digests (
    id TEXT PRIMARY KEY,
    generated_at TEXT NOT NULL,
    content TEXT NOT NULL,
    cluster_count INTEGER DEFAULT 0,
    item_count INTEGER DEFAULT 0,
    model TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_status (
    source_name TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    last_fetch_at TEXT,
    last_success_at TEXT,
    items_fetched INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    last_error TEXT
);

CREATE TABLE IF NOT EXISTS cost_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cost_log_timestamp ON cost_log(timestamp);
"""


def _dt_to_str(dt: datetime) -> str:
    return dt.isoformat()


def _str_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


class SQLiteStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # --- Items ---

    def insert_item(self, item: EnrichedItem) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO items (
                    id, source_type, source_name, source_url, title,
                    published_at, ingested_at, language,
                    summary, entities_json, claims_json, framing,
                    sentiment, topic_tags_json,
                    embedding_id, embedding_model,
                    cluster_id, cluster_label,
                    enrichment_model, enrichment_cost_usd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.id,
                    item.source_type.value,
                    item.source_name,
                    item.source_url,
                    item.title,
                    _dt_to_str(item.published_at),
                    _dt_to_str(item.ingested_at),
                    item.language,
                    item.summary,
                    json.dumps([e.model_dump() for e in item.entities]),
                    json.dumps(item.claims),
                    item.framing,
                    item.sentiment,
                    json.dumps(item.topic_tags),
                    item.embedding_id,
                    item.embedding_model,
                    item.cluster_id,
                    item.cluster_label,
                    item.enrichment_model,
                    item.enrichment_cost_usd,
                ),
            )

    def get_item(self, item_id: str) -> EnrichedItem | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_item(row)

    def get_items(
        self,
        since: datetime | None = None,
        limit: int = 50,
        source_type: str | None = None,
    ) -> list[EnrichedItem]:
        query = "SELECT * FROM items WHERE archived = 0"
        params: list = []
        if since:
            query += " AND published_at >= ?"
            params.append(_dt_to_str(since))
        if source_type:
            query += " AND source_type = ?"
            params.append(source_type)
        query += " ORDER BY published_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_item(r) for r in rows]

    def item_url_exists(self, url: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM items WHERE source_url = ?", (url,)
            ).fetchone()
        return row is not None

    def update_item_cluster(
        self, item_id: str, cluster_id: str, cluster_label: str
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE items SET cluster_id = ?, cluster_label = ? WHERE id = ?",
                (cluster_id, cluster_label, item_id),
            )

    def get_items_by_cluster(self, cluster_id: str) -> list[EnrichedItem]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM items WHERE cluster_id = ? AND archived = 0 ORDER BY published_at DESC",
                (cluster_id,),
            ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def archive_old_items(self, before: datetime) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE items SET archived = 1 WHERE published_at < ? AND archived = 0",
                (_dt_to_str(before),),
            )
        return cursor.rowcount

    def _row_to_item(self, row: sqlite3.Row) -> EnrichedItem:
        entities_raw = json.loads(row["entities_json"])
        entities = [
            Entity(
                name=e["name"],
                type=EntityType(e["type"]),
                role=EntityRole(e["role"]),
                aliases=e.get("aliases", []),
            )
            for e in entities_raw
        ]
        return EnrichedItem(
            id=row["id"],
            source_type=SourceType(row["source_type"]),
            source_name=row["source_name"],
            source_url=row["source_url"],
            title=row["title"],
            published_at=_str_to_dt(row["published_at"]),
            ingested_at=_str_to_dt(row["ingested_at"]),
            language=row["language"],
            summary=row["summary"],
            entities=entities,
            claims=json.loads(row["claims_json"]),
            framing=row["framing"],
            sentiment=row["sentiment"],
            topic_tags=json.loads(row["topic_tags_json"]),
            embedding_id=row["embedding_id"],
            embedding_model=row["embedding_model"],
            cluster_id=row["cluster_id"],
            cluster_label=row["cluster_label"],
            enrichment_model=row["enrichment_model"],
            enrichment_cost_usd=row["enrichment_cost_usd"],
        )

    # --- Clusters ---

    def upsert_cluster(self, cluster: NarrativeCluster) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO clusters (
                    id, label, summary, item_count,
                    first_seen, last_updated,
                    centroid_json, source_distribution_json,
                    sentiment_distribution_json,
                    key_entities_json, key_claims_json,
                    status, parent_cluster_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    cluster.id,
                    cluster.label,
                    cluster.summary,
                    cluster.item_count,
                    _dt_to_str(cluster.first_seen),
                    _dt_to_str(cluster.last_updated),
                    json.dumps(cluster.centroid),
                    json.dumps(cluster.source_distribution),
                    json.dumps(cluster.sentiment_distribution),
                    json.dumps(cluster.key_entities),
                    json.dumps(cluster.key_claims),
                    cluster.status.value,
                    cluster.parent_cluster_id,
                ),
            )

    def get_cluster(self, cluster_id: str) -> NarrativeCluster | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM clusters WHERE id = ?", (cluster_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_cluster(row)

    def get_active_clusters(self) -> list[NarrativeCluster]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM clusters WHERE status IN ('emerging', 'active') ORDER BY item_count DESC"
            ).fetchall()
        return [self._row_to_cluster(r) for r in rows]

    def update_cluster_status(self, cluster_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE clusters SET status = ? WHERE id = ?", (status, cluster_id)
            )

    def _row_to_cluster(self, row: sqlite3.Row) -> NarrativeCluster:
        return NarrativeCluster(
            id=row["id"],
            label=row["label"],
            summary=row["summary"],
            item_count=row["item_count"],
            first_seen=_str_to_dt(row["first_seen"]),
            last_updated=_str_to_dt(row["last_updated"]),
            centroid=json.loads(row["centroid_json"]),
            source_distribution=json.loads(row["source_distribution_json"]),
            sentiment_distribution=json.loads(row["sentiment_distribution_json"]),
            key_entities=json.loads(row["key_entities_json"]),
            key_claims=json.loads(row["key_claims_json"]),
            status=ClusterStatus(row["status"]),
            parent_cluster_id=row["parent_cluster_id"],
        )

    # --- Cluster membership ---

    def set_cluster_membership(self, item_id: str, cluster_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cluster_membership (item_id, cluster_id, assigned_at) VALUES (?, ?, ?)",
                (item_id, cluster_id, _dt_to_str(datetime.now(timezone.utc))),
            )

    def clear_cluster_memberships(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM cluster_membership")

    # --- Digests ---

    def insert_digest(self, digest: DailyDigest) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO digests (id, generated_at, content, cluster_count, item_count, model) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    digest.id,
                    _dt_to_str(digest.generated_at),
                    digest.content,
                    digest.cluster_count,
                    digest.item_count,
                    digest.model,
                ),
            )

    def get_latest_digest(self) -> DailyDigest | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM digests ORDER BY generated_at DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return DailyDigest(
            id=row["id"],
            generated_at=_str_to_dt(row["generated_at"]),
            content=row["content"],
            cluster_count=row["cluster_count"],
            item_count=row["item_count"],
            model=row["model"],
        )

    # --- Source status ---

    def update_source_status(self, status: SourceStatus) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO source_status (
                    source_name, source_type, last_fetch_at, last_success_at,
                    items_fetched, error_count, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    status.source_name,
                    status.source_type.value,
                    _dt_to_str(status.last_fetch_at) if status.last_fetch_at else None,
                    _dt_to_str(status.last_success_at) if status.last_success_at else None,
                    status.items_fetched,
                    status.error_count,
                    status.last_error,
                ),
            )

    def get_all_source_status(self) -> list[SourceStatus]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM source_status ORDER BY source_name").fetchall()
        return [
            SourceStatus(
                source_name=r["source_name"],
                source_type=SourceType(r["source_type"]),
                last_fetch_at=_str_to_dt(r["last_fetch_at"]) if r["last_fetch_at"] else None,
                last_success_at=_str_to_dt(r["last_success_at"]) if r["last_success_at"] else None,
                items_fetched=r["items_fetched"],
                error_count=r["error_count"],
                last_error=r["last_error"],
            )
            for r in rows
        ]

    # --- Cost tracking ---

    def log_cost(self, entry: CostLogEntry) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO cost_log (item_id, model, input_tokens, output_tokens, cost_usd, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    entry.item_id,
                    entry.model,
                    entry.input_tokens,
                    entry.output_tokens,
                    entry.cost_usd,
                    _dt_to_str(entry.timestamp),
                ),
            )

    def get_daily_cost(self, date: datetime) -> float:
        day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start.replace(hour=23, minute=59, second=59)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0.0) as total FROM cost_log WHERE timestamp >= ? AND timestamp <= ?",
                (_dt_to_str(day_start), _dt_to_str(day_end)),
            ).fetchone()
        return float(row["total"])

    def get_total_cost(self) -> float:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0.0) as total FROM cost_log"
            ).fetchone()
        return float(row["total"])

    # --- Stats ---

    def get_item_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM items WHERE archived = 0"
            ).fetchone()
        return int(row["cnt"])

    def get_cluster_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM clusters").fetchone()
        return int(row["cnt"])
