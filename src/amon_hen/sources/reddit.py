"""Reddit ingestion via PRAW."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import praw

from amon_hen.config import RedditConfig, Settings
from amon_hen.models import RawItem, SourceType

logger = logging.getLogger(__name__)


def _fetch_reddit_sync(config: RedditConfig, settings: Settings) -> list[RawItem]:
    """Synchronous Reddit fetch using PRAW."""
    if not settings.reddit_client_id or not settings.reddit_client_secret:
        logger.warning("Reddit credentials not configured, skipping")
        return []

    reddit = praw.Reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        user_agent=settings.reddit_user_agent,
    )

    all_items: list[RawItem] = []

    for sub_config in config.subreddits:
        try:
            subreddit = reddit.subreddit(sub_config.name)
            if sub_config.sort == "hot":
                submissions = subreddit.hot(limit=sub_config.limit)
            elif sub_config.sort == "new":
                submissions = subreddit.new(limit=sub_config.limit)
            elif sub_config.sort == "top":
                submissions = subreddit.top(limit=sub_config.limit, time_filter="day")
            else:
                submissions = subreddit.hot(limit=sub_config.limit)
        except Exception as e:
            logger.warning(f"Reddit r/{sub_config.name} failed: {e}")
            continue

        for submission in submissions:
            # Build content from title + selftext + top comments
            parts = []
            if submission.title:
                parts.append(submission.title)
            if submission.selftext:
                parts.append(submission.selftext)

            # Include top comments if configured
            if config.include_top_comments > 0:
                try:
                    submission.comments.replace_more(limit=0)
                    for comment in submission.comments[:config.include_top_comments]:
                        if hasattr(comment, "body") and comment.body:
                            parts.append(f"[comment] {comment.body}")
                except Exception:
                    pass

            content = "\n\n".join(parts)
            if not content:
                continue

            created = datetime.fromtimestamp(
                submission.created_utc, tz=timezone.utc
            )

            all_items.append(
                RawItem(
                    source_type=SourceType.REDDIT,
                    source_name=f"reddit:r/{sub_config.name}",
                    source_url=f"https://reddit.com{submission.permalink}",
                    title=submission.title,
                    content_text=content,
                    author=str(getattr(submission, "author", "[deleted]") or "[deleted]"),
                    published_at=created,
                    raw_metadata={
                        "subreddit": sub_config.name,
                        "score": submission.score,
                        "upvote_ratio": submission.upvote_ratio,
                        "num_comments": submission.num_comments,
                        "is_self": submission.is_self,
                        "link_flair_text": submission.link_flair_text,
                    },
                )
            )

    logger.info(f"Reddit: {len(all_items)} posts")
    return all_items


async def fetch_reddit(config: RedditConfig, settings: Settings) -> list[RawItem]:
    """Async wrapper for synchronous PRAW fetch."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_reddit_sync, config, settings)
