"""Deterministic dependency-graph resolution.

Given a registry, the resolver computes a topologically ordered *plan* for a
requested contract: the list of contracts to instantiate, dependencies first,
the requested contract last. Resolution is purely structural -- no factories run
here -- which keeps it side-effect free and trivially testable.

Determinism guarantee: for a fixed registry and requested contract, the plan is
always identical, because ``requires`` order is fixed and the traversal is a
deterministic depth-first walk.
"""

from __future__ import annotations

from score.itf.core.ctf.errors import CyclicDependencyError, UnresolvedContractError
from score.itf.core.ctf.registry import Registry


class GraphResolver:
    """Computes deterministic instantiation plans from a registry."""

    def __init__(self, registry: Registry) -> None:
        self._registry = registry

    def plan(self, contract: str) -> list[str]:
        """Return contracts to instantiate for ``contract``, dependencies first.

        Raises:
            UnresolvedContractError: a contract has no descriptor/provider.
            CyclicDependencyError: the dependency graph contains a cycle.
        """
        order: list[str] = []
        done: set[str] = set()
        self._visit(contract, required_by=None, on_stack=[], seen=set(), order=order, done=done)
        return order

    def validate(self) -> None:
        """Eagerly resolve every provider to surface graph errors up front."""
        for provider in self._registry.providers():
            self.plan(provider.provides)

    def dependents(self, contract: str) -> frozenset[str]:
        """Return ``contract`` plus every contract that transitively requires it.

        Computes the reverse-dependency closure by asking, for each registered
        contract, whether ``contract`` appears in *its* instantiation plan. The
        result therefore includes ``contract`` itself (a plan always contains
        its own root). This is the "downstream" set a recovery must tear down
        when ``contract`` is invalidated: nothing built on top of a re-flashed
        node may keep a handle over it.

        Unresolvable contracts are skipped -- they were never instantiated, so
        they cannot be downstream of anything live.
        """
        downstream: set[str] = set()
        for other in self._registry.contracts():
            try:
                if contract in self.plan(other):
                    downstream.add(other)
            except (UnresolvedContractError, CyclicDependencyError):
                continue
        return frozenset(downstream)

    def _visit(
        self,
        contract: str,
        required_by: str | None,
        on_stack: list[str],
        seen: set[str],
        order: list[str],
        done: set[str],
    ) -> None:
        if contract in done:
            return
        if contract in seen:
            cycle = on_stack[on_stack.index(contract) :] + [contract]
            raise CyclicDependencyError(cycle)

        descriptor = self._registry.descriptor(contract)
        if descriptor is not None:
            order.append(contract)
            done.add(contract)
            return

        provider = self._registry.provider(contract)
        if provider is None:
            raise UnresolvedContractError(contract, required_by=required_by)

        seen.add(contract)
        on_stack.append(contract)
        for dependency in provider.requires:
            self._visit(dependency, contract, on_stack, seen, order, done)
        on_stack.pop()
        seen.discard(contract)

        order.append(contract)
        done.add(contract)
