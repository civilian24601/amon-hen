"""Source ingestion layer — fetch from RSS, GDELT, Bluesky, Reddit."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod

from amon_hen.config import Settings, SourcesConfig, get_settings, get_sources
from amon_hen.models import RawItem, SourceStatus, SourceType
from amon_hen.storage.sqlite import SQLiteStore

logger = logging.getLogger(__name__)


class BaseSource(ABC):
    """Abstract base for all ingestion sources."""

    source_type: SourceType

    @abstractmethod
    async def fetch(self) -> list[RawItem]:
        ...


def deduplicate(items: list[RawItem], store: SQLiteStore) -> list[RawItem]:
    """Filter out items whose source_url already exists in SQLite."""
    new = []
    for item in items:
        if not store.item_url_exists(item.source_url):
            new.append(item)
    return new


async def run_ingestion(
    settings: Settings | None = None,
    sources_config: SourcesConfig | None = None,
    sqlite: SQLiteStore | None = None,
) -> list[RawItem]:
    """Fetch from all configured sources, deduplicate, return new items."""
    from datetime import datetime, timezone

    from amon_hen.sources.bluesky import fetch_bluesky
    from amon_hen.sources.gdelt import fetch_gdelt
    from amon_hen.sources.reddit import fetch_reddit
    from amon_hen.sources.rss import fetch_all_rss
    from amon_hen.storage import get_stores

    if settings is None:
        settings = get_settings()
    if sources_config is None:
        sources_config = get_sources(settings)
    if sqlite is None:
        sqlite, _ = get_stores(settings)

    now = datetime.now(timezone.utc)
    all_items: list[RawItem] = []

    # Gather all source fetches concurrently
    tasks = []
    task_names = []

    if sources_config.rss:
        tasks.append(fetch_all_rss(sources_config.rss))
        task_names.append("rss")

    if sources_config.gdelt.enabled and sources_config.gdelt.queries:
        tasks.append(fetch_gdelt(sources_config.gdelt))
        task_names.append("gdelt")

    if sources_config.bluesky.enabled:
        tasks.append(fetch_bluesky(sources_config.bluesky, settings))
        task_names.append("bluesky")

    if sources_config.reddit.enabled and sources_config.reddit.subreddits:
        tasks.append(fetch_reddit(sources_config.reddit, settings))
        task_names.append("reddit")

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for name, result in zip(task_names, results):
        if isinstance(result, Exception):
            logger.error(f"Source '{name}' failed: {result}")
            source_type = SourceType(name)
            sqlite.update_source_status(
                SourceStatus(
                    source_name=name,
                    source_type=source_type,
                    last_fetch_at=now,
                    error_count=1,
                    last_error=str(result),
                )
            )
        else:
            items = result
            logger.info(f"Source '{name}' fetched {len(items)} items")
            all_items.extend(items)
            source_type = SourceType(name)
            sqlite.update_source_status(
                SourceStatus(
                    source_name=name,
                    source_type=source_type,
                    last_fetch_at=now,
                    last_success_at=now,
                    items_fetched=len(items),
                )
            )

    # Deduplicate against existing DB
    new_items = deduplicate(all_items, sqlite)
    logger.info(
        f"Ingestion complete: {len(all_items)} fetched, {len(new_items)} new "
        f"({len(all_items) - len(new_items)} duplicates filtered)"
    )
    return new_items
