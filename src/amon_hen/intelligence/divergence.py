"""Source divergence detection within narrative clusters."""

from __future__ import annotations

import logging

import numpy as np

from amon_hen.models import NarrativeCluster
from amon_hen.storage.sqlite import SQLiteStore
from amon_hen.storage.vectors import VectorStore

logger = logging.getLogger(__name__)


class DivergenceDetector:
    """Detect when different source types tell different stories about the same narrative."""

    def __init__(self, threshold: float = 0.3):
        self.threshold = threshold

    def detect(
        self,
        clusters: list[NarrativeCluster],
        sqlite: SQLiteStore,
        vectors: VectorStore,
    ) -> list[dict]:
        """For each cluster, check if source sub-centroids diverge."""
        divergences = []

        for cluster in clusters:
            items = sqlite.get_items_by_cluster(cluster.id)
            if len(items) < 3:
                continue

            # Group by source_type
            source_groups: dict[str, list[str]] = {}
            for item in items:
                key = item.source_type.value
                source_groups.setdefault(key, []).append(item.embedding_id)

            if len(source_groups) < 2:
                continue

            # Get vectors for each group
            all_ids = [eid for ids in source_groups.values() for eid in ids]
            vectors_map = vectors.get_vectors_by_ids(all_ids)

            # Compute sub-centroids
            sub_centroids: dict[str, np.ndarray] = {}
            for source_type, ids in source_groups.items():
                vecs = [vectors_map[eid] for eid in ids if eid in vectors_map]
                if vecs:
                    sub_centroids[source_type] = np.mean(vecs, axis=0)

            if len(sub_centroids) < 2:
                continue

            # Compare all pairs
            sources = list(sub_centroids.keys())
            for i in range(len(sources)):
                for j in range(i + 1, len(sources)):
                    sa, sb = sources[i], sources[j]
                    va = sub_centroids[sa]
                    vb = sub_centroids[sb]
                    # Cosine distance
                    cos_sim = np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb) + 1e-10)
                    cos_dist = 1.0 - cos_sim

                    if cos_dist > self.threshold:
                        divergences.append(
                            {
                                "cluster_id": cluster.id,
                                "cluster_label": cluster.label,
                                "source_a": sa,
                                "source_b": sb,
                                "cosine_distance": round(float(cos_dist), 4),
                                "description": (
                                    f"'{sa}' and '{sb}' sources diverge on "
                                    f"'{cluster.label}' (distance={cos_dist:.3f})"
                                ),
                            }
                        )

        logger.info(f"Divergence detection: {len(divergences)} divergences found")
        return divergences
