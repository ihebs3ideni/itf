# *******************************************************************************
# Copyright (c) 2026 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
# *******************************************************************************
"""@provides / @delivers decorators and the catalog (docs/octo-kit/11-spec-itf-engine.md §4).

Staging is keyed by the defining module (`func.__module__`), append-only, so whether a
descriptor is present never depends on what else happened to be imported (A-3.2).
"""

from __future__ import annotations

import collections.abc
import dataclasses
import inspect
import typing
from dataclasses import dataclass, field

from ..octo import Need, ProviderClaim, Shape, StateContractClaim, shape_of
from .scopes import state_ref
from .config import ConfigSchema

_STAGING: dict[str, list] = {}


@dataclass(frozen=True)
class Expectation:
    """`expect(contract, shape)`'s result, for a `needs=`/`uses=` dict value that wants to require
    more than the contract token alone (or whose parameter has no useful annotation to infer from).
    """

    contract: str
    shape: object = None


def expect(contract: str, shape: object = None) -> Expectation:
    """Wrap a `needs=`/`uses=` slot's contract with an explicit shape, independent of the
    parameter's own type annotation — `expect()`'s shape always wins over an annotation, the same
    way an annotation always wins over nothing declared at all.

        @provides("widget.session", name="pack.session",
                  needs={"endpoint": expect("itf.capabilities.descriptor.endpoint", ("host", "port"))})

    `shape` takes anything `_to_shape` accepts: `None`, a `Shape`, a tuple of member names, or a
    type `shape_of` reduces (Protocol, dataclass, ABC, Pydantic model, plain class) — never a
    concrete class imported from the pack that implements the contract (D-28): the whole point is
    naming a footprint without naming who provides it.
    """
    return Expectation(contract, shape)


def _to_shape(spec) -> Shape:
    """A shape spec is None, a tuple of member names, a `Shape`, or any type `shape_of` reduces
    (Protocol, dataclass, ABC, Pydantic model, or a plain class)."""
    if spec is None:
        return Shape()
    if isinstance(spec, Shape):
        return spec
    if isinstance(spec, (tuple, list)):
        return Shape.of(*spec)
    if inspect.isclass(spec):
        return shape_of(spec)
    raise TypeError(f"cannot build a shape from {spec!r}")


def _annotation(func, param: str | None):
    """The resolved annotation of `param` (None = return), or None if absent or unresolvable."""
    try:
        hints = typing.get_type_hints(func)
    except Exception:
        return None
    return hints.get("return" if param is None else param)


def _yielded(ann):
    """`Iterator[X]` / `Generator[X, ...]` / `Iterable[X]` -> X, for fixture-style providers."""
    if typing.get_origin(ann) in (collections.abc.Iterator, collections.abc.Generator, collections.abc.Iterable):
        args = typing.get_args(ann)
        return args[0] if args else None
    return ann


def _inferred_shape(ann) -> Shape:
    if not inspect.isclass(ann) or ann.__module__ == "builtins":
        return Shape()
    return shape_of(ann)


def _default_name(func) -> str:
    return f"{func.__module__.split('.', 1)[0]}.{func.__name__}"


def _check_signature(func, declared_slots: set[str], what: str) -> None:
    params = set(inspect.signature(func).parameters) - {"config"}
    missing = declared_slots - params
    extra = params - declared_slots
    if missing or extra:
        raise TypeError(
            f"{what} {func.__qualname__!r}: declared slots {sorted(declared_slots)} must match "
            f"parameters {sorted(params)} (plus optional 'config'); "
            f"missing={sorted(missing)} extra={sorted(extra)}"
        )


def _needs(func, slots: dict[str, "str | Expectation"]) -> tuple[Need, ...]:
    """Each slot's expected shape: `expect()`'s own shape if it has one, else the parameter's own
    annotation."""
    needs = []
    for slot, value in sorted(slots.items()):
        if isinstance(value, Expectation):
            contract = value.contract
            expected = _to_shape(value.shape) if value.shape is not None else _inferred_shape(_annotation(func, slot))
        else:
            contract = value
            expected = _inferred_shape(_annotation(func, slot))
        needs.append(Need(slot=slot, contract=contract, expected=expected))
    return tuple(needs)


@dataclass
class ProviderDescriptor:
    name: str
    implements: str
    gives: Shape
    needs: tuple[Need, ...]
    impl: str
    module: str
    config_schema: ConfigSchema | None = None


@dataclass
class ActionDescriptor:
    token: str
    name: str
    impl: str
    module: str
    probe: str = ""
    requires: frozenset[str] = frozenset()
    invalidates: frozenset[str] = frozenset()
    also_delivers: frozenset[str] = frozenset()
    uses: tuple[Need, ...] = ()
    extra_probes: dict[str, str] = field(default_factory=dict)  # also-delivered token -> its own probe


def provides(
    token: str,
    *,
    name: str | None = None,
    needs: dict[str, "str | Expectation"] | None = None,
    gives=None,
    config_schema=None,
):
    """A capability factory, fixture-style: `return obj`, or `yield obj` and clean up after the yield.

    What it gives is read from the return annotation (`-> Shell`, or `-> Iterator[Shell]` when it
    yields); `gives=` overrides that for untyped code. What each slot must offer is read from that
    parameter's annotation, or from an `expect(contract, shape)`-wrapped `needs=` value, which
    always wins over the annotation.
    """
    needs = needs or {}

    def deco(func):
        _check_signature(func, set(needs), "provides")
        schema = ConfigSchema.from_dataclass(config_schema) if config_schema is not None else None
        if schema is not None and "config" not in inspect.signature(func).parameters:
            raise TypeError("a provider with config_schema must accept config")
        provider_name = name or _default_name(func)
        shape = _to_shape(gives) if gives is not None else _inferred_shape(_yielded(_annotation(func, None)))
        desc = ProviderDescriptor(
            name=provider_name,
            implements=token,
            gives=shape,
            needs=_needs(func, needs),
            impl=f"{func.__module__}:{func.__qualname__}",
            module=func.__module__,
            config_schema=schema,
        )
        _STAGING.setdefault(func.__module__, []).append(desc)
        func.__itf_provides_name__ = provider_name
        return func

    return deco


def delivers(
    token: str,
    *,
    name: str | None = None,
    requires=(),
    invalidates=(),
    also_delivers=(),
    uses: dict[str, "str | Expectation"] | None = None,
):
    """The action that makes state `token` true. Add `@<action>.probe` to observe whether it holds.

    An action that really establishes several states in one call lists the others in `also_delivers`;
    by default its probe vouches for all of them. `@<action>.probe_for(other)` gives one of them its
    own evidence: it is then published as a contract of its own sharing this action, and the planner
    runs the action once while checking each state with its own probe.
    """
    uses = uses or {}

    def deco(func):
        _check_signature(func, set(uses), "delivers")
        action_name = name or _default_name(func)
        desc = ActionDescriptor(
            token=token,
            name=action_name,
            impl=f"{func.__module__}:{func.__qualname__}",
            module=func.__module__,
            requires=frozenset(state_ref(r) for r in requires),
            invalidates=frozenset(state_ref(r) for r in invalidates),
            also_delivers=frozenset(also_delivers),
            uses=_needs(func, uses),
        )
        _STAGING.setdefault(func.__module__, []).append(desc)
        func.__itf_delivers_name__ = action_name

        def probe(probe_func):
            _check_signature(probe_func, set(uses), "probe")
            desc.probe = f"{probe_func.__module__}:{probe_func.__qualname__}"
            return probe_func

        # One action, several states, each with its own evidence: an action that delivers both "A" and "B" runs
        # once, but a stale B is not vouched for by a probe of A. Without
        # probe_for the single probe vouches for all states, which is the safe default for small actions.
        def probe_for(state: str):
            if state not in desc.also_delivers:
                raise TypeError(
                    f"{action_name}: probe_for({state!r}) names a state the action does not "
                    f"also_deliver; also_delivers={sorted(desc.also_delivers)}"
                )

            def register(probe_func):
                _check_signature(probe_func, set(uses), "probe")
                desc.extra_probes[state] = f"{probe_func.__module__}:{probe_func.__qualname__}"
                return probe_func

            return register

        func.probe = probe
        func.probe_for = probe_for
        return func

    return deco


# Published once per session from what the registered contributors declared. The catalog is data (names,
# shapes, schemas), which is why the same publish step also feeds the SQLite catalog tool and `--itf-plan`:
# one source of truth for what a pack offers, no second registry to drift.
@dataclass(frozen=True)
class Catalog:
    providers: tuple[ProviderClaim, ...]
    actions: tuple[StateContractClaim, ...]
    action_by_name: dict = field(default_factory=dict)  # action name -> StateContractClaim
    action_by_name_and_token: dict = field(default_factory=dict)  # (action name, token) -> claim
    config_schemas: dict[str, ConfigSchema] = field(default_factory=dict)


def publish(registry) -> Catalog:
    """Every descriptor staged by a registered contributor's package, at that package's origin."""
    from .registry import contributor_of  # the registry imports this module

    providers = []
    actions = []
    action_by_name: dict[str, StateContractClaim] = {}
    action_by_name_and_token: dict[tuple[str, str], StateContractClaim] = {}
    config_schemas: dict[str, ConfigSchema] = {}
    for mod_name in sorted(_STAGING):
        origin = registry.origin_of_package(contributor_of(mod_name))
        if origin is None:
            continue
        for desc in _STAGING[mod_name]:
            if isinstance(desc, ProviderDescriptor):
                if desc.config_schema is not None:
                    config_schemas[desc.name] = desc.config_schema
                providers.append(
                    ProviderClaim(
                        name=desc.name,
                        implements=desc.implements,
                        gives=desc.gives,
                        needs=desc.needs,
                        impl=desc.impl,
                        origin=origin,
                    )
                )
            else:
                claim = StateContractClaim(
                    token=desc.token,
                    impl=desc.impl,
                    probe=desc.probe,
                    requires=desc.requires,
                    invalidates=desc.invalidates,
                    also_delivers=desc.also_delivers - set(desc.extra_probes),
                    uses=desc.uses,
                    scope="",
                    origin=origin,
                )
                actions.append(claim)
                action_by_name[desc.name] = claim
                action_by_name_and_token[(desc.name, desc.token)] = claim
                # A separately probed extra state: same action and uses, so the planner collapses
                # the two contracts into one invocation and keeps both probes.
                for state, probe in sorted(desc.extra_probes.items()):
                    extra = dataclasses.replace(claim, token=state, probe=probe, also_delivers=frozenset())
                    actions.append(extra)
                    action_by_name_and_token[(desc.name, state)] = extra
    return Catalog(
        providers=tuple(providers),
        actions=tuple(actions),
        action_by_name=action_by_name,
        action_by_name_and_token=action_by_name_and_token,
        config_schemas=config_schemas,
    )


def provider_name_of(value) -> str | None:
    return getattr(value, "__itf_provides_name__", None)


def action_name_of(value) -> str | None:
    return getattr(value, "__itf_delivers_name__", None)
