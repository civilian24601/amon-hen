"""Tests for source deduplication logic."""

from __future__ import annotations

import pytest

from amon_hen.sources import deduplicate
from amon_hen.storage.sqlite import SQLiteStore
from tests.conftest import make_enriched_item, make_enriched_item as _mei

from amon_hen.models import RawItem, SourceType
from datetime import datetime, timezone


def _make_raw(url: str) -> RawItem:
    return RawItem(
        source_type=SourceType.RSS,
        source_name="test",
        source_url=url,
        content_text="test content",
        published_at=datetime.now(timezone.utc),
    )


def test_deduplicate_filters_existing(sqlite_store: SQLiteStore):
    """Items with URLs already in SQLite are filtered out."""
    existing_url = "https://example.com/existing"
    sqlite_store.insert_item(make_enriched_item(source_url=existing_url))

    items = [
        _make_raw("https://example.com/existing"),
        _make_raw("https://example.com/new-1"),
        _make_raw("https://example.com/new-2"),
    ]

    result = deduplicate(items, sqlite_store)
    assert len(result) == 2
    assert all(i.source_url != existing_url for i in result)


def test_deduplicate_empty_db(sqlite_store: SQLiteStore):
    """With empty DB, all items pass through."""
    items = [_make_raw(f"https://example.com/{i}") for i in range(5)]
    result = deduplicate(items, sqlite_store)
    assert len(result) == 5


def test_deduplicate_empty_list(sqlite_store: SQLiteStore):
    """Empty input returns empty output."""
    assert deduplicate([], sqlite_store) == []
