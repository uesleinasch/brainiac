import pytest


def test_spread_empty_seeds_returns_empty():
    from brainiac.core.spreading import spread_activation
    assert spread_activation({}, {}) == {}


def test_spread_no_edges_returns_seeds_unchanged():
    from brainiac.core.spreading import spread_activation
    seeds = {"a": 1.0, "b": 0.5}
    out = spread_activation(seeds, {})
    assert out == seeds


def test_spread_single_hop_propagates_to_neighbor():
    from brainiac.core.spreading import spread_activation
    seeds = {"a": 1.0}
    edges = {"a": [("b", 1.0)]}
    out = spread_activation(seeds, edges, max_hops=1, decay=0.5, floor=0.0)
    # a stays at 1.0, b receives 1.0 * 1.0 * 0.5 = 0.5
    assert out["a"] == pytest.approx(1.0)
    assert out["b"] == pytest.approx(0.5)


def test_spread_two_hops_reaches_grandchildren():
    from brainiac.core.spreading import spread_activation
    seeds = {"a": 1.0}
    edges = {"a": [("b", 1.0)], "b": [("c", 1.0)]}
    out = spread_activation(seeds, edges, max_hops=2, decay=0.5, floor=0.0)
    # hop1: b += 0.5; hop2: c += 0.25 (from b=0.5 * 1.0 * 0.5)
    assert out["c"] == pytest.approx(0.25)


def test_spread_max_hops_caps_iterations():
    from brainiac.core.spreading import spread_activation
    seeds = {"a": 1.0}
    edges = {"a": [("b", 1.0)], "b": [("c", 1.0)], "c": [("d", 1.0)]}
    # max_hops=1: only b is reached
    out = spread_activation(seeds, edges, max_hops=1, decay=0.5, floor=0.0)
    assert "b" in out
    assert "c" not in out
    assert "d" not in out


def test_spread_floor_excludes_low_activation_nodes():
    from brainiac.core.spreading import spread_activation
    seeds = {"a": 1.0}
    edges = {"a": [("b", 0.01)]}  # weight 0.01 → b gets 0.005
    out = spread_activation(seeds, edges, max_hops=1, decay=0.5, floor=0.05)
    assert "b" not in out  # below floor
    assert "a" in out


def test_spread_co_activation_two_paths_sum():
    from brainiac.core.spreading import spread_activation
    # Both a and b link to c with weight 1.0
    seeds = {"a": 1.0, "b": 1.0}
    edges = {"a": [("c", 1.0)], "b": [("c", 1.0)]}
    out = spread_activation(seeds, edges, max_hops=1, decay=0.5, floor=0.0)
    # c receives contributions from both: 0.5 + 0.5 = 1.0
    assert out["c"] == pytest.approx(1.0)


def test_spread_decay_attenuates_per_hop():
    from brainiac.core.spreading import spread_activation
    seeds = {"a": 1.0}
    edges = {"a": [("b", 1.0)]}
    out_high = spread_activation(seeds, edges, max_hops=1, decay=0.9, floor=0.0)
    out_low = spread_activation(seeds, edges, max_hops=1, decay=0.1, floor=0.0)
    assert out_high["b"] > out_low["b"]


def test_spread_convergence_stops_early_when_delta_small():
    from brainiac.core.spreading import spread_activation
    seeds = {"a": 1.0}
    edges = {"a": [("b", 0.0001)]}  # extremely weak edge
    # Should converge after first hop (delta < epsilon)
    out = spread_activation(seeds, edges, max_hops=10, decay=0.5, epsilon=0.01, floor=0.0)
    assert "a" in out
    # b's contribution is below epsilon, may be in dict but tiny
    assert out.get("b", 0.0) < 0.01


def test_spread_self_loop_handled():
    from brainiac.core.spreading import spread_activation
    seeds = {"a": 1.0}
    edges = {"a": [("a", 1.0)]}  # self-loop
    out = spread_activation(seeds, edges, max_hops=2, decay=0.5, floor=0.0)
    assert out["a"] > 1.0  # accumulated via self-link


def test_spread_disconnected_graph_seeds_only():
    from brainiac.core.spreading import spread_activation
    seeds = {"a": 1.0, "b": 1.0}
    edges = {}  # no edges
    out = spread_activation(seeds, edges, max_hops=3, decay=0.5, floor=0.0)
    assert out == {"a": 1.0, "b": 1.0}


def test_spread_high_decay_amplifies_distant_nodes():
    from brainiac.core.spreading import spread_activation
    seeds = {"a": 1.0}
    edges = {"a": [("b", 1.0)], "b": [("c", 1.0)]}
    out_high = spread_activation(seeds, edges, max_hops=2, decay=0.9, floor=0.0)
    out_low = spread_activation(seeds, edges, max_hops=2, decay=0.1, floor=0.0)
    # higher decay → more activation reaches c
    assert out_high["c"] > out_low["c"]
