"""Contract-based composition primitives.

Providers declare, via decorators, the single contract they *provide* and the
ordered contracts they *require*. Resolved dependencies are injected into the
factory **positionally, in ``requires`` declaration order** -- an explicit
mapping that avoids guessing from parameter names.

Example:
    >>> @provides("doip/client")
    ... @requires("transport/doip")
    ... def doip_client(transport):
    ...     return DoipClient(transport)
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

_PROVIDES_ATTR = "__ctf_provides__"
_REQUIRES_ATTR = "__ctf_requires__"

#: A contract's *tier* is not declared -- it is **derived** from the dependency
#: graph (see :func:`ctf.assembly.compute_tiers`). Descriptors and providers
#: that require nothing sit at tier 0; every other provider sits one tier above
#: its deepest dependency. The tier law falls out for free: a contribution can
#: only ``@requires`` strictly lower tiers, so two same-tier nodes are mutually
#: invisible and peer coupling is impossible by construction. There is nothing
#: to declare and nothing to keep consistent -- and therefore no phase to get
#: wrong.


def provides(contract: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark a factory as the producer of ``contract``.

    Args:
        contract: The contract string this factory produces.

    A provider declares only *what* it provides and *what* it requires; its tier
    on the bring-up ladder is derived from the graph, never declared. The kernel
    owns a single (session) timeline: every resolved resource lives for the
    whole assembly and is torn down in reverse order at the end. Per-test
    freshness is not a kernel concern -- express it with a pytest fixture that
    wraps the resolved resource.
    """
    if not isinstance(contract, str) or not contract:
        raise ValueError("provides() contract must be a non-empty string")

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        setattr(fn, _PROVIDES_ATTR, contract)
        return fn

    return decorator


def requires(*contracts: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Declare contracts a factory depends on, in injection order.

    Multiple ``@requires`` decorators compose top-to-bottom; the topmost
    decorator's contracts are injected first.
    """
    for contract in contracts:
        if not isinstance(contract, str) or not contract:
            raise ValueError("requires() contracts must be non-empty strings")

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        existing = tuple(getattr(fn, _REQUIRES_ATTR, ()))
        setattr(fn, _REQUIRES_ATTR, tuple(contracts) + existing)
        return fn

    return decorator


@dataclass(frozen=True)
class Provider:
    """A pure transformation: required contracts -> a produced resource.

    Attributes:
        provides: The contract this provider produces.
        requires: Ordered contracts injected positionally into ``factory``.
        factory: A callable, or a generator function whose post-``yield`` body
            runs at teardown.
        name: Human-readable identity used in errors and diagnostics.
        is_generator: Whether ``factory`` yields (enabling teardown).
    """

    provides: str
    factory: Callable[..., Any]
    requires: tuple[str, ...] = ()
    name: str = ""
    is_generator: bool = field(default=False)

    def __post_init__(self) -> None:
        if not self.name:
            object.__setattr__(self, "name", getattr(self.factory, "__name__", repr(self.factory)))
        object.__setattr__(
            self, "is_generator", inspect.isgeneratorfunction(self.factory)
        )


def build_provider(fn: Callable[..., Any]) -> Provider:
    """Construct a :class:`Provider` from a ``@provides``-decorated factory."""
    contract = getattr(fn, _PROVIDES_ATTR, None)
    if contract is None:
        raise ValueError(
            f"{getattr(fn, '__name__', fn)!r} is not decorated with @provides(...)"
        )
    required = tuple(getattr(fn, _REQUIRES_ATTR, ()))
    return Provider(
        provides=contract,
        factory=fn,
        requires=required,
    )
