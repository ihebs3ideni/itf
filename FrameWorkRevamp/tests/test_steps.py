from __future__ import annotations

import pytest

from ctf.errors import StepCollisionError
from ctf.steps import ArtifactSink, Policy, StepContext, StepRegistry


def _ctx():
    return StepContext(dut=None, registry=None, artifacts=ArtifactSink())


def test_fanout_runs_all_in_order():
    steps = StepRegistry()
    steps.declare("p", Policy.FANOUT)
    calls: list[str] = []
    steps.add("p", lambda c: calls.append("b") or "b", order=20, name="b")
    steps.add("p", lambda c: calls.append("a") or "a", order=10, name="a")

    results = steps.resolve("p", _ctx())
    assert calls == ["a", "b"]  # ordered by (order, name)
    assert results == [("a", "a"), ("b", "b")]


def test_fanout_reverse():
    steps = StepRegistry()
    steps.declare("p", Policy.FANOUT)
    calls: list[str] = []
    steps.add("p", lambda c: calls.append("a"), order=10, name="a")
    steps.add("p", lambda c: calls.append("b"), order=20, name="b")

    steps.resolve("p", _ctx(), reverse=True)
    assert calls == ["b", "a"]


def test_first_stops_at_first_non_none():
    steps = StepRegistry()
    steps.declare("p", Policy.FIRST)
    calls: list[str] = []

    def a(c):
        calls.append("a")
        return None  # declines

    def b(c):
        calls.append("b")
        return "handled"

    def d(c):  # should never run
        calls.append("d")
        return "nope"

    steps.add("p", a, order=10, name="a")
    steps.add("p", b, order=20, name="b")
    steps.add("p", d, order=30, name="d")

    assert steps.resolve("p", _ctx()) == "handled"
    assert calls == ["a", "b"]


def test_first_returns_none_when_all_decline():
    steps = StepRegistry()
    steps.declare("p", Policy.FIRST)
    steps.add("p", lambda c: None)
    assert steps.resolve("p", _ctx()) is None


def test_unique_allows_single():
    steps = StepRegistry()
    steps.declare("p", Policy.UNIQUE)
    steps.add("p", lambda c: "only")
    assert steps.resolve("p", _ctx()) == "only"


def test_unique_fails_on_collision():
    steps = StepRegistry()
    steps.declare("p", Policy.UNIQUE)
    steps.add("p", lambda c: 1, name="first")
    steps.add("p", lambda c: 2, name="second")

    with pytest.raises(StepCollisionError) as exc:
        steps.resolve("p", _ctx())
    assert exc.value.point == "p"
    assert set(exc.value.contributors) == {"first", "second"}


def test_unique_empty_returns_none():
    steps = StepRegistry()
    steps.declare("p", Policy.UNIQUE)
    assert steps.resolve("p", _ctx()) is None


def test_builtin_points_have_expected_policies():
    steps = StepRegistry()
    # Provisioning fans out: many independent provision verbs, no single owner.
    assert steps.policy("ctf_provision") is Policy.FANOUT
    assert steps.policy("ctf_after_test") is Policy.FANOUT
    # Unknown points default to FANOUT.
    assert steps.policy("something/custom") is Policy.FANOUT


def test_context_require_and_publish_delegate():
    class FakeDut:
        def require(self, c):
            return f"res:{c}"

    class FakeRegistry:
        def __init__(self):
            self.published = []

        def add_descriptor(self, d):
            self.published.append(d)

    registry = FakeRegistry()
    ctx = StepContext(dut=FakeDut(), registry=registry, artifacts=ArtifactSink())
    assert ctx.require("x") == "res:x"
    ctx.publish("desc")
    assert registry.published == ["desc"]
