"""Recovery: a live DUT can be re-driven mid-run (messy-HW recovery).

``dut.invalidate(contract)`` drops a cached node *and its transitive dependents*,
tearing them down in reverse instantiation order so no stale handle survives over
a re-flashed box. Rebuilding is lazy: re-requiring the capability re-realizes the
invalidated subtree from scratch -- the reflash / reprovision story, keyed on a
contract rather than a declared phase.
"""

from __future__ import annotations

from ctf.contracts import provides, requires
from ctf.descriptor import Descriptor
from ctf.dut import build_manager
from ctf.registry import Registry
from ctf.target import TARGET_ANCHOR


def _ladder(events: list[str]) -> Registry:
    registry = Registry()
    registry.add_descriptor(Descriptor("ctf/env/testbench", value="bench"))

    @registry.register
    @provides(TARGET_ANCHOR)
    @requires("ctf/env/testbench")
    def target(bench):
        events.append("target-up")
        yield "target"
        events.append("target-down")

    @registry.register
    @provides("ctf/target/reachable")
    @requires(TARGET_ANCHOR)
    def conn(target):
        events.append("conn-up")
        yield f"conn:{target}"
        events.append("conn-down")

    @registry.register
    @provides("ctf/sec/token")
    @requires("ctf/target/reachable")
    def token(conn):
        events.append("token-up")
        yield "token"
        events.append("token-down")

    @registry.register
    @provides("ctf/cap/exec")
    @requires("ctf/sec/token")
    def exec_cap(token):
        events.append("exec-up")
        yield f"exec[{token}]"
        events.append("exec-down")

    return registry


def test_invalidate_tears_down_node_and_dependents_then_lazily_rebuilds():
    events: list[str] = []
    manager = build_manager(_ladder(events))
    manager.enter()
    manager.realize()
    events.clear()

    # Re-provision: token + everything above it torn down (reverse), nothing
    # below touched. Rebuild is lazy on the next require.
    torn = manager.invalidate("ctf/sec/token")
    assert torn == ("ctf/cap/exec", "ctf/sec/token")
    assert events == ["exec-down", "token-down"]
    assert "ctf/sec/token" not in manager.materialized()
    assert "ctf/target/reachable" in manager.materialized()

    manager.get("ctf/cap/exec")
    assert events == ["exec-down", "token-down", "token-up", "exec-up"]

    manager.exit()


def test_invalidate_leaf_reruns_only_itself():
    events: list[str] = []
    manager = build_manager(_ladder(events))
    manager.enter()
    manager.realize()
    events.clear()

    manager.invalidate("ctf/cap/exec")
    assert events == ["exec-down"]
    manager.get("ctf/cap/exec")
    assert events == ["exec-down", "exec-up"]

    manager.exit()


def test_invalidate_root_cascades_reverse_then_lazily_rebuilds():
    events: list[str] = []
    manager = build_manager(_ladder(events))
    manager.enter()
    manager.realize()
    events.clear()

    # Reflash: invalidating the anchor tears down exec->token->conn->target
    # (reverse), preserving the earlier substrate fact.
    torn = manager.invalidate(TARGET_ANCHOR)
    assert torn == (
        "ctf/cap/exec",
        "ctf/sec/token",
        "ctf/target/reachable",
        TARGET_ANCHOR,
    )
    assert events == ["exec-down", "token-down", "conn-down", "target-down"]

    manager.get("ctf/cap/exec")
    assert events[-4:] == ["target-up", "conn-up", "token-up", "exec-up"]

    manager.exit()


def test_invalidate_preserves_upstream_facts():
    events: list[str] = []
    manager = build_manager(_ladder(events))
    manager.enter()
    manager.realize()

    # The substrate fact is upstream of the anchor, so invalidating the anchor
    # must not disturb it.
    manager.invalidate(TARGET_ANCHOR)
    assert manager.materialized()["ctf/env/testbench"] == "bench"

    manager.exit()


def test_invalidate_is_noop_when_not_cached():
    events: list[str] = []
    manager = build_manager(_ladder(events))
    manager.enter()

    assert manager.invalidate("ctf/sec/token") == ()
    assert events == []

    manager.exit()


def test_exit_tears_down_everything_after_invalidate():
    events: list[str] = []
    manager = build_manager(_ladder(events))
    manager.enter()
    manager.realize()
    manager.invalidate("ctf/target/reachable")
    events.clear()

    manager.exit()
    # Only what is still live is torn down, in reverse instantiation order.
    assert events == ["target-down"]
