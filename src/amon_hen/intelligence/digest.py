"""Daily intelligence digest generation."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from amon_hen.enrichment.llm import LLMProvider
from amon_hen.models import DailyDigest, NarrativeCluster, RawItem, SourceType
from amon_hen.storage.sqlite import SQLiteStore

logger = logging.getLogger(__name__)

DIGEST_PROMPT = """You are an intelligence analyst. Generate a concise daily intelligence digest based on the following narrative clusters, source divergences, and anomalies.

CLUSTERS:
{clusters_text}

DIVERGENCES:
{divergences_text}

ANOMALIES:
{anomalies_text}

Write a clear, professional intelligence digest that:
1. Highlights the most significant narratives
2. Notes any source disagreements (divergences)
3. Flags anomalies and emerging trends
4. Is structured with clear sections

Keep it under 500 words. Write in professional intelligence briefing style."""


class DigestGenerator:
    """Generate daily intelligence digests from cluster analysis."""

    def __init__(self, llm: LLMProvider, sqlite: SQLiteStore):
        self.llm = llm
        self.sqlite = sqlite

    async def generate(
        self,
        clusters: list[NarrativeCluster],
        divergences: list[dict],
        anomalies: list[dict],
    ) -> DailyDigest:
        """Generate and store a daily digest."""
        # Build context for the LLM
        clusters_text = ""
        for c in clusters[:10]:
            clusters_text += (
                f"\n- {c.label} ({c.item_count} items, status={c.status.value})\n"
                f"  Summary: {c.summary}\n"
                f"  Sources: {json.dumps(c.source_distribution)}\n"
                f"  Key entities: {', '.join(c.key_entities[:5])}\n"
            )

        divergences_text = ""
        for d in divergences[:5]:
            divergences_text += f"\n- {d['description']}"

        anomalies_text = ""
        for a in anomalies[:5]:
            anomalies_text += f"\n- {a['description']}"

        if not clusters_text:
            clusters_text = "No active clusters."
        if not divergences_text:
            divergences_text = "No divergences detected."
        if not anomalies_text:
            anomalies_text = "No anomalies detected."

        prompt_text = DIGEST_PROMPT.format(
            clusters_text=clusters_text,
            divergences_text=divergences_text,
            anomalies_text=anomalies_text,
        )

        # Use LLM to generate digest
        prompt_item = RawItem(
            source_type=SourceType.RSS,
            source_name="digest_generator",
            source_url="internal://daily-digest",
            content_text=prompt_text,
            published_at=datetime.now(timezone.utc),
        )

        try:
            result, cost_entry = await self.llm.enrich(prompt_item)
            content = result.summary
        except Exception as e:
            logger.error(f"Digest generation failed: {e}")
            content = self._fallback_digest(clusters, divergences, anomalies)

        total_items = sum(c.item_count for c in clusters)
        digest = DailyDigest(
            generated_at=datetime.now(timezone.utc),
            content=content,
            cluster_count=len(clusters),
            item_count=total_items,
            model=getattr(self.llm, "model", "unknown"),
        )

        self.sqlite.insert_digest(digest)
        logger.info(f"Generated digest with {len(clusters)} clusters, {total_items} items")
        return digest

    def _fallback_digest(
        self,
        clusters: list[NarrativeCluster],
        divergences: list[dict],
        anomalies: list[dict],
    ) -> str:
        """Generate a simple digest without LLM."""
        lines = [f"# Intelligence Digest — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"]
        lines.append(f"\n## Active Narratives ({len(clusters)} clusters)")
        for c in clusters[:10]:
            lines.append(f"- **{c.label}** ({c.item_count} items): {c.summary}")
        if divergences:
            lines.append(f"\n## Source Divergences ({len(divergences)})")
            for d in divergences[:5]:
                lines.append(f"- {d['description']}")
        if anomalies:
            lines.append(f"\n## Anomalies ({len(anomalies)})")
            for a in anomalies[:5]:
                lines.append(f"- {a['description']}")
        return "\n".join(lines)
