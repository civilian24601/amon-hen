"""LLM enrichment providers for Amon Hen."""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod

from amon_hen.config import Settings
from amon_hen.models import (
    CostLogEntry,
    EnrichmentResult,
    Entity,
    EntityRole,
    EntityType,
    RawItem,
)

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 4000

ENRICHMENT_PROMPT = """Analyze the following news/social media content and extract structured intelligence.

CONTENT:
{content}

Respond with a JSON object containing exactly these fields:
{{
  "summary": "2-3 sentence summary of the key narrative",
  "entities": [
    {{"name": "entity name", "type": "person|org|place|event", "role": "subject|target|source|location|mentioned", "aliases": []}}
  ],
  "claims": ["list of factual claims or assertions made"],
  "framing": "how the narrative is framed (e.g., 'crisis framing', 'progress narrative', 'conflict framing')",
  "sentiment": 0.0,
  "topic_tags": ["relevant", "topic", "tags"]
}}

Rules:
- sentiment must be a float between -1.0 (very negative) and 1.0 (very positive)
- Include 1-5 entities with accurate types and roles
- Include 1-5 claims that are specific assertions from the content
- Respond with ONLY the JSON object, no other text"""


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence (possibly with language tag)
        text = re.sub(r"^```\w*\n?", "", text)
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _parse_enrichment_json(raw: str) -> EnrichmentResult:
    """Parse LLM JSON output into EnrichmentResult."""
    cleaned = _strip_code_fences(raw)
    data = json.loads(cleaned)

    entities = []
    for e in data.get("entities", []):
        try:
            entities.append(
                Entity(
                    name=e["name"],
                    type=EntityType(e.get("type", "person")),
                    role=EntityRole(e.get("role", "mentioned")),
                    aliases=e.get("aliases", []),
                )
            )
        except (ValueError, KeyError):
            continue

    sentiment = float(data.get("sentiment", 0.0))
    sentiment = max(-1.0, min(1.0, sentiment))

    return EnrichmentResult(
        summary=data.get("summary", ""),
        entities=entities,
        claims=data.get("claims", []),
        framing=data.get("framing", ""),
        sentiment=sentiment,
        topic_tags=data.get("topic_tags", []),
    )


class LLMProvider(ABC):
    """Abstract base for LLM enrichment providers."""

    @abstractmethod
    async def enrich(self, item: RawItem) -> tuple[EnrichmentResult, CostLogEntry]:
        ...


class AnthropicProvider(LLMProvider):
    """Claude Haiku enrichment provider."""

    # Haiku pricing per token (as of 2025)
    # Verify from https://docs.anthropic.com/en/docs/about-claude/models
    INPUT_COST_PER_TOKEN = 0.80 / 1_000_000   # $0.80 per 1M input tokens
    OUTPUT_COST_PER_TOKEN = 4.00 / 1_000_000  # $4.00 per 1M output tokens

    def __init__(self, settings: Settings):
        import anthropic
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.enrichment.model

    async def enrich(self, item: RawItem) -> tuple[EnrichmentResult, CostLogEntry]:
        content = item.content_text[:MAX_CONTENT_CHARS]
        prompt = ENRICHMENT_PROMPT.format(content=content)

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        # Calculate cost
        cost = (
            input_tokens * self.INPUT_COST_PER_TOKEN
            + output_tokens * self.OUTPUT_COST_PER_TOKEN
        )

        # Parse response — retry once on failure
        try:
            result = _parse_enrichment_json(raw_text)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"First parse failed for item {item.id}: {e}, retrying...")
            # Retry with explicit instruction
            retry_response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": raw_text},
                    {
                        "role": "user",
                        "content": "Your response was not valid JSON. Please respond with ONLY a valid JSON object.",
                    },
                ],
            )
            retry_text = retry_response.content[0].text
            input_tokens += retry_response.usage.input_tokens
            output_tokens += retry_response.usage.output_tokens
            cost += (
                retry_response.usage.input_tokens * self.INPUT_COST_PER_TOKEN
                + retry_response.usage.output_tokens * self.OUTPUT_COST_PER_TOKEN
            )
            result = _parse_enrichment_json(retry_text)

        cost_entry = CostLogEntry(
            item_id=item.id,
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )
        return result, cost_entry


class OllamaProvider(LLMProvider):
    """Local Ollama LLM enrichment provider (zero cost)."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        import httpx
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.AsyncClient(timeout=120.0)

    async def enrich(self, item: RawItem) -> tuple[EnrichmentResult, CostLogEntry]:
        content = item.content_text[:MAX_CONTENT_CHARS]
        prompt = ENRICHMENT_PROMPT.format(content=content)

        response = await self._client.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "format": "json",
                "stream": False,
            },
        )
        response.raise_for_status()
        data = response.json()
        raw_text = data.get("response", "")

        result = _parse_enrichment_json(raw_text)
        cost_entry = CostLogEntry(
            item_id=item.id,
            model=f"ollama:{self.model}",
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
        )
        return result, cost_entry


def get_provider(settings: Settings) -> LLMProvider:
    """Factory for LLM provider based on config."""
    if settings.enrichment.provider == "ollama":
        return OllamaProvider()
    return AnthropicProvider(settings)
