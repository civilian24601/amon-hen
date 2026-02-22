"""Bluesky social media ingestion via AT Protocol."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from amon_hen.config import BlueskyConfig, Settings
from amon_hen.models import RawItem, SourceType

logger = logging.getLogger(__name__)


async def fetch_bluesky(
    config: BlueskyConfig, settings: Settings
) -> list[RawItem]:
    """Fetch posts from Bluesky using the search API."""
    from atproto import AsyncClient

    if not settings.bluesky_handle or not settings.bluesky_app_password:
        logger.warning("Bluesky credentials not configured, skipping")
        return []

    client = AsyncClient()
    try:
        await client.login(settings.bluesky_handle, settings.bluesky_app_password)
    except Exception as e:
        logger.error(f"Bluesky login failed: {e}")
        return []

    all_items: list[RawItem] = []
    seen_uris: set[str] = set()

    for keyword in config.keywords:
        try:
            response = await client.app.bsky.feed.search_posts(
                params={"q": keyword, "limit": min(100, config.max_posts_per_cycle)}
            )
        except Exception as e:
            logger.warning(f"Bluesky search for '{keyword}' failed: {e}")
            continue

        for post in response.posts:
            uri = post.uri
            if uri in seen_uris:
                continue
            seen_uris.add(uri)

            record = post.record
            text = getattr(record, "text", "") or ""
            if not text:
                continue

            # Parse created_at
            created = datetime.now(timezone.utc)
            created_str = getattr(record, "created_at", None) or getattr(record, "createdAt", None)
            if created_str:
                try:
                    created = datetime.fromisoformat(
                        str(created_str).replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            # Author info
            author = post.author
            handle = getattr(author, "handle", "unknown")
            display_name = getattr(author, "display_name", handle) or handle

            # Engagement metrics
            like_count = getattr(post, "like_count", 0) or 0
            repost_count = getattr(post, "repost_count", 0) or 0
            reply_count = getattr(post, "reply_count", 0) or 0

            all_items.append(
                RawItem(
                    source_type=SourceType.BLUESKY,
                    source_name="bluesky",
                    source_url=f"https://bsky.app/profile/{handle}/post/{uri.split('/')[-1]}",
                    title=None,
                    content_text=text,
                    author=f"{display_name} (@{handle})",
                    published_at=created,
                    raw_metadata={
                        "keyword": keyword,
                        "likes": like_count,
                        "reposts": repost_count,
                        "replies": reply_count,
                        "handle": handle,
                    },
                )
            )

            if len(all_items) >= config.max_posts_per_cycle:
                break
        if len(all_items) >= config.max_posts_per_cycle:
            break

    logger.info(f"Bluesky: {len(all_items)} posts")
    return all_items
