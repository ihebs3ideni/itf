"""Lifecycle *verbs* and policy-based resolution (the "WHEN" plane).

This is the lifecycle plane, kept strictly separate from composition (the "WHAT"
plane in :mod:`ctf.dut`). Plugins contribute *verbs* -- side-effect-only actions
that only ``require`` nouns and return nothing -- to named *extension points*.
The engine, driven by pytest's own lifecycle hooks, resolves the verbs of a
point according to that point's :class:`Policy`:

* ``FANOUT``  -- run every verb (deterministic order); collect all results.
* ``FIRST``   -- run in order, stop at the first that returns non-``None``.
* ``UNIQUE``  -- exactly one verb allowed; more than one is a hard error.

The engine defines only generic points and policies -- never domain verbs like
"flash" or "provision". Plugins name and fill the points.

Noun vs verb: *does anyone ``require`` your result?* Yes -> it is a noun (a
provider, single-source-of-truth, graph-ordered). No -> it is a verb (fanout by
default, order-independent because verbs compose only through nouns, never
through each other). Provisioning that establishes state a capability needs is a
noun; provisioning that is fire-and-forget is a verb -- hence ``ctf_provision``
is FANOUT, not a single privileged owner.

:meth:`StepRegistry.resolve` is stateless, so a point can be fired again on
demand -- e.g. re-running provision verbs after a recovery re-flashed the box.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from ctf.errors import StepCollisionError

StepFn = Callable[["StepContext"], Any]


class Policy(Enum):
    """How the engine resolves the steps registered at an extension point."""

    FANOUT = "fanout"
    FIRST = "first"
    UNIQUE = "unique"


#: Built-in extension points and their default policies. Points are bound to
#: pytest lifecycle moments in :mod:`ctf.pytest_plugin`. Provisioning is a
#: fanout verb -- many independent provision actions may run, and none of them
#: is a privileged single owner (that role belongs to the noun graph's anchor).
BUILTIN_POINTS: dict[str, Policy] = {
    "ctf_provision": Policy.FANOUT,
    "ctf_session_setup": Policy.FANOUT,
    "ctf_before_test": Policy.FANOUT,
    "ctf_after_test": Policy.FANOUT,
    "ctf_collect": Policy.FANOUT,
    "ctf_session_teardown": Policy.FANOUT,
}


@dataclass(frozen=True)
class Step:
    """A single lifecycle contribution bound to an extension point."""

    point: str
    fn: StepFn
    order: int = 0
    name: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            object.__setattr__(self, "name", getattr(self.fn, "__name__", repr(self.fn)))


class ArtifactSink:
    """A minimal collector for test artifacts contributed by steps."""

    def __init__(self) -> None:
        self.items: list[tuple[str, Any]] = []

    def add(self, name: str, value: Any = None) -> None:
        self.items.append((name, value))

    def names(self) -> list[str]:
        return [name for name, _ in self.items]


@dataclass
class StepContext:
    """What a step receives. Bridges the phase plane to the composition plane."""

    dut: Any  # ctf.dut.DUT -- avoid import cycle
    registry: Any  # ctf.registry.Registry
    artifacts: ArtifactSink
    config: Any = None
    session: Any = None
    item: Any = None
    report: Any = None

    def require(self, contract: str) -> Any:
        """Pull a resource from the composition plane."""
        return self.dut.require(contract)

    def publish(self, descriptor: Any) -> None:
        """Enrich the composition graph with a runtime-discovered fact."""
        self.registry.add_descriptor(descriptor)


class StepRegistry:
    """Holds contributed steps and resolves them per extension-point policy."""

    def __init__(self) -> None:
        self._steps: dict[str, list[Step]] = defaultdict(list)
        self._policies: dict[str, Policy] = dict(BUILTIN_POINTS)

    # -- contribution ------------------------------------------------------
    def declare(self, point: str, policy: Policy) -> None:
        """Declare a custom extension point (or override a policy)."""
        self._policies[point] = policy

    def add(
        self,
        point: str,
        fn: StepFn,
        *,
        order: int = 0,
        name: str | None = None,
    ) -> None:
        """Contribute a step to ``point``."""
        self._steps[point].append(Step(point, fn, order, name or getattr(fn, "__name__", "")))

    # -- queries -----------------------------------------------------------
    def policy(self, point: str) -> Policy:
        return self._policies.get(point, Policy.FANOUT)

    def points(self) -> list[str]:
        """All known extension points (declared and/or contributed to)."""
        return sorted(set(self._policies) | set(self._steps))

    def steps_for(self, point: str, *, reverse: bool = False) -> list[Step]:
        ordered = sorted(self._steps[point], key=lambda s: (s.order, s.name))
        return list(reversed(ordered)) if reverse else ordered

    def validate(self) -> None:
        """Fail fast on structural errors before any point is resolved.

        Currently this surfaces ``UNIQUE`` collisions up front so a bad
        ecosystem stops the run at session start rather than mid-test.
        """
        for point, steps in self._steps.items():
            if self.policy(point) is Policy.UNIQUE and len(steps) > 1:
                raise StepCollisionError(point, [s.name for s in steps])

    # -- resolution --------------------------------------------------------
    def resolve(self, point: str, ctx: StepContext, *, reverse: bool = False) -> Any:
        """Run the steps of ``point`` according to its policy.

        Returns:
            FANOUT: list of ``(step_name, result)`` for every step.
            FIRST: the first non-``None`` result, or ``None``.
            UNIQUE: the single step's result, or ``None`` if none registered.

        Raises:
            StepCollisionError: policy is ``UNIQUE`` and >1 step is registered.
        """
        policy = self.policy(point)
        steps = self.steps_for(point, reverse=reverse)

        if policy is Policy.UNIQUE:
            if len(steps) > 1:
                raise StepCollisionError(point, [s.name for s in steps])
            return steps[0].fn(ctx) if steps else None

        if policy is Policy.FIRST:
            for step in steps:
                result = step.fn(ctx)
                if result is not None:
                    return result
            return None

        # FANOUT
        return [(step.name, step.fn(ctx)) for step in steps]
