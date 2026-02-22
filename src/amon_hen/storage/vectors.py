"""Qdrant vector store operations for Amon Hen."""

from __future__ import annotations

import logging
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.models import (
    DatetimeRange,
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    ScoredPoint,
    VectorParams,
)

from amon_hen.config import Settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "amon_hen_items"
VECTOR_SIZE = 384  # all-MiniLM-L6-v2


class VectorStore:
    def __init__(self, settings: Settings):
        if settings.qdrant_mode == "memory":
            self.client = QdrantClient(":memory:")
        elif settings.qdrant_mode == "local":
            self.client = QdrantClient(path=str(settings.qdrant_local_path))
        else:  # cloud
            self.client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key or None,
            )
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        collections = [c.name for c in self.client.get_collections().collections]
        if COLLECTION_NAME not in collections:
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=VECTOR_SIZE,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(f"Created Qdrant collection '{COLLECTION_NAME}'")

    def upsert_item(
        self, point_id: str, vector: list[float], payload: dict
    ) -> None:
        self.client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
            ],
        )

    def search(
        self,
        query_vector: list[float],
        limit: int = 20,
        source_type: str | None = None,
        since: str | None = None,
    ) -> list[ScoredPoint]:
        conditions = []
        if source_type:
            conditions.append(
                FieldCondition(key="source_type", match=MatchValue(value=source_type))
            )
        if since:
            conditions.append(
                FieldCondition(key="published_at", range=DatetimeRange(gte=since))
            )
        query_filter = Filter(must=conditions) if conditions else None

        result = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=limit,
            query_filter=query_filter,
        )
        return result.points

    def get_all_vectors(
        self, since: str | None = None
    ) -> tuple[list[str], list[list[float]]]:
        """Retrieve all vectors for clustering. Returns (point_ids, vectors)."""
        conditions = []
        if since:
            conditions.append(
                FieldCondition(key="published_at", range=DatetimeRange(gte=since))
            )
        scroll_filter = Filter(must=conditions) if conditions else None

        ids: list[str] = []
        vectors: list[list[float]] = []
        offset = None

        while True:
            results, next_offset = self.client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=scroll_filter,
                limit=1000,
                offset=offset,
                with_vectors=True,
            )
            for point in results:
                ids.append(str(point.id))
                vectors.append(list(point.vector))
            if next_offset is None:
                break
            offset = next_offset

        return ids, vectors

    def get_vectors_by_ids(self, point_ids: list[str]) -> dict[str, list[float]]:
        if not point_ids:
            return {}
        points = self.client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=point_ids,
            with_vectors=True,
        )
        return {str(p.id): list(p.vector) for p in points}

    def delete_points(self, point_ids: list[str]) -> None:
        if not point_ids:
            return
        from qdrant_client.models import PointIdsList
        self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=PointIdsList(points=point_ids),
        )

    def get_collection_info(self) -> dict:
        info = self.client.get_collection(COLLECTION_NAME)
        return {
            "name": COLLECTION_NAME,
            "points_count": info.points_count,
        }
