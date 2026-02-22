"""Tests for GDELT source ingestion."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from amon_hen.config import GDELTConfig, GDELTQueryConfig
from amon_hen.models import SourceType
from amon_hen.sources.gdelt import fetch_gdelt


@pytest.fixture
def gdelt_config():
    return GDELTConfig(
        enabled=True,
        queries=[
            GDELTQueryConfig(name="test_query", keywords=["climate", "policy"]),
        ],
    )


@pytest.fixture
def sample_gdelt_df():
    return pd.DataFrame(
        {
            "url": [
                "https://news.example.com/article-1",
                "https://news.example.com/article-2",
            ],
            "title": ["Climate Policy Update", "New Climate Report"],
            "seendate": ["20250601T120000", "20250601T130000"],
            "domain": ["news.example.com", "news.example.com"],
            "language": ["English", "English"],
            "sourcecountry": ["United States", "United States"],
            "tone": [-1.5, 0.3],
        }
    )


@pytest.mark.asyncio
async def test_fetch_gdelt_parses_articles(gdelt_config, sample_gdelt_df):
    """GDELT fetcher converts DataFrame rows to RawItems."""
    with patch("gdeltdoc.GdeltDoc") as MockGdelt:
        mock_gd = MagicMock()
        mock_gd.article_search.return_value = sample_gdelt_df
        MockGdelt.return_value = mock_gd

        items = await fetch_gdelt(gdelt_config)

    assert len(items) == 2
    assert items[0].source_type == SourceType.GDELT
    assert items[0].source_name == "gdelt:test_query"
    assert items[0].title == "Climate Policy Update"
    # GDELT uses title as content_text (no full text available)
    assert items[0].content_text == "Climate Policy Update"
    assert items[0].raw_metadata["domain"] == "news.example.com"


@pytest.mark.asyncio
async def test_fetch_gdelt_handles_empty_results(gdelt_config):
    """GDELT fetcher handles empty DataFrame gracefully."""
    with patch("gdeltdoc.GdeltDoc") as MockGdelt:
        mock_gd = MagicMock()
        mock_gd.article_search.return_value = pd.DataFrame()
        MockGdelt.return_value = mock_gd

        items = await fetch_gdelt(gdelt_config)

    assert items == []


@pytest.mark.asyncio
async def test_fetch_gdelt_handles_api_error(gdelt_config):
    """GDELT fetcher handles API errors gracefully."""
    with patch("gdeltdoc.GdeltDoc") as MockGdelt:
        mock_gd = MagicMock()
        mock_gd.article_search.side_effect = Exception("API error")
        MockGdelt.return_value = mock_gd

        items = await fetch_gdelt(gdelt_config)

    assert items == []
