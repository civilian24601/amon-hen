"""GDELT news ingestion via gdeltdoc library."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from amon_hen.config import GDELTConfig, GDELTQueryConfig
from amon_hen.models import RawItem, SourceType

logger = logging.getLogger(__name__)


def _fetch_gdelt_query(query_config: GDELTQueryConfig) -> list[RawItem]:
    """Synchronous GDELT fetch for a single query config."""
    from gdeltdoc import Filters, GdeltDoc

    gd = GdeltDoc()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=1)

    f = Filters(
        keyword=" OR ".join(query_config.keywords),
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d"),
    )

    try:
        articles = gd.article_search(f)
    except Exception as e:
        logger.warning(f"GDELT query '{query_config.name}' failed: {e}")
        return []

    if articles is None or articles.empty:
        logger.info(f"GDELT '{query_config.name}': 0 articles")
        return []

    items = []
    for _, row in articles.iterrows():
        url = row.get("url", "")
        title = row.get("title", "")
        if not url or not title:
            continue

        # Parse seendate (YYYYMMDDTHHMMSS format)
        published = datetime.now(timezone.utc)
        seendate = str(row.get("seendate", ""))
        if seendate and len(seendate) >= 8:
            try:
                published = datetime.strptime(
                    seendate[:15], "%Y%m%dT%H%M%S"
                ).replace(tzinfo=timezone.utc)
            except (ValueError, IndexError):
                pass

        items.append(
            RawItem(
                source_type=SourceType.GDELT,
                source_name=f"gdelt:{query_config.name}",
                source_url=url,
                title=title,
                content_text=title,  # GDELT only gives titles, no full text
                published_at=published,
                raw_metadata={
                    "domain": row.get("domain", ""),
                    "language": row.get("language", ""),
                    "sourcecountry": row.get("sourcecountry", ""),
                    "tone": row.get("tone", 0),
                    "query_name": query_config.name,
                },
            )
        )
    logger.info(f"GDELT '{query_config.name}': {len(items)} articles")
    return items


def _fetch_gdelt_backfill(
    query_config: GDELTQueryConfig,
    start_date: datetime,
    end_date: datetime,
) -> list[RawItem]:
    """Fetch historical GDELT articles for backfill/seeding."""
    from gdeltdoc import Filters, GdeltDoc

    gd = GdeltDoc()
    f = Filters(
        keyword=" OR ".join(query_config.keywords),
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
    )

    try:
        articles = gd.article_search(f)
    except Exception as e:
        logger.warning(f"GDELT backfill '{query_config.name}' failed: {e}")
        return []

    if articles is None or articles.empty:
        return []

    items = []
    for _, row in articles.iterrows():
        url = row.get("url", "")
        title = row.get("title", "")
        if not url or not title:
            continue

        published = datetime.now(timezone.utc)
        seendate = str(row.get("seendate", ""))
        if seendate and len(seendate) >= 8:
            try:
                published = datetime.strptime(
                    seendate[:15], "%Y%m%dT%H%M%S"
                ).replace(tzinfo=timezone.utc)
            except (ValueError, IndexError):
                pass

        items.append(
            RawItem(
                source_type=SourceType.GDELT,
                source_name=f"gdelt:{query_config.name}",
                source_url=url,
                title=title,
                content_text=title,
                published_at=published,
                raw_metadata={
                    "domain": row.get("domain", ""),
                    "language": row.get("language", ""),
                    "sourcecountry": row.get("sourcecountry", ""),
                    "tone": row.get("tone", 0),
                    "query_name": query_config.name,
                    "backfill": True,
                },
            )
        )
    logger.info(f"GDELT backfill '{query_config.name}': {len(items)} articles")
    return items


async def fetch_gdelt(config: GDELTConfig) -> list[RawItem]:
    """Fetch from all configured GDELT queries (sync wrapped in thread)."""
    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(None, _fetch_gdelt_query, q)
        for q in config.queries
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_items = []
    for q, result in zip(config.queries, results):
        if isinstance(result, Exception):
            logger.error(f"GDELT query '{q.name}' error: {result}")
        else:
            all_items.extend(result)
    return all_items


async def fetch_gdelt_backfill(
    config: GDELTConfig,
    days: int = 7,
) -> list[RawItem]:
    """Fetch historical GDELT articles for seeding."""
    loop = asyncio.get_event_loop()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    tasks = [
        loop.run_in_executor(None, _fetch_gdelt_backfill, q, start, end)
        for q in config.queries
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_items = []
    for q, result in zip(config.queries, results):
        if isinstance(result, Exception):
            logger.error(f"GDELT backfill '{q.name}' error: {result}")
        else:
            all_items.extend(result)
    logger.info(f"GDELT backfill total: {len(all_items)} articles over {days} days")
    return all_items
