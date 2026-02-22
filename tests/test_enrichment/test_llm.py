"""Tests for LLM enrichment."""

from __future__ import annotations

import json

import pytest

from amon_hen.enrichment.llm import (
    _parse_enrichment_json,
    _strip_code_fences,
)
from amon_hen.models import EntityRole, EntityType

VALID_JSON = json.dumps(
    {
        "summary": "Test article about climate policy changes.",
        "entities": [
            {
                "name": "United Nations",
                "type": "org",
                "role": "subject",
                "aliases": ["UN"],
            },
            {"name": "Paris", "type": "place", "role": "location"},
        ],
        "claims": [
            "Global temperatures rose 1.5C above pre-industrial levels",
            "New policy targets 50% emission reduction by 2030",
        ],
        "framing": "crisis framing with urgency",
        "sentiment": -0.3,
        "topic_tags": ["climate", "policy", "environment"],
    }
)


# ─── Code fence stripping ───


def test_strip_code_fences_json():
    wrapped = f"```json\n{VALID_JSON}\n```"
    assert _strip_code_fences(wrapped) == VALID_JSON


def test_strip_code_fences_plain():
    wrapped = f"```\n{VALID_JSON}\n```"
    assert _strip_code_fences(wrapped) == VALID_JSON


def test_strip_code_fences_none():
    assert _strip_code_fences(VALID_JSON) == VALID_JSON


def test_strip_code_fences_whitespace():
    assert _strip_code_fences(f"  ```json\n{VALID_JSON}\n```  ").strip() == VALID_JSON


# ─── JSON parsing ───


def test_parse_valid_json():
    result = _parse_enrichment_json(VALID_JSON)
    assert result.summary == "Test article about climate policy changes."
    assert len(result.entities) == 2
    assert result.entities[0].name == "United Nations"
    assert result.entities[0].type == EntityType.ORG
    assert result.entities[0].role == EntityRole.SUBJECT
    assert result.entities[0].aliases == ["UN"]
    assert len(result.claims) == 2
    assert result.framing == "crisis framing with urgency"
    assert result.sentiment == -0.3
    assert "climate" in result.topic_tags


def test_parse_code_fenced_json():
    result = _parse_enrichment_json(f"```json\n{VALID_JSON}\n```")
    assert result.summary == "Test article about climate policy changes."


def test_parse_clamps_sentiment():
    """Sentiment values outside [-1, 1] are clamped."""
    data = {
        "summary": "test",
        "entities": [],
        "claims": [],
        "framing": "test",
        "sentiment": 5.0,
        "topic_tags": [],
    }
    result = _parse_enrichment_json(json.dumps(data))
    assert result.sentiment == 1.0

    data["sentiment"] = -5.0
    result = _parse_enrichment_json(json.dumps(data))
    assert result.sentiment == -1.0


def test_parse_invalid_entity_type_skipped():
    """Entities with invalid type are skipped, not crashed."""
    data = {
        "summary": "test",
        "entities": [
            {"name": "Good", "type": "person", "role": "subject"},
            {"name": "Bad", "type": "invalid_type", "role": "subject"},
        ],
        "claims": [],
        "framing": "test",
        "sentiment": 0.0,
        "topic_tags": [],
    }
    result = _parse_enrichment_json(json.dumps(data))
    assert len(result.entities) == 1
    assert result.entities[0].name == "Good"


def test_parse_missing_optional_fields():
    """Missing optional fields get defaults."""
    data = {
        "summary": "test",
        "framing": "test",
        "sentiment": 0.0,
    }
    result = _parse_enrichment_json(json.dumps(data))
    assert result.entities == []
    assert result.claims == []
    assert result.topic_tags == []


def test_parse_invalid_json_raises():
    with pytest.raises(json.JSONDecodeError):
        _parse_enrichment_json("not json at all")
