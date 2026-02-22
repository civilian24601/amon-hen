"""RSS feed ingestion."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx

from amon_hen.config import RSSSourceConfig
from amon_hen.models import RawItem, SourceType

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    return _HTML_TAG_RE.sub("", text).strip()


def _parse_date(entry: dict) -> datetime:
    """Extract publication date from a feedparser entry."""
    for field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field)
        if parsed:
            try:
                from time import mktime
                return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
            except (ValueError, OverflowError, OSError):
                continue
    # Fallback: try raw string
    for field in ("published", "updated"):
        raw = entry.get(field)
        if raw:
            try:
                return parsedate_to_datetime(raw).astimezone(timezone.utc)
            except (ValueError, TypeError):
                try:
                    return datetime.fromisoformat(raw).astimezone(timezone.utc)
                except (ValueError, TypeError):
                    continue
    return datetime.now(timezone.utc)


async def _fetch_single_feed(
    config: RSSSourceConfig, client: httpx.AsyncClient
) -> list[RawItem]:
    """Fetch and parse a single RSS feed."""
    try:
        resp = await client.get(config.url, follow_redirects=True)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
    except Exception as e:
        logger.warning(f"RSS feed '{config.name}' ({config.url}) failed: {e}")
        return []

    items = []
    for entry in feed.entries:
        link = entry.get("link", "")
        if not link:
            continue

        title = entry.get("title", "")
        # Content: prefer summary, fallback to content
        content = ""
        if entry.get("summary"):
            content = _strip_html(entry.summary)
        elif entry.get("content"):
            content = _strip_html(entry.content[0].get("value", ""))
        if not content:
            content = title  # Fallback to title

        items.append(
            RawItem(
                source_type=SourceType.RSS,
                source_name=config.name,
                source_url=link,
                title=title,
                content_text=content,
                author=entry.get("author"),
                published_at=_parse_date(entry),
                raw_metadata={
                    "category": config.category,
                    "feed_url": config.url,
                    "tags": [t.get("term", "") for t in entry.get("tags", [])],
                },
            )
        )
    logger.info(f"RSS '{config.name}': {len(items)} entries")
    return items


async def fetch_all_rss(
    configs: list[RSSSourceConfig],
    timeout: float = 30.0,
) -> list[RawItem]:
    """Fetch all configured RSS feeds concurrently."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        tasks = [_fetch_single_feed(c, client) for c in configs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_items = []
    for config, result in zip(configs, results):
        if isinstance(result, Exception):
            logger.error(f"RSS '{config.name}' error: {result}")
        else:
            all_items.extend(result)
    return all_items
