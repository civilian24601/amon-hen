"""Tests for RSS source ingestion."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from amon_hen.config import RSSSourceConfig
from amon_hen.models import SourceType
from amon_hen.sources.rss import _parse_date, _strip_html, fetch_all_rss

SAMPLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>Test Feed</title>
  <item>
    <title>Test Article One</title>
    <link>https://example.com/article-1</link>
    <description>&lt;p&gt;First article &lt;b&gt;content&lt;/b&gt;.&lt;/p&gt;</description>
    <author>Author A</author>
    <pubDate>Mon, 01 Jan 2025 12:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Test Article Two</title>
    <link>https://example.com/article-2</link>
    <description>Second article plain text.</description>
    <pubDate>Tue, 02 Jan 2025 12:00:00 GMT</pubDate>
  </item>
  <item>
    <title>No Link Item</title>
  </item>
</channel>
</rss>"""


def test_strip_html():
    assert _strip_html("<p>Hello <b>World</b></p>") == "Hello World"
    assert _strip_html("Plain text") == "Plain text"
    assert _strip_html("") == ""


@pytest.mark.asyncio
async def test_fetch_all_rss_parses_feed():
    """RSS fetcher parses valid XML into RawItems."""
    configs = [
        RSSSourceConfig(name="Test Feed", url="https://example.com/feed.xml", category="test")
    ]

    async def mock_get(url, **kwargs):
        resp = httpx.Response(200, text=SAMPLE_RSS_XML, request=httpx.Request("GET", url))
        return resp

    with patch("amon_hen.sources.rss.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        items = await fetch_all_rss(configs)

    # Should get 2 items (the one without a link is skipped)
    assert len(items) == 2
    assert items[0].source_type == SourceType.RSS
    assert items[0].source_name == "Test Feed"
    assert items[0].source_url == "https://example.com/article-1"
    assert items[0].title == "Test Article One"
    # HTML should be stripped from content
    assert "<p>" not in items[0].content_text
    assert "First article" in items[0].content_text
    assert items[0].raw_metadata["category"] == "test"


@pytest.mark.asyncio
async def test_fetch_all_rss_handles_http_error():
    """RSS fetcher handles HTTP errors gracefully."""
    configs = [
        RSSSourceConfig(name="Bad Feed", url="https://example.com/bad.xml", category="test")
    ]

    async def mock_get(url, **kwargs):
        resp = httpx.Response(404, text="Not Found", request=httpx.Request("GET", url))
        resp.raise_for_status()
        return resp

    with patch("amon_hen.sources.rss.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        items = await fetch_all_rss(configs)

    # Should return empty list, not raise
    assert items == []
