"""Anomaly detection for narrative intelligence."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from amon_hen.models import NarrativeCluster
from amon_hen.storage.sqlite import SQLiteStore

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """Detect volume spikes, sentiment shifts, and entity surges."""

    def __init__(self, sqlite: SQLiteStore):
        self.sqlite = sqlite

    def detect_volume_spikes(
        self, clusters: list[NarrativeCluster]
    ) -> list[dict]:
        """Detect clusters with 6h item count > 3x rolling 7-day average hourly rate."""
        anomalies = []
        now = datetime.now(timezone.utc)
        six_hours_ago = now - timedelta(hours=6)
        seven_days_ago = now - timedelta(days=7)

        for cluster in clusters:
            items = self.sqlite.get_items_by_cluster(cluster.id)
            if not items:
                continue

            recent_count = sum(
                1 for i in items if i.published_at >= six_hours_ago
            )
            week_count = sum(
                1 for i in items if i.published_at >= seven_days_ago
            )
            avg_hourly = week_count / (7 * 24) if week_count > 0 else 0
            six_hour_rate = recent_count / 6.0

            if avg_hourly > 0 and six_hour_rate > 3 * avg_hourly:
                anomalies.append(
                    {
                        "type": "volume_spike",
                        "cluster_id": cluster.id,
                        "cluster_label": cluster.label,
                        "recent_6h_count": recent_count,
                        "avg_hourly_7d": round(avg_hourly, 2),
                        "spike_ratio": round(six_hour_rate / avg_hourly, 2),
                        "description": (
                            f"Volume spike in '{cluster.label}': "
                            f"{recent_count} items in 6h vs {avg_hourly:.1f}/h avg"
                        ),
                    }
                )

        return anomalies

    def detect_sentiment_shifts(
        self, clusters: list[NarrativeCluster]
    ) -> list[dict]:
        """Detect clusters where avg sentiment changed > 0.5 in 24h."""
        anomalies = []
        now = datetime.now(timezone.utc)
        one_day_ago = now - timedelta(hours=24)
        two_days_ago = now - timedelta(hours=48)

        for cluster in clusters:
            items = self.sqlite.get_items_by_cluster(cluster.id)
            if not items:
                continue

            recent = [i.sentiment for i in items if i.published_at >= one_day_ago]
            older = [
                i.sentiment
                for i in items
                if two_days_ago <= i.published_at < one_day_ago
            ]

            if not recent or not older:
                continue

            avg_recent = sum(recent) / len(recent)
            avg_older = sum(older) / len(older)
            shift = avg_recent - avg_older

            if abs(shift) > 0.5:
                anomalies.append(
                    {
                        "type": "sentiment_shift",
                        "cluster_id": cluster.id,
                        "cluster_label": cluster.label,
                        "sentiment_before": round(avg_older, 3),
                        "sentiment_after": round(avg_recent, 3),
                        "shift": round(shift, 3),
                        "description": (
                            f"Sentiment shift in '{cluster.label}': "
                            f"{avg_older:.2f} -> {avg_recent:.2f} ({'+' if shift > 0 else ''}{shift:.2f})"
                        ),
                    }
                )

        return anomalies

    def detect_entity_surges(self) -> list[dict]:
        """Detect entities appearing in >10 items within 6 hours."""
        anomalies = []
        now = datetime.now(timezone.utc)
        six_hours_ago = now - timedelta(hours=6)

        recent_items = self.sqlite.get_items(since=six_hours_ago, limit=1000)
        entity_items: dict[str, int] = {}
        for item in recent_items:
            for entity in item.entities:
                entity_items[entity.name] = entity_items.get(entity.name, 0) + 1

        for entity_name, count in entity_items.items():
            if count > 10:
                anomalies.append(
                    {
                        "type": "entity_surge",
                        "entity_name": entity_name,
                        "count_6h": count,
                        "description": (
                            f"Entity surge: '{entity_name}' in {count} items in 6h"
                        ),
                    }
                )

        return anomalies
