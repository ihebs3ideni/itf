from __future__ import annotations

import pytest

from ctf.contracts import build_provider, provides
from ctf.errors import CompositionError
from ctf.lifecycle import LifecycleScope


def test_plain_provider_returns_value():
    @provides("x")
    def factory():
        return 7

    scope = LifecycleScope()
    assert scope.instantiate(build_provider(factory), []) == 7
    scope.close()


def test_generator_teardown_runs_in_reverse():
    events: list[str] = []

    @provides("a")
    def a():
        events.append("setup-a")
        yield "a"
        events.append("teardown-a")

    @provides("b")
    def b():
        events.append("setup-b")
        yield "b"
        events.append("teardown-b")

    scope = LifecycleScope()
    scope.instantiate(build_provider(a), [])
    scope.instantiate(build_provider(b), [])
    assert events == ["setup-a", "setup-b"]

    scope.close()
    assert events == ["setup-a", "setup-b", "teardown-b", "teardown-a"]


def test_close_is_idempotent():
    scope = LifecycleScope()
    scope.close()
    scope.close()  # must not raise


def test_instantiate_after_close_fails():
    @provides("x")
    def factory():
        return 1

    scope = LifecycleScope()
    scope.close()
    with pytest.raises(CompositionError):
        scope.instantiate(build_provider(factory), [])


def test_teardown_errors_aggregated():
    @provides("x")
    def factory():
        yield 1
        raise RuntimeError("boom")

    scope = LifecycleScope()
    scope.instantiate(build_provider(factory), [])
    with pytest.raises(CompositionError):
        scope.close()


def test_context_manager():
    events: list[str] = []

    @provides("x")
    def factory():
        yield 1
        events.append("down")

    with LifecycleScope() as scope:
        scope.instantiate(build_provider(factory), [])
    assert events == ["down"]
