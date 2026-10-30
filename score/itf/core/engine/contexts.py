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
"""Write-only claim builders for `itf_setup` and `itf_init` (docs/octo-kit/11-spec-itf-engine.md §5).

References are names, not imported callables, so contributors can be collected independently.
These builders only collect immutable declarations (claims): setup describes objects and wiring;
init describes desired states and their dependencies. Resolution and execution happen elsewhere.
"""

from __future__ import annotations

import dataclasses

from ..octo import (
    AssumeClaim,
    BindingClaim,
    CapabilityContractClaim,
    GoalClaim,
    Need,
    NodeClaim,
    RelationClaim,
    Shape,
    ShapeExpectationClaim,
    shape_of,
)
from .publish import action_name_of, provider_name_of
from .scopes import ROOT, check_scope_name, node_ref, state_ref


class CollectionClosed(Exception):
    """A context was used after its collection phase drained it."""


class WrongPhase(Exception):
    """A setup verb called on InitContext, or an init verb called on SetupContext."""


def _definition_on_scope(name: str) -> AttributeError:
    return AttributeError(
        f"'{name}' is a definition and applies in every scope: call ctx.{name}(...), not ctx.scope(...).{name}(...)"
    )


def _pairs(mapping) -> tuple:
    """Make mappings deterministic and immutable for claim comparison and serialization."""
    if not mapping:
        return ()
    return tuple(sorted(mapping.items()))


def _node_refs(mapping) -> tuple:
    """Normalize each slot's node reference without looking up or constructing the node."""
    return _pairs({slot: node_ref(ref) for slot, ref in (mapping or {}).items()})


def _state_refs(refs) -> frozenset:
    """Normalize state references; ordering and duplicate entries have no semantic meaning."""
    return frozenset(state_ref(r) for r in refs)


def _require_name(value, *, what: str) -> str | None:
    """Keep declarations name-based; decorated Python callables are not claim references."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    name = provider_name_of(value) or action_name_of(value)
    if name:
        raise TypeError(f"{what} must be a name (str); pass {what}={name!r} instead of the function")
    raise TypeError(f"{what} must be a name (str), not {value!r}")


class ScopeSetupBuilder:
    """A namespace-bound view that appends declarations to its owning setup context."""

    def __init__(self, ctx: "SetupContext", scope: str):
        self._ctx = ctx
        self._scope = scope

    def add(self, name, contract=None, *, using=None, bind=None, config=None):
        """Declare a node: contract is its role, using its provider, bind its slot-to-node wiring."""
        self._ctx._check_open()
        using_name = _require_name(using, what="using")
        claim = NodeClaim(
            scope=self._scope,
            name=name,
            contract=contract,
            using=using_name,
            bind=_node_refs(bind),
            config=_pairs(config),
            origin=self._ctx._origin,
        )
        self._ctx._claims.append(claim)

    def alias(self, name: str, target: str):
        """Give an existing node another name; aliases share one realized object and lifetime."""
        self._ctx._check_open()
        claim = NodeClaim(scope=self._scope, name=name, alias=node_ref(target), origin=self._ctx._origin)
        self._ctx._claims.append(claim)

    def rebind(self, name: str, **slots):
        """Contribute slot bindings for an existing node without redeclaring its other fields."""
        self._ctx._check_open()
        claim = BindingClaim(scope=self._scope, name=name, bind=_node_refs(slots), origin=self._ctx._origin)
        self._ctx._claims.append(claim)

    def __getattr__(self, name):
        if name in ("goal", "relate", "assume"):
            raise WrongPhase(f"'{name}' belongs in itf_init, not itf_setup")
        if name in ("contract", "expect"):
            raise _definition_on_scope(name)
        raise AttributeError(name)


class SetupContext:
    """Top-level `add`/`alias`/`rebind` write to the target's root scope; `scope(name)` to a device."""

    def __init__(self, origin: str, catalog):
        self._origin = origin
        self._catalog = catalog
        self._claims: list = []
        self._closed = False
        self._root = ScopeSetupBuilder(self, ROOT)

    def add(self, name, contract=None, *, using=None, bind=None, config=None):
        self._root.add(name, contract, using=using, bind=bind, config=config)

    def alias(self, name: str, target: str):
        self._root.alias(name, target)

    def rebind(self, name: str, **slots):
        self._root.rebind(name, **slots)

    def contract(self, token: str, *, gives=None, needs: dict[str, str] | None = None):
        """Declare a reusable capability role and shape, not an instance or implementation."""
        self._check_open()
        needs = needs or {}
        need_objs = tuple(Need(slot, contract, Shape()) for slot, contract in sorted(needs.items()))
        gives_shape = gives if isinstance(gives, Shape) else Shape.of(*gives) if gives else Shape()
        self._claims.append(
            CapabilityContractClaim(token=token, gives=gives_shape, needs=need_objs, origin=self._origin)
        )

    def expect(self, contract: str, shape=None) -> None:
        """Every node offering `contract` must satisfy `shape`, regardless of which consumer's
        `needs`/`uses` asked for it — additive across every `ctx.expect()` call for the same
        contract (D-34): two policies' expectations union, they never conflict the way two
        `NodeClaim`s at equal origin would. `shape` takes anything a `needs=`/`uses=` shape does:
        `None`, a `Shape`, a tuple of member names, or a type `shape_of` reduces.
        """
        self._check_open()
        if shape is None:
            shape_obj = Shape()
        elif isinstance(shape, Shape):
            shape_obj = shape
        elif isinstance(shape, (tuple, list)):
            shape_obj = Shape.of(*shape)
        else:
            shape_obj = shape_of(shape)
        self._claims.append(ShapeExpectationClaim(contract=contract, shape=shape_obj, origin=self._origin))

    def scope(self, name: str) -> ScopeSetupBuilder:
        self._check_open()
        return ScopeSetupBuilder(self, check_scope_name(name))

    def _check_open(self):
        if self._closed:
            raise CollectionClosed("SetupContext is closed after itf_setup collection")

    def _drain(self) -> frozenset:
        # Phase closure prevents later hooks from changing declarations already being resolved.
        self._closed = True
        return frozenset(self._claims)

    def __getattr__(self, name):
        if name in ("goal", "relate", "state", "target", "assume"):
            raise WrongPhase(f"'{name}' belongs in itf_init, not itf_setup")
        raise AttributeError(name)


class ScopeInitBuilder:
    """Collect state goals and relations in one scope; no action or probe executes here."""

    def __init__(self, ctx: "InitContext", scope: str):
        self._ctx = ctx
        self._scope = scope

    def goal(self, *states: str):
        """Request final conditions, not a sequence of actions in the argument order."""
        self._ctx._check_open()
        self._ctx._claims.append(GoalClaim(scope=self._scope, states=frozenset(states), origin=self._ctx._origin))

    def relate(self, state: str, *, requires=(), invalidates=()):
        """Add policy-specific relations to the action producing `state` in this scope.

        `requires` must hold before that action runs. `invalidates` names conditions that
        its execution destroys; it does not mean those states need to hold first.
        Relations augment the pack's action declarations, rather than replacing them.
        A relation is not a goal and does not itself schedule or execute any work.
        """
        self._ctx._check_open()
        # OCTO combines this policy claim with the selected producer's requires/invalidates.
        self._ctx._claims.append(
            RelationClaim(
                state=state,
                adds_requires=_state_refs(requires),
                adds_invalidates=_state_refs(invalidates),
                scope=self._scope,
                origin=self._ctx._origin,
            )
        )

    def assume(self, token: str, *, owner: str = "", reason: str = ""):
        """Treat `token` as already true in this scope; its producer action never runs (D-30)."""
        self._ctx._check_open()
        self._ctx._claims.append(
            AssumeClaim(
                scope=self._scope,
                token=token,
                owner=owner,
                reason=reason,
                origin=self._ctx._origin,
            )
        )

    def __getattr__(self, name):
        if name in ("add", "alias", "rebind"):
            raise WrongPhase(f"'{name}' belongs in itf_setup, not itf_init")
        if name == "state":
            raise _definition_on_scope(name)
        raise AttributeError(name)


class TargetView:
    """Read-only view of the Gate 1 plan. Never constructs. `scope=None` is the root scope."""

    def __init__(self, plan):
        self._plan = plan

    def tokens(self, scope: str | None = None) -> tuple[str, ...]:
        return self._plan.tokens(scope or ROOT)

    def has(self, token: str, scope: str | None = None) -> bool:
        return token in self._plan.tokens(scope or ROOT)

    def nodes(self, scope: str | None = None) -> tuple:
        return tuple(n for n in self._plan.nodes if n.scope == (scope or ROOT))


class InitContext:
    """Top-level `goal`/`relate`/`assume` write to the root scope; `scope(name)` to a device.
    `state` is the one definition verb: it picks the action for a token in every scope."""

    def __init__(self, origin: str, catalog, target_plan):
        self._origin = origin
        self._catalog = catalog
        self._claims: list = []
        self._closed = False
        self.target = TargetView(target_plan)
        self._root = ScopeInitBuilder(self, ROOT)

    def scope(self, name: str) -> ScopeInitBuilder:
        self._check_open()
        return ScopeInitBuilder(self, check_scope_name(name))

    def goal(self, *states: str):
        """Request root-scope final states; dependencies determine the action order."""
        self._root.goal(*states)

    def relate(self, state: str, *, requires=(), invalidates=()):
        """Add prerequisites/effects to a root-scope state's producer, without executing it.

        For a device-local relation, use `ctx.scope(name).relate(...)`. See ScopeInitBuilder
        for the requires/invalidates distinction; this method delegates to the root builder.
        """
        self._root.relate(state, requires=requires, invalidates=invalidates)

    def assume(self, token: str, *, owner: str = "", reason: str = ""):
        self._root.assume(token, owner=owner, reason=reason)

    def state(self, token: str, *, using):
        """Select an existing producer by action name for this token in every scope."""
        self._check_open()
        name = _require_name(using, what="using")
        by_token = getattr(self._catalog, "action_by_name_and_token", {})
        action = by_token.get((name, token)) or self._catalog.action_by_name.get(name)
        if action is None:
            raise KeyError(f"no action named {name!r}; known: {sorted(self._catalog.action_by_name)}")
        # An empty scope denotes a shared state definition, not a root/device state instance.
        claim = dataclasses.replace(action, token=token, scope="", origin=self._origin)
        self._claims.append(claim)

    def _check_open(self):
        if self._closed:
            raise CollectionClosed("InitContext is closed after itf_init collection")

    def _drain(self) -> frozenset:
        self._closed = True
        return frozenset(self._claims)

    def __getattr__(self, name):
        if name in ("contract", "expect", "add", "alias", "rebind"):
            raise WrongPhase(f"'{name}' belongs in itf_setup, not itf_init")
        raise AttributeError(name)
