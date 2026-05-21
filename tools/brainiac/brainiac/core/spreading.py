from __future__ import annotations


def spread_activation(
    seeds: dict[str, float],
    edges: dict[str, list[tuple[str, float]]],
    *,
    max_hops: int = 3,
    decay: float = 0.5,
    epsilon: float = 0.01,
    floor: float = 0.05,
) -> dict[str, float]:
    """Iterative spreading activation over a directed weighted graph.

    Formula: a_j(t+1) = a_j(t) + decay * Σ_i a_i(t) * w_ij

    Args:
        seeds: initial activation per node {note_id: score}
        edges: adjacency list {src: [(dst, weight), ...]}
        max_hops: max iterations (stops early on convergence)
        decay: attenuation factor per hop (γ in [0,1])
        epsilon: convergence threshold on max delta
        floor: minimum activation to include in output

    Returns:
        {note_id: final_activation} filtered by floor.
    """
    if not seeds:
        return {}

    a: dict[str, float] = dict(seeds)
    for _ in range(max_hops):
        delta: dict[str, float] = {}
        for src, score in list(a.items()):
            for dst, weight in edges.get(src, []):
                delta[dst] = delta.get(dst, 0.0) + decay * score * weight

        if not delta:
            break

        max_change = 0.0
        for dst, contrib in delta.items():
            a[dst] = a.get(dst, 0.0) + contrib
            if abs(contrib) > max_change:
                max_change = abs(contrib)

        if max_change < epsilon:
            break

    return {nid: score for nid, score in a.items() if score >= floor}
