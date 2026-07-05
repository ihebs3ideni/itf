"""The Device Under Test: the runtime composition result (the "WHAT" plane).

The DUT is not predefined. It is a *view* over the resolved dependency graph,
backed by a single session-lived :class:`~ctf.assembly.Assembly`. Resources are
resolved **lazily** on first :meth:`DUT.require` and cached for the whole run,
so a test only pays for the capabilities it uses while resolution stays
deterministic.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from ctf.assembly import Assembly, RunMode, analyze
from ctf.registry import Registry
from ctf.resolver import GraphResolver


class DUT:
    """A runtime composition of resolved resources."""

    def __init__(self, assembly: Assembly) -> None:
        self._assembly = assembly

    def require(self, contract: str) -> Any:
        """Resolve, instantiate (if needed), and return ``contract``'s resource."""
        return self._assembly.get(contract)

    def invalidate(self, contract: str) -> tuple[str, ...]:
        """Recover from a failed node: drop it and its transitive dependents.

        Tears down ``contract`` and everything that (transitively) requires it,
        in reverse instantiation order, so no stale handle survives over a
        re-flashed or re-provisioned resource. Rebuilding is lazy -- a test
        recovers by *re-requiring* the capability it needs, which re-realizes
        the invalidated subtree from scratch. Returns the torn-down contracts.
        """
        return self._assembly.invalidate(contract)

    def provides(self) -> frozenset[str]:
        """All contracts this DUT can resolve."""
        return self._assembly.registry.contracts()

    def can_provide(self, contract: str) -> bool:
        return self._assembly.registry.has(contract)

    def available(self, contract: str) -> bool:
        """Whether ``contract`` fully resolves (False for unavailable additive)."""
        return self._assembly.available(contract)

    def materialized(self) -> dict[str, Any]:
        """Resources instantiated so far in the session."""
        return self._assembly.materialized()


def build_manager(registry: Registry, mode: RunMode = RunMode.LOOSE) -> Assembly:
    """Validate the graph and build the session :class:`Assembly`.

    ``mode`` governs only *additive* capabilities: in ``LOOSE`` (default) an
    unmet additive provider is recorded as unavailable rather than failing the
    run. Without a declared anchor there is no spine, so ``LOOSE`` behaves like
    ``STRICT`` and every provider must resolve.
    """
    resolver = GraphResolver(registry)
    plan = analyze(registry, resolver, mode)
    return Assembly(registry, resolver, plan)


@contextmanager
def compose(registry: Registry, mode: RunMode = RunMode.LOOSE) -> Iterator[DUT]:
    """Programmatic composition (for non-pytest use).

    Enters the session, yields a :class:`DUT`, and tears every resolved resource
    down in reverse instantiation order on exit.
    """
    assembly = build_manager(registry, mode)
    assembly.enter()
    try:
        yield DUT(assembly)
    finally:
        assembly.exit()
