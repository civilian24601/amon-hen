"""LLM enrichment pipeline — enrich raw items with intelligence."""

from __future__ import annotations

import asyncio
import logging

from amon_hen.config import Settings
from amon_hen.enrichment.embeddings import EmbeddingService
from amon_hen.enrichment.llm import LLMProvider
from amon_hen.models import EnrichedItem, RawItem
from amon_hen.storage.sqlite import SQLiteStore
from amon_hen.storage.vectors import VectorStore

logger = logging.getLogger(__name__)


async def enrich_items(
    raw_items: list[RawItem],
    settings: Settings,
    sqlite: SQLiteStore,
    vectors: VectorStore,
    llm: LLMProvider,
    embedder: EmbeddingService,
    concurrency: int = 3,
) -> list[EnrichedItem]:
    """Enrich raw items with LLM intelligence + embeddings, store results.

    Uses a semaphore to limit concurrent LLM calls.
    Checks daily budget before each enrichment.
    """
    from datetime import datetime, timezone

    semaphore = asyncio.Semaphore(concurrency)
    enriched: list[EnrichedItem] = []

    async def _process_one(item: RawItem) -> EnrichedItem | None:
        async with semaphore:
            # Check budget
            today = datetime.now(timezone.utc)
            daily_cost = sqlite.get_daily_cost(today)
            if daily_cost >= settings.enrichment_daily_budget_usd:
                logger.warning(
                    f"Daily budget ${settings.enrichment_daily_budget_usd:.2f} exceeded "
                    f"(${daily_cost:.4f} spent), skipping item {item.id}"
                )
                return None

            try:
                result, cost_entry = await llm.enrich(item)
            except Exception as e:
                logger.error(f"LLM enrichment failed for item {item.id}: {e}")
                return None

            # Log cost
            if settings.enrichment.track_costs:
                sqlite.log_cost(cost_entry)

            # Generate embedding from intelligence signal
            try:
                vector = embedder.embed_enrichment(result)
            except Exception as e:
                logger.error(f"Embedding failed for item {item.id}: {e}")
                return None

            # Build enriched item
            enriched_item = EnrichedItem(
                id=item.id,
                source_type=item.source_type,
                source_name=item.source_name,
                source_url=item.source_url,
                title=item.title,
                published_at=item.published_at,
                ingested_at=item.ingested_at,
                language=item.language,
                summary=result.summary,
                entities=result.entities,
                claims=result.claims,
                framing=result.framing,
                sentiment=result.sentiment,
                topic_tags=result.topic_tags,
                embedding_id=item.id,
                embedding_model=embedder.model_name,
                enrichment_model=cost_entry.model,
                enrichment_cost_usd=cost_entry.cost_usd,
            )

            # Store in SQLite
            try:
                sqlite.insert_item(enriched_item)
            except Exception as e:
                logger.error(f"SQLite insert failed for item {item.id}: {e}")
                return None

            # Store in Qdrant
            payload = {
                "source_type": item.source_type.value,
                "source_name": item.source_name,
                "published_at": item.published_at.isoformat(),
                "title": item.title or "",
                "summary": result.summary,
            }
            vectors.upsert_item(item.id, vector, payload)

            return enriched_item

    tasks = [_process_one(item) for item in raw_items]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in results:
        if isinstance(r, Exception):
            logger.error(f"Enrichment task error: {r}")
        elif r is not None:
            enriched.append(r)

    logger.info(
        f"Enrichment complete: {len(enriched)}/{len(raw_items)} items enriched"
    )
    return enriched
