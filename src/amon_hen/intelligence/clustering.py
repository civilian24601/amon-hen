"""Narrative clustering pipeline using HDBSCAN."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import numpy as np
from sklearn.cluster import HDBSCAN

from amon_hen.config import ClusteringConfig
from amon_hen.enrichment.llm import LLMProvider
from amon_hen.models import ClusterStatus, EnrichedItem, NarrativeCluster
from amon_hen.storage.sqlite import SQLiteStore
from amon_hen.storage.vectors import VectorStore

logger = logging.getLogger(__name__)


class ClusteringPipeline:
    """Run HDBSCAN clustering on enriched items, manage cluster lifecycle."""

    def __init__(
        self,
        config: ClusteringConfig,
        sqlite: SQLiteStore,
        vectors: VectorStore,
        llm: LLMProvider | None = None,
    ):
        self.config = config
        self.sqlite = sqlite
        self.vectors = vectors
        self.llm = llm

    async def run(self) -> list[NarrativeCluster]:
        """Full clustering cycle: cluster -> label -> match -> persist."""
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=self.config.rolling_window_days)
        since_str = since.isoformat()

        # 1. Pull all vectors from Qdrant
        point_ids, vectors_list = self.vectors.get_all_vectors(since=since_str)
        if len(point_ids) < self.config.min_cluster_size:
            logger.info(
                f"Only {len(point_ids)} items in window — need at least "
                f"{self.config.min_cluster_size} for clustering"
            )
            return []

        X = np.array(vectors_list)

        # 2. Run HDBSCAN
        clusterer = HDBSCAN(
            min_cluster_size=self.config.min_cluster_size,
            min_samples=self.config.min_samples,
            metric="cosine",
        )
        labels = clusterer.fit_predict(X)

        # 3. Group items by cluster label (skip noise = -1)
        cluster_groups: dict[int, list[int]] = {}
        for idx, label in enumerate(labels):
            if label == -1:
                continue
            cluster_groups.setdefault(label, []).append(idx)

        logger.info(
            f"HDBSCAN found {len(cluster_groups)} clusters from {len(point_ids)} points "
            f"({sum(1 for l in labels if l == -1)} noise)"
        )

        # 4. Batch-load all items from SQLite
        all_items: dict[str, EnrichedItem] = {}
        for pid in point_ids:
            item = self.sqlite.get_item(pid)
            if item:
                all_items[pid] = item

        # 5. Build new clusters
        new_clusters: list[NarrativeCluster] = []
        for cluster_label, indices in cluster_groups.items():
            member_ids = [point_ids[i] for i in indices]
            member_items = [all_items[mid] for mid in member_ids if mid in all_items]
            if not member_items:
                continue

            # Compute centroid
            cluster_vecs = X[indices]
            centroid = cluster_vecs.mean(axis=0)
            centroid_list = centroid.tolist()

            # Get 5 closest items to centroid for labeling
            distances = np.linalg.norm(cluster_vecs - centroid, axis=1)
            closest_indices = distances.argsort()[:5]
            representative_items = [member_items[i] for i in closest_indices if i < len(member_items)]

            # Label cluster (LLM or fallback)
            label_text, summary_text = await self._label_cluster(representative_items)

            # Source distribution
            source_dist: dict[str, int] = {}
            for item in member_items:
                key = item.source_type.value
                source_dist[key] = source_dist.get(key, 0) + 1

            # Sentiment distribution
            sentiment_dist = _bin_sentiment([item.sentiment for item in member_items])

            # Key entities and claims
            entity_counts: dict[str, int] = {}
            all_claims: list[str] = []
            for item in member_items:
                for entity in item.entities:
                    entity_counts[entity.name] = entity_counts.get(entity.name, 0) + 1
                all_claims.extend(item.claims)
            key_entities = sorted(entity_counts, key=entity_counts.get, reverse=True)[:10]
            key_claims = list(dict.fromkeys(all_claims))[:10]  # Deduplicated, ordered

            cluster = NarrativeCluster(
                label=label_text,
                summary=summary_text,
                item_count=len(member_items),
                first_seen=min(i.published_at for i in member_items),
                last_updated=now,
                centroid=centroid_list,
                source_distribution=source_dist,
                sentiment_distribution=sentiment_dist,
                key_entities=key_entities,
                key_claims=key_claims,
                status=ClusterStatus.EMERGING,
            )
            cluster._member_ids = member_ids  # Temporary for matching
            new_clusters.append(cluster)

        # 6. Match to previous clusters
        previous_clusters = self.sqlite.get_active_clusters()
        self._match_clusters(new_clusters, previous_clusters)

        # 7. Persist
        self.sqlite.clear_cluster_memberships()
        for cluster in new_clusters:
            self.sqlite.upsert_cluster(cluster)
            member_ids = getattr(cluster, "_member_ids", [])
            for mid in member_ids:
                self.sqlite.set_cluster_membership(mid, cluster.id)
                self.sqlite.update_item_cluster(mid, cluster.id, cluster.label)

        # Mark clusters that disappeared as fading
        new_ids = {c.id for c in new_clusters}
        for prev in previous_clusters:
            if prev.id not in new_ids:
                self.sqlite.update_cluster_status(prev.id, ClusterStatus.FADING.value)

        logger.info(f"Persisted {len(new_clusters)} clusters")
        return new_clusters

    async def _label_cluster(
        self, representative_items: list[EnrichedItem]
    ) -> tuple[str, str]:
        """Generate cluster label and summary from representative items."""
        if self.llm is None:
            # Fallback: use first item's summary as label
            if representative_items:
                first = representative_items[0]
                return first.summary[:80], first.summary
            return "Unlabeled Cluster", "No representative items."

        # Build prompt from representative items
        items_text = ""
        for i, item in enumerate(representative_items[:5], 1):
            items_text += f"\n{i}. Summary: {item.summary}\n   Framing: {item.framing}\n"

        from amon_hen.models import RawItem, SourceType

        prompt_item = RawItem(
            source_type=SourceType.RSS,
            source_name="cluster_labeling",
            source_url="internal://cluster-label",
            content_text=(
                f"Generate a short narrative cluster label (max 10 words) and a 2-sentence "
                f"summary for this group of related items:\n{items_text}\n\n"
                f"Respond with JSON: {{\"label\": \"...\", \"summary\": \"...\"}}"
            ),
            published_at=datetime.now(timezone.utc),
        )

        try:
            result, _ = await self.llm.enrich(prompt_item)
            # Use the summary field as both label and summary
            return result.summary[:80], result.summary
        except Exception as e:
            logger.warning(f"Cluster labeling failed: {e}")
            if representative_items:
                return representative_items[0].summary[:80], representative_items[0].summary
            return "Unlabeled Cluster", "Labeling failed."

    def _match_clusters(
        self,
        new_clusters: list[NarrativeCluster],
        previous_clusters: list[NarrativeCluster],
    ) -> None:
        """Match new clusters to previous ones via Jaccard overlap on member IDs.

        Rules:
        - >70% overlap = same cluster (inherit ID, status -> active)
        - <50% retained = fading (handled in caller)
        - No match = emerging (default)
        """
        if not previous_clusters:
            return

        # Build previous membership sets
        prev_members: dict[str, set[str]] = {}
        for pc in previous_clusters:
            items = self.sqlite.get_items_by_cluster(pc.id)
            prev_members[pc.id] = {i.id for i in items}

        used_prev = set()

        for nc in new_clusters:
            nc_members = set(getattr(nc, "_member_ids", []))
            if not nc_members:
                continue

            best_overlap = 0.0
            best_prev_id = None

            for pc in previous_clusters:
                if pc.id in used_prev:
                    continue
                pm = prev_members.get(pc.id, set())
                if not pm:
                    continue
                overlap = len(nc_members & pm) / len(nc_members | pm)  # Jaccard
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_prev_id = pc.id

            if best_overlap > 0.7 and best_prev_id:
                # Same cluster — inherit ID, promote to active
                nc.id = best_prev_id
                nc.status = ClusterStatus.ACTIVE
                # Preserve first_seen from the previous cluster
                for pc in previous_clusters:
                    if pc.id == best_prev_id:
                        nc.first_seen = pc.first_seen
                        break
                used_prev.add(best_prev_id)
            # else: remains emerging (default)


def _bin_sentiment(values: list[float]) -> dict[str, int]:
    """Bin sentiment values into distribution buckets."""
    bins = {
        "very_negative": 0,
        "negative": 0,
        "neutral": 0,
        "positive": 0,
        "very_positive": 0,
    }
    for v in values:
        if v <= -0.6:
            bins["very_negative"] += 1
        elif v <= -0.2:
            bins["negative"] += 1
        elif v <= 0.2:
            bins["neutral"] += 1
        elif v <= 0.6:
            bins["positive"] += 1
        else:
            bins["very_positive"] += 1
    return bins
