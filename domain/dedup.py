"""L2 maths (docs/02): cosine similarity and greedy leader clustering."""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


@dataclass
class Cluster:
    cluster_id: str
    leader: int  # index into the input sequence
    members: list[int]  # indexes, leader excluded

    @property
    def duplicates_count(self) -> int:
        return len(self.members)


def greedy_clusters(
    vectors: Sequence[Sequence[float]],
    scores: Sequence[float],
    threshold: float,
    run_id: str,
) -> list[Cluster]:
    """Highest score first becomes leader; every unassigned item with cos ≥ τ to it joins.

    Leaders are returned in score order, with cluster ids ``{run_id}_c{n}``.
    """
    order = sorted(range(len(vectors)), key=lambda i: scores[i], reverse=True)
    assigned: set[int] = set()
    clusters: list[Cluster] = []
    for i in order:
        if i in assigned:
            continue
        assigned.add(i)
        members = []
        for j in order:
            if j in assigned:
                continue
            if cosine(vectors[i], vectors[j]) >= threshold:
                assigned.add(j)
                members.append(j)
        clusters.append(Cluster(f"{run_id}_c{len(clusters)}", i, members))
    return clusters


def novelty_score(max_cosine: float | None) -> float:
    """``1 − max cosine`` against the 90-day history; 1.0 = never proposed before."""
    return 1.0 if max_cosine is None else max(0.0, 1.0 - max_cosine)
