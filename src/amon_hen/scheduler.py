"""Pipeline scheduler using APScheduler."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from amon_hen.config import Settings, get_settings, get_sources

logger = logging.getLogger(__name__)


class PipelineScheduler:
    """Schedule periodic ingestion, enrichment, clustering, and cleanup."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._scheduler = AsyncIOScheduler()
        self._setup_jobs()

    def _setup_jobs(self) -> None:
        # Ingest + enrich every 15 minutes
        self._scheduler.add_job(
            self.ingest_and_enrich,
            IntervalTrigger(minutes=15),
            id="ingest_and_enrich",
            name="Ingest and enrich",
            replace_existing=True,
        )

        # Cluster every 2 hours
        self._scheduler.add_job(
            self.run_clustering,
            IntervalTrigger(hours=2),
            id="run_clustering",
            name="Run clustering",
            replace_existing=True,
        )

        # Daily digest at 6:00 AM UTC
        self._scheduler.add_job(
            self.generate_digest,
            CronTrigger(hour=6, minute=0),
            id="generate_digest",
            name="Generate daily digest",
            replace_existing=True,
        )

        # Cleanup old data daily at midnight UTC
        self._scheduler.add_job(
            self.cleanup_old_data,
            CronTrigger(hour=0, minute=0),
            id="cleanup_old_data",
            name="Clean up old data",
            replace_existing=True,
        )

    def start(self) -> None:
        self._scheduler.start()
        logger.info("Pipeline scheduler started")

    def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("Pipeline scheduler stopped")

    async def ingest_and_enrich(self) -> None:
        """Combined ingestion + enrichment cycle."""
        logger.info("Starting ingest + enrich cycle")
        try:
            from amon_hen.enrichment import enrich_items
            from amon_hen.enrichment.embeddings import EmbeddingService
            from amon_hen.enrichment.llm import get_provider
            from amon_hen.sources import run_ingestion
            from amon_hen.storage import get_stores

            sqlite, vectors = get_stores(self.settings)
            raw_items = await run_ingestion(self.settings)

            if not raw_items:
                logger.info("No new items to enrich")
                return

            llm = get_provider(self.settings)
            embedder = EmbeddingService()
            enriched = await enrich_items(
                raw_items, self.settings, sqlite, vectors, llm, embedder
            )
            logger.info(f"Cycle complete: {len(enriched)} items enriched")
        except Exception as e:
            logger.error(f"Ingest+enrich cycle failed: {e}", exc_info=True)

    async def run_clustering(self) -> None:
        """Run the intelligence pipeline."""
        logger.info("Starting clustering cycle")
        try:
            from amon_hen.intelligence import run_intelligence_pipeline
            from amon_hen.storage import get_stores

            sqlite, vectors = get_stores(self.settings)
            result = await run_intelligence_pipeline(self.settings, sqlite, vectors)
            clusters = result["clusters"]
            logger.info(f"Clustering complete: {len(clusters)} clusters")
        except Exception as e:
            logger.error(f"Clustering cycle failed: {e}", exc_info=True)

    async def generate_digest(self) -> None:
        """Generate daily intelligence digest."""
        logger.info("Generating daily digest")
        try:
            from amon_hen.enrichment.llm import get_provider
            from amon_hen.intelligence import run_intelligence_pipeline
            from amon_hen.intelligence.digest import DigestGenerator
            from amon_hen.storage import get_stores

            sqlite, vectors = get_stores(self.settings)
            llm = get_provider(self.settings)

            result = await run_intelligence_pipeline(self.settings, sqlite, vectors, llm)
            all_anomalies = (
                result["anomalies"].get("volume_spikes", [])
                + result["anomalies"].get("sentiment_shifts", [])
                + result["anomalies"].get("entity_surges", [])
            )

            generator = DigestGenerator(llm, sqlite)
            digest = await generator.generate(
                result["clusters"], result["divergences"], all_anomalies
            )
            logger.info(f"Digest generated: {digest.id}")
        except Exception as e:
            logger.error(f"Digest generation failed: {e}", exc_info=True)

    async def cleanup_old_data(self) -> None:
        """Archive items older than the rolling window."""
        logger.info("Cleaning up old data")
        try:
            from amon_hen.storage import get_stores

            sqlite, vectors = get_stores(self.settings)
            cutoff = datetime.now(timezone.utc) - timedelta(
                days=self.settings.clustering.rolling_window_days
            )
            archived = sqlite.archive_old_items(cutoff)
            logger.info(f"Archived {archived} old items")
        except Exception as e:
            logger.error(f"Cleanup failed: {e}", exc_info=True)
