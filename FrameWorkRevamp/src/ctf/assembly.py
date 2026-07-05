"""The kernel's single session-lived lifecycle and its tier-walk driver.

The kernel owns exactly one timeline: the session. An :class:`Assembly` holds one
instantiation cache and one teardown stack for the whole run. Resources are
resolved lazily on first :meth:`get`, or eagerly and in tier order by
:meth:`realize`, and torn down in reverse instantiation order, mirroring pytest's
yield-fixture semantics.

There is deliberately no *scope* axis. Per-test lifetimes are not a kernel
concern -- an ecosystem author who wants a fresh-per-test object writes a pytest
fixture that wraps a resolved resource.

Three ideas layer on top of the plain cache:

* **Derived tiers** (:func:`compute_tiers`). A contract's tier is *not* declared;
  it is the longest path from a leaf in the dependency graph -- descriptors and
  providers that require nothing sit at tier 0, and every other provider sits one
  tier above its deepest dependency. Eager :meth:`realize` walks tiers ascending
  so that dependencies are always live before their dependents. The tier law
  ("a contribution may require only lower tiers") is not enforced -- it is *true
  by construction*, because a tier is defined from ``requires``.

* **Run modes** (:class:`RunMode`) + a mandatory **spine**. The spine is the
  ``@requires`` closure rooted at the :data:`~ctf.target.TARGET_ANCHOR`. It must
  always resolve. Providers outside the spine are *additive*: in ``LOOSE`` mode
  an additive provider whose dependencies are missing is simply marked
  unavailable (dependent tests skip) instead of failing the run. Without an
  anchor there is no declared spine, so ``LOOSE`` behaves like ``STRICT``.

* **Recovery.** Real hardware needs recovery mid-run. :meth:`invalidate` drops a
  cached node *and its transitive downstream dependents*, tearing them down in
  reverse instantiation order so no stale handle survives over a re-flashed box.
  Rebuilding is lazy: the next :meth:`get` re-realizes the node (and whatever a
  caller re-requests) from scratch. The DUT handle a test holds outlives any one
  composition, so a test recovers by re-requiring, not by mutating in place.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from ctf.errors import (
    CapabilityUnavailableError,
    CompositionError,
    UnresolvedContractError,
)
from ctf.lifecycle import instantiate_provider
from ctf.registry import Registry
from ctf.resolver import GraphResolver
from ctf.target import TARGET_ANCHOR


class RunMode(str, Enum):
    """How unmet *additive* capabilities are treated at compose time."""

    #: Any registered provider that cannot resolve aborts the run.
    STRICT = "strict"
    #: Only the target spine must resolve; unmet additive caps become skips.
    LOOSE = "loose"


def compute_tiers(registry: Registry, contracts: frozenset[str]) -> dict[str, int]:
    """Derive each contract's tier from the dependency graph (longest path).

    ``tier(node)`` is ``0`` for a descriptor or a provider that requires nothing,
    else ``1 + max(tier(dep) for dep in requires)``. Only ``contracts`` is
    computed; each is assumed resolvable, so recursion never descends into a
    missing dependency (an *unavailable* additive provider is not passed in).
    """
    memo: dict[str, int] = {}

    def tier(contract: str) -> int:
        if contract in memo:
            return memo[contract]
        if registry.descriptor(contract) is not None:
            memo[contract] = 0
            return 0
        provider = registry.provider(contract)
        if provider is None or not provider.requires:
            memo[contract] = 0
            return 0
        result = 1 + max(tier(dep) for dep in provider.requires)
        memo[contract] = result
        return result

    return {contract: tier(contract) for contract in contracts}


@dataclass(frozen=True)
class TierReport:
    """What a single tier of the walk realized."""

    tier: int
    realized: tuple[str, ...]

    def __str__(self) -> str:
        what = ", ".join(self.realized) if self.realized else "(nothing new)"
        return f"tier {self.tier}: {what}"


@dataclass(frozen=True)
class CompositionPlan:
    """Static analysis of a registry under a run mode (no factories run)."""

    mode: RunMode
    #: The mandatory closure rooted at the anchor. Empty when no anchor exists.
    spine: frozenset[str]
    #: Contracts whose dependency graph fully resolves.
    available: frozenset[str]
    #: Additive contract -> reason it cannot be resolved (LOOSE only).
    unavailable: dict[str, str]
    #: Every *available* contract -> its derived tier (longest-path depth).
    tier_of: dict[str, int]


def analyze(
    registry: Registry, resolver: GraphResolver, mode: RunMode
) -> CompositionPlan:
    """Classify a registry into spine / available / unavailable under ``mode``.

    Raises immediately (both modes) if the spine cannot resolve. In effective
    strict mode -- ``STRICT``, or ``LOOSE`` with no declared anchor -- any unmet
    provider also raises. In ``LOOSE`` with an anchor, unmet *additive* providers
    are recorded, not raised.
    """
    has_anchor = registry.has(TARGET_ANCHOR)
    spine: set[str] = set(resolver.plan(TARGET_ANCHOR)) if has_anchor else set()

    available: set[str] = set()
    unavailable: dict[str, str] = {}
    for contract in registry.contracts():
        if registry.provider(contract) is None:  # a descriptor: a leaf fact
            available.add(contract)
            continue
        try:
            resolver.plan(contract)
        except UnresolvedContractError as exc:
            unavailable[contract] = str(exc)
        else:
            available.add(contract)

    effective_strict = mode is RunMode.STRICT or not has_anchor
    if effective_strict and unavailable:
        # Re-plan the first offender so the raised error carries the exact chain.
        resolver.plan(sorted(unavailable)[0])

    tier_of = compute_tiers(registry, frozenset(available))
    return CompositionPlan(
        mode=mode,
        spine=frozenset(spine),
        available=frozenset(available),
        unavailable=unavailable,
        tier_of=tier_of,
    )


class Assembly:
    """Owns the session cache and teardown stack for one composed DUT."""

    def __init__(
        self, registry: Registry, resolver: GraphResolver, plan: CompositionPlan
    ) -> None:
        self.registry = registry
        self.resolver = resolver
        self.plan = plan
        self.mode = plan.mode
        self._cache: dict[str, Any] = {}
        self._order: list[str] = []
        self._finalizers: dict[str, Callable[[], None]] = {}
        self._active = False
        self._trace: list[TierReport] = []
        self._realized = False

    @property
    def is_active(self) -> bool:
        return self._active

    def enter(self) -> None:
        """Open the session. Resources may now be resolved."""
        self._active = True

    def exit(self) -> None:
        """Tear down every resolved resource in reverse instantiation order."""
        if not self._active:
            return
        self._active = False
        self._teardown(list(self._order))
        self._trace.clear()
        self._realized = False

    # -- resolution --------------------------------------------------------
    def get(self, contract: str) -> Any:
        """Resolve, instantiate (once), and return ``contract``'s resource.

        Raises :class:`CapabilityUnavailableError` for an additive contract that
        was marked unavailable in LOOSE mode, so the adapter can skip.
        """
        if not self._active:
            raise CompositionError(
                f"cannot resolve {contract!r}: the assembly is not active"
            )
        if contract in self.plan.unavailable:
            raise CapabilityUnavailableError(
                contract, self.plan.unavailable[contract]
            )
        return self._build(contract)

    def available(self, contract: str) -> bool:
        """Whether ``contract``'s dependency graph fully resolves."""
        return contract in self.plan.available

    def materialized(self) -> dict[str, Any]:
        """A snapshot of every resource instantiated so far."""
        return dict(self._cache)

    def tier(self, contract: str) -> int | None:
        """The derived tier of ``contract``, or ``None`` if unavailable."""
        return self.plan.tier_of.get(contract)

    # -- tier walk ---------------------------------------------------------
    def realize(self) -> tuple[TierReport, ...]:
        """Eagerly realize every available resource, tier by tier (ascending).

        Brings the target spine and all available additive capabilities up in
        dependency order -- the eager fail-fast handoff. Returns a per-tier trace
        for narration.
        """
        if not self._active:
            raise CompositionError("cannot realize: the assembly is not active")
        self._realized = True
        self._trace = []
        realize = self.plan.available
        if not realize:
            return ()
        max_tier = max(self.plan.tier_of[c] for c in realize)
        for tier in range(max_tier + 1):
            realized_now: list[str] = []
            for contract in sorted(
                c for c in realize if self.plan.tier_of[c] == tier
            ):
                if contract in self._cache:
                    continue
                self._build(contract)
                realized_now.append(contract)
            self._trace.append(TierReport(tier, tuple(realized_now)))
        return tuple(self._trace)

    def invalidate(self, contract: str) -> tuple[str, ...]:
        """Drop ``contract`` and its transitive dependents (messy-HW recovery).

        Tears down ``contract`` together with every resource that (transitively)
        requires it, in reverse instantiation order, so no stale handle survives
        over a re-flashed or re-provisioned node. Cache, order, and finalizers are
        cleaned. Rebuilding is lazy: the next :meth:`get` re-realizes on demand.

        A no-op (returns ``()``) when ``contract`` was never instantiated.
        Returns the contracts that were torn down, in teardown order.
        """
        if not self._active:
            raise CompositionError("cannot invalidate: the assembly is not active")
        if contract not in self._cache:
            return ()
        downstream = self.resolver.dependents(contract)
        torn_down: list[str] = []
        errors: list[BaseException] = []
        for node in reversed(self._order):
            if node not in downstream:
                continue
            torn_down.append(node)
            self._cache.pop(node, None)
            finalize = self._finalizers.pop(node, None)
            if finalize is None:
                continue
            try:
                finalize()
            except BaseException as exc:  # noqa: BLE001 - collect and re-raise
                errors.append(exc)
        self._order = [c for c in self._order if c not in downstream]
        if errors:
            raise CompositionError(
                f"{len(errors)} teardown(s) failed while invalidating "
                f"{contract!r}: " + "; ".join(repr(e) for e in errors)
            )
        return tuple(torn_down)

    def trace(self) -> tuple[TierReport, ...]:
        """The per-tier report from the most recent walk."""
        return tuple(self._trace)

    def is_ready(self) -> bool:
        """Whether the mandatory spine is fully realized after a walk."""
        return self._realized and self.plan.spine.issubset(self._cache)

    # -- internals ---------------------------------------------------------
    def _build(self, contract: str) -> Any:
        for node in self.resolver.plan(contract):
            if node in self._cache:
                continue
            self._instantiate(node)
        return self._cache[contract]

    def _instantiate(self, contract: str) -> None:
        descriptor = self.registry.descriptor(contract)
        if descriptor is not None:
            self._cache[contract] = descriptor.value
            self._order.append(contract)
            return
        provider = self.registry.provider(contract)
        assert provider is not None  # guaranteed by the resolver
        args = [self._cache[dep] for dep in provider.requires]
        value, finalizer = instantiate_provider(provider, args)
        self._cache[contract] = value
        self._order.append(contract)
        if finalizer is not None:
            self._finalizers[contract] = finalizer

    def _teardown(self, affected: list[str]) -> None:
        affected_set = set(affected)
        errors: list[BaseException] = []
        for contract in reversed(self._order):
            if contract not in affected_set:
                continue
            self._cache.pop(contract, None)
            finalize = self._finalizers.pop(contract, None)
            if finalize is None:
                continue
            try:
                finalize()
            except BaseException as exc:  # noqa: BLE001 - collect and re-raise
                errors.append(exc)
        self._order = [c for c in self._order if c not in affected_set]
        if errors:
            raise CompositionError(
                f"{len(errors)} teardown(s) failed: "
                + "; ".join(repr(e) for e in errors)
            )
