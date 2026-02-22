"""Intelligence layer — clustering, divergence, anomalies, digest."""

from __future__ import annotations

import logging

from amon_hen.config import Settings
from amon_hen.enrichment.llm import LLMProvider
from amon_hen.intelligence.anomalies import AnomalyDetector
from amon_hen.intelligence.clustering import ClusteringPipeline
from amon_hen.intelligence.divergence import DivergenceDetector
from amon_hen.storage.sqlite import SQLiteStore
from amon_hen.storage.vectors import VectorStore

logger = logging.getLogger(__name__)


async def run_intelligence_pipeline(
    settings: Settings,
    sqlite: SQLiteStore,
    vectors: VectorStore,
    llm: LLMProvider | None = None,
) -> dict:
    """Run the full intelligence pipeline: cluster -> divergence -> anomalies."""
    # 1. Clustering
    pipeline = ClusteringPipeline(settings.clustering, sqlite, vectors, llm)
    clusters = await pipeline.run()

    # 2. Divergence detection
    divergence_detector = DivergenceDetector(
        threshold=settings.clustering.divergence_threshold
    )
    divergences = divergence_detector.detect(clusters, sqlite, vectors)

    # 3. Anomaly detection
    anomaly_detector = AnomalyDetector(sqlite)
    anomalies = {
        "volume_spikes": anomaly_detector.detect_volume_spikes(clusters),
        "sentiment_shifts": anomaly_detector.detect_sentiment_shifts(clusters),
        "entity_surges": anomaly_detector.detect_entity_surges(),
    }

    all_anomalies = (
        anomalies["volume_spikes"]
        + anomalies["sentiment_shifts"]
        + anomalies["entity_surges"]
    )

    logger.info(
        f"Intelligence pipeline complete: {len(clusters)} clusters, "
        f"{len(divergences)} divergences, {len(all_anomalies)} anomalies"
    )

    return {
        "clusters": clusters,
        "divergences": divergences,
        "anomalies": anomalies,
    }
