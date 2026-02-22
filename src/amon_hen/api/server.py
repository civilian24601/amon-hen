"""FastAPI REST API for Amon Hen."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from amon_hen.config import get_settings
from amon_hen.storage import get_stores

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    sqlite, vectors = get_stores(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup: optionally start scheduler
        logger.info("Amon Hen API starting")
        try:
            from amon_hen.scheduler import PipelineScheduler

            scheduler = PipelineScheduler(settings)
            scheduler.start()
            app.state.scheduler = scheduler
        except Exception as e:
            logger.warning(f"Scheduler not started: {e}")
        yield
        # Shutdown
        if hasattr(app.state, "scheduler"):
            app.state.scheduler.stop()
        logger.info("Amon Hen API stopped")

    app = FastAPI(
        title="Amon Hen",
        description="Narrative Intelligence Platform API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Endpoints ---

    @app.get("/api/clusters")
    def list_clusters():
        """List active narrative clusters."""
        clusters = sqlite.get_active_clusters()
        return [
            {
                "id": c.id,
                "label": c.label,
                "summary": c.summary,
                "item_count": c.item_count,
                "status": c.status.value,
                "first_seen": c.first_seen.isoformat(),
                "last_updated": c.last_updated.isoformat(),
                "source_distribution": c.source_distribution,
                "sentiment_distribution": c.sentiment_distribution,
                "key_entities": c.key_entities,
            }
            for c in clusters
        ]

    @app.get("/api/clusters/{cluster_id}")
    def get_cluster(cluster_id: str):
        """Get cluster detail with member items."""
        c = sqlite.get_cluster(cluster_id)
        if not c:
            return {"error": "Cluster not found"}, 404

        items = sqlite.get_items_by_cluster(cluster_id)
        return {
            "id": c.id,
            "label": c.label,
            "summary": c.summary,
            "item_count": c.item_count,
            "status": c.status.value,
            "first_seen": c.first_seen.isoformat(),
            "last_updated": c.last_updated.isoformat(),
            "centroid": c.centroid,
            "source_distribution": c.source_distribution,
            "sentiment_distribution": c.sentiment_distribution,
            "key_entities": c.key_entities,
            "key_claims": c.key_claims,
            "items": [
                {
                    "id": i.id,
                    "title": i.title,
                    "summary": i.summary,
                    "source_type": i.source_type.value,
                    "source_name": i.source_name,
                    "source_url": i.source_url,
                    "published_at": i.published_at.isoformat(),
                    "sentiment": i.sentiment,
                    "framing": i.framing,
                }
                for i in items[:50]
            ],
        }

    @app.get("/api/search")
    def search_items(
        q: str = Query(..., min_length=1),
        limit: int = Query(20, ge=1, le=100),
    ):
        """Semantic search across enriched items."""
        from amon_hen.enrichment.embeddings import EmbeddingService

        embedder = EmbeddingService()
        query_vec = embedder.embed_query(q)
        results = vectors.search(query_vec, limit=limit)

        return [
            {
                "id": str(r.id),
                "score": r.score,
                "title": r.payload.get("title", ""),
                "summary": r.payload.get("summary", ""),
                "source_type": r.payload.get("source_type", ""),
                "source_name": r.payload.get("source_name", ""),
                "published_at": r.payload.get("published_at", ""),
            }
            for r in results
        ]

    @app.get("/api/items")
    def list_items(
        since: str | None = None,
        limit: int = Query(50, ge=1, le=200),
        source_type: str | None = None,
    ):
        """List recent enriched items."""
        since_dt = None
        if since:
            since_dt = datetime.fromisoformat(since)
        items = sqlite.get_items(since=since_dt, limit=limit, source_type=source_type)
        return [
            {
                "id": i.id,
                "title": i.title,
                "summary": i.summary,
                "source_type": i.source_type.value,
                "source_name": i.source_name,
                "source_url": i.source_url,
                "published_at": i.published_at.isoformat(),
                "sentiment": i.sentiment,
                "cluster_id": i.cluster_id,
                "cluster_label": i.cluster_label,
            }
            for i in items
        ]

    @app.get("/api/digest/latest")
    def get_latest_digest():
        """Get the latest intelligence digest."""
        d = sqlite.get_latest_digest()
        if not d:
            return {"message": "No digest available"}
        return {
            "id": d.id,
            "generated_at": d.generated_at.isoformat(),
            "content": d.content,
            "cluster_count": d.cluster_count,
            "item_count": d.item_count,
            "model": d.model,
        }

    @app.get("/api/health")
    def health():
        """Health check with stats."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        return {
            "status": "ok",
            "items_count": sqlite.get_item_count(),
            "clusters_count": sqlite.get_cluster_count(),
            "daily_cost": sqlite.get_daily_cost(now),
            "total_cost": sqlite.get_total_cost(),
            "sources": [
                {
                    "name": s.source_name,
                    "type": s.source_type.value,
                    "last_fetch": s.last_fetch_at.isoformat() if s.last_fetch_at else None,
                    "items_fetched": s.items_fetched,
                    "error_count": s.error_count,
                }
                for s in sqlite.get_all_source_status()
            ],
            "vectors": vectors.get_collection_info(),
        }

    # Serve dashboard static files if built
    dashboard_dist = Path(__file__).parent.parent.parent.parent / "dashboard" / "dist"
    if dashboard_dist.exists():
        app.mount("/", StaticFiles(directory=str(dashboard_dist), html=True), name="dashboard")

    return app
