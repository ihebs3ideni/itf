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
"""Gate 1 — what must exist. Pick one winning declaration per node name, choose its provider,
fill each of the provider's slots (explicit bind, else the single candidate in scope, else derive a
node), check shapes at every seam, and order construction. Reads kind flags, never kind names.
"""

from __future__ import annotations

import dataclasses
import functools
from typing import Iterable

from dataclasses import dataclass

from .. import graph
from .. import precedence as ranking
from ..claims import Pairs, Scalar
from ..diagnostics import Diagnostic, shape_mismatches
from ..kinds import Kind
from ..plans import Seam
from ..relations import Relation
from ..shapes import Need, Shape


# ---------------------------------------------------------------- setup claims (Gate 1)


@dataclass(frozen=True)
class CapabilityContractClaim:
    token: str
    gives: Shape = Shape()
    needs: tuple[Need, ...] = ()
    origin: str = ""

    def subject(self) -> str:
        return f"contract:{self.token}"

    def to_json(self) -> dict:
        return {
            "token": self.token,
            "gives": self.gives.to_json(),
            "needs": [n.to_json() for n in self.needs],
            "origin": self.origin,
        }

    @classmethod
    def from_json(cls, data: dict) -> "CapabilityContractClaim":
        return cls(
            token=data["token"],
            gives=Shape.from_json(data.get("gives", {})),
            needs=tuple(Need.from_json(n) for n in data.get("needs", ())),
            origin=data.get("origin", ""),
        )


@dataclass(frozen=True)
class ProviderClaim:
    name: str
    implements: str
    gives: Shape = Shape()
    needs: tuple[Need, ...] = ()
    impl: str = ""  # "module:qualname", opaque to OCTO
    origin: str = ""

    def subject(self) -> str:
        return f"provider:{self.name}"

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "implements": self.implements,
            "gives": self.gives.to_json(),
            "needs": [n.to_json() for n in self.needs],
            "impl": self.impl,
            "origin": self.origin,
        }

    @classmethod
    def from_json(cls, data: dict) -> "ProviderClaim":
        return cls(
            name=data["name"],
            implements=data["implements"],
            gives=Shape.from_json(data.get("gives", {})),
            needs=tuple(Need.from_json(n) for n in data.get("needs", ())),
            impl=data.get("impl", ""),
            origin=data.get("origin", ""),
        )


@dataclass(frozen=True)
class ShapeExpectationClaim:
    """A shape every node offering `contract` must satisfy, regardless of which consumer's `needs`
    asked for it. Additive across every claim for the same contract (D-34): two contributors'
    expectations for the same contract union their members, they never conflict the way two
    `NodeClaim`s at equal origin would — the same "equal origins add up, never pick a winner"
    treatment `GoalClaim`/`RelationClaim` already get in Gate 2, applied to Gate 1's shape check.
    """

    contract: str
    shape: Shape = Shape()
    origin: str = ""

    def to_json(self) -> dict:
        return {"contract": self.contract, "shape": self.shape.to_json(), "origin": self.origin}

    @classmethod
    def from_json(cls, data: dict) -> "ShapeExpectationClaim":
        return cls(
            contract=data["contract"],
            shape=Shape.from_json(data.get("shape", {})),
            origin=data.get("origin", ""),
        )


@dataclass(frozen=True)
class NodeClaim:
    scope: str
    name: str
    contract: str | None = None  # None: taken from `using`'s provider, or alias set
    using: str | None = None  # provider name
    bind: Pairs = ()  # ((slot, "name" | "scope.name"), ...)
    config: Pairs = ()  # ((key, Scalar), ...)
    alias: str | None = None  # "scope.name"
    origin: str = ""

    def subject(self) -> str:
        return f"{self.scope}.{self.name}"

    def to_json(self) -> dict:
        return {
            "scope": self.scope,
            "name": self.name,
            "contract": self.contract,
            "using": self.using,
            "bind": dict(self.bind),
            "config": dict(self.config),
            "alias": self.alias,
            "origin": self.origin,
        }

    @classmethod
    def from_json(cls, data: dict) -> "NodeClaim":
        return cls(
            scope=data["scope"],
            name=data["name"],
            contract=data.get("contract"),
            using=data.get("using"),
            bind=tuple(sorted(data.get("bind", {}).items())),
            config=tuple(sorted(data.get("config", {}).items())),
            alias=data.get("alias"),
            origin=data.get("origin", ""),
        )


@dataclass(frozen=True)
class BindingClaim:
    scope: str
    name: str
    bind: Pairs  # ((slot, "name" | "scope.name"), ...)
    origin: str = ""

    def subject(self) -> str:
        return f"{self.scope}.{self.name}"

    def to_json(self) -> dict:
        return {"scope": self.scope, "name": self.name, "bind": dict(self.bind), "origin": self.origin}

    @classmethod
    def from_json(cls, data: dict) -> "BindingClaim":
        return cls(
            scope=data["scope"],
            name=data["name"],
            bind=tuple(sorted(data.get("bind", {}).items())),
            origin=data.get("origin", ""),
        )


# ---------------------------------------------------------------- target plan (Gate 1 output)


@dataclass(frozen=True)
class PlannedNode:
    scope: str
    name: str
    contract: str
    provider: str
    impl: str
    derived: bool
    config: Pairs  # ((key, Scalar), ...)
    bindings: Pairs  # ((slot, "scope.name"), ...) — always resolved node refs
    why_provider: str  # explicit-using | sole-implementation
    why_bindings: Pairs  # ((slot, explicit|rebind|sole-candidate-in-scope|derived|alias), ...)
    gives: Shape = Shape()  # what the node offers: its provider's gives ∪ its contract's

    @property
    def ref(self) -> str:
        return f"{self.scope}.{self.name}"


@dataclass(frozen=True)
class TargetPlan:
    nodes: tuple[PlannedNode, ...]  # sorted by ref
    construction_order: tuple[str, ...]  # node refs
    aliases: Pairs  # (("scope.alias", "scope.node"), ...)
    seams: tuple[Seam, ...]
    kinds: tuple[str, ...] = ()  # the kind set this plan was resolved under

    def resolve(self, ref: str) -> str:
        """Follow aliases: "gw.capture" -> "shop.capture". Unknown ref -> KeyError."""
        alias_map = self._alias_map
        seen: set[str] = set()
        cur = ref
        while cur in alias_map:
            if cur in seen:
                raise KeyError(ref)
            seen.add(cur)
            cur = alias_map[cur]
        if cur not in self._node_by_ref:
            raise KeyError(ref)
        return cur

    def node(self, ref: str) -> PlannedNode:
        """Node for a ref or an alias ref."""
        return self._node_by_ref[self.resolve(ref)]

    def names(self, scope: str) -> tuple[str, ...]:
        """Sorted names visible in `scope`: its nodes and its aliases."""
        return self._names_by_scope.get(scope, ())

    # Lookup indexes over the immutable fields; cached on first use, never part of eq/hash/JSON.
    @functools.cached_property
    def _alias_map(self) -> dict[str, str]:
        return dict(self.aliases)

    @functools.cached_property
    def _node_by_ref(self) -> dict[str, PlannedNode]:
        return {n.ref: n for n in self.nodes}

    @functools.cached_property
    def _names_by_scope(self) -> dict[str, tuple[str, ...]]:
        names: dict[str, set[str]] = {}
        for n in self.nodes:
            names.setdefault(n.scope, set()).add(n.name)
        for alias_ref, _ in self.aliases:
            scope, name = alias_ref.split(".", 1)
            names.setdefault(scope, set()).add(name)
        return {scope: tuple(sorted(v)) for scope, v in names.items()}

    def tokens(self, scope: str) -> tuple[str, ...]:
        """Sorted distinct contracts available by name in `scope` (aliases included)."""
        tokens = set()
        for name in self.names(scope):
            tokens.add(self.node(f"{scope}.{name}").contract)
        return tuple(sorted(tokens))

    def scopes(self) -> tuple[str, ...]:
        scopes = {n.scope for n in self.nodes}
        for alias_ref, _ in self.aliases:
            scopes.add(alias_ref.rsplit(".", 1)[0])
        return tuple(sorted(scopes))

    def to_json(self) -> dict:
        return {
            "nodes": [
                {
                    "scope": n.scope,
                    "name": n.name,
                    "contract": n.contract,
                    "provider": n.provider,
                    "impl": n.impl,
                    "derived": n.derived,
                    "config": {k: v for k, v in n.config},
                    "bindings": {k: v for k, v in n.bindings},
                    "why": {
                        "provider": n.why_provider,
                        "bindings": {k: v for k, v in n.why_bindings},
                    },
                    "gives": n.gives.to_json(),
                }
                for n in self.nodes
            ],
            "construction_order": list(self.construction_order),
            "aliases": {k: v for k, v in self.aliases},
            "seams": [
                {
                    "consumer": s.consumer,
                    "slot": s.slot,
                    "provider": s.provider,
                    "expected": list(s.expected),
                    "given": list(s.given),
                }
                for s in self.seams
            ],
            "kinds": list(self.kinds),
        }

    @classmethod
    def from_json(cls, data: dict) -> "TargetPlan":
        nodes = tuple(
            PlannedNode(
                scope=n["scope"],
                name=n["name"],
                contract=n["contract"],
                provider=n["provider"],
                impl=n["impl"],
                derived=n["derived"],
                config=tuple(sorted(n["config"].items())),
                bindings=tuple(sorted(n["bindings"].items())),
                why_provider=n["why"]["provider"],
                why_bindings=tuple(sorted(n["why"]["bindings"].items())),
                gives=Shape.from_json(n.get("gives", {})),
            )
            for n in data["nodes"]
        )
        seams = tuple(
            Seam(
                consumer=s["consumer"],
                slot=s["slot"],
                provider=s["provider"],
                expected=tuple(s["expected"]),
                given=tuple(s["given"]),
            )
            for s in data["seams"]
        )
        return cls(
            nodes=nodes,
            construction_order=tuple(data["construction_order"]),
            aliases=tuple(sorted(data["aliases"].items())),
            seams=seams,
            kinds=tuple(data.get("kinds", ())),
        )


def _parse_ref(ref: str, default_scope: str) -> tuple[str, str]:
    if "." in ref:
        scope, name = ref.split(".", 1)
        return scope, name
    return default_scope, ref


def _union_shape(a: Shape, b: Shape) -> Shape:
    return Shape(members=a.members | b.members, protocols=a.protocols | b.protocols)


def _group_by(claims, key_fn):
    groups: dict = {}
    for c in claims:
        groups.setdefault(key_fn(c), []).append(c)
    return groups


def _dedupe_conflicts(groups: dict, code: str, subject_fn):
    diags = []
    resolved = {}
    for key in sorted(groups, key=repr):
        group = groups[key]
        if len(group) == 1:
            resolved[key] = group[0]
            continue
        contents = {ranking.content_key(c) for c in group}
        winner = sorted(group, key=ranking.sort_key)[0]
        resolved[key] = winner
        if len(contents) > 1:
            diags.append(Diagnostic(code, subject_fn(key), 1))
    return resolved, diags


def resolve_contract_to_node(
    kind: Kind,
    claims: Iterable,
    *,
    precedence: tuple[str, ...] = (),
    max_derivation_depth: int = 8,
    strict_shapes: bool = False,
) -> tuple[TargetPlan | None, tuple[Diagnostic, ...]]:
    """Gate 1's engine. Parameterised by `kind`; contains no branch on a kind's name."""

    # Gate 1 turns "what the recipe asks for" and "what packs offer" into one TargetPlan: a node per name, each
    # bound to exactly one provider. It is a pure function of its claims (no I/O, no imports of providers), so
    # the same inputs always give the same plan and a bad recipe is diagnosed without touching hardware.
    diags: list[Diagnostic] = []

    contract_claims = [c for c in claims if isinstance(c, CapabilityContractClaim)]
    provider_claims = [c for c in claims if isinstance(c, ProviderClaim)]
    node_claims = [c for c in claims if isinstance(c, NodeClaim)]
    binding_claims = [c for c in claims if isinstance(c, BindingClaim)]
    shape_expectation_claims = [c for c in claims if isinstance(c, ShapeExpectationClaim)]

    def effective_scope(scope: str) -> str:
        return scope if kind.scoped else ""

    # ---- 1.1 index ----
    contracts_by_token, contract_diags = _dedupe_conflicts(
        _group_by(contract_claims, lambda c: c.token), "CONTRACT_CONFLICT", lambda k: f"contract:{k}"
    )
    providers_by_name, provider_diags = _dedupe_conflicts(
        _group_by(provider_claims, lambda c: c.name), "PROVIDER_CONFLICT", lambda k: f"provider:{k}"
    )
    if contract_diags or provider_diags:
        return None, tuple(sorted(contract_diags + provider_diags, key=lambda d: (d.gate, d.code, d.subject)))

    # Additive, like GoalClaim/RelationClaim in Gate 2 (D-34): every expectation for the same
    # contract unions into one shape, regardless of which contributor or consumer declared it.
    shape_expectations_by_contract: dict[str, Shape] = {}
    for c in shape_expectation_claims:
        shape_expectations_by_contract[c.contract] = _union_shape(
            shape_expectations_by_contract.get(c.contract, Shape()), c.shape
        )

    providers_by_contract: dict[str, list[str]] = {}
    for name, p in providers_by_name.items():
        providers_by_contract.setdefault(p.implements, []).append(name)
    for lst in providers_by_contract.values():
        lst.sort()

    # ---- 1.2 identity, override, alias ----
    # Several contributors may claim the same node name: the highest-ranked origin wins (precedence is the
    # recipe owner's own origin, then packs). An unresolvable tie is NAME_COLLISION, never an arbitrary pick, because
    # silently choosing a provider is how two setups end up running different code from one recipe.
    node_groups = _group_by(node_claims, lambda c: (effective_scope(c.scope), c.name))
    node_winners: dict[str, NodeClaim] = {}
    for key in sorted(node_groups, key=repr):
        group = node_groups[key]
        winner, conflict = ranking.resolve_group(group, precedence)
        ref = f"{key[0]}.{key[1]}"
        node_winners[ref] = winner
        if conflict:
            diags.append(Diagnostic("NAME_COLLISION", ref, 1))

    binding_by_key = _group_by(binding_claims, lambda c: f"{effective_scope(c.scope)}.{c.name}")
    rebound_slots: dict[str, set[str]] = {}
    for key in sorted(binding_by_key):
        group = binding_by_key[key]
        if key not in node_winners or node_winners[key].alias is not None:
            diags.append(Diagnostic("REBIND_ORPHAN", key, 1))
            continue
        per_slot: dict[str, list[tuple[str, str]]] = {}
        for bc in group:
            for slot, ref in bc.bind:
                per_slot.setdefault(slot, []).append((bc.origin, ref))
        winner_claim = node_winners[key]
        bind_dict = dict(winner_claim.bind)
        for slot in sorted(per_slot):
            entries = per_slot[slot]
            if len(entries) == 1:
                bind_dict[slot] = entries[0][1]
            else:
                best_rank = max(ranking.rank(o, precedence) for o, _ in entries)
                top = [e for e in entries if ranking.rank(e[0], precedence) == best_rank]
                values = {v for _, v in top}
                bind_dict[slot] = sorted(top, key=lambda e: e[1])[0][1]
                if len(values) > 1:
                    diags.append(Diagnostic("NAME_COLLISION", f"{key}#{slot}", 1))
            rebound_slots.setdefault(key, set()).add(slot)
        node_winners[key] = dataclasses.replace(winner_claim, bind=tuple(sorted(bind_dict.items())))

    alias_claims = {k: c for k, c in node_winners.items() if c.alias is not None}
    alias_target: dict[str, str] = {}
    for key, claim in alias_claims.items():
        scope, name = _parse_ref(claim.alias, claim.scope)
        alias_target[key] = f"{effective_scope(scope)}.{name}"

    alias_keys = set(alias_target)
    cycle_edges = frozenset((a, b) for a, b in alias_target.items() if b in alias_keys)
    cycle = graph.find_cycle(alias_keys, cycle_edges)
    if cycle:
        for key in cycle:
            diags.append(Diagnostic("ALIAS_CYCLE", key, 1))
            alias_target.pop(key, None)

    def resolve_alias_chain(key: str, seen: frozenset[str] = frozenset()) -> str | None:
        if key in seen:
            return None
        if key not in alias_target:
            return key if key in node_winners and key not in alias_claims else None
        target = alias_target[key]
        if target not in node_winners:
            return None
        return resolve_alias_chain(target, seen | {key})

    resolved_alias: dict[str, str] = {}
    for key in alias_claims:
        if key not in alias_target:
            continue
        real = resolve_alias_chain(key)
        if real is None:
            diags.append(Diagnostic("ALIAS_UNRESOLVED", key, 1))
        else:
            resolved_alias[key] = real

    visible: dict[str, dict[str, str]] = {}
    for key, claim in node_winners.items():
        if claim.alias is None:
            visible.setdefault(effective_scope(claim.scope), {})[claim.name] = key
    for akey, real in resolved_alias.items():
        aclaim = node_winners[akey]
        visible.setdefault(effective_scope(aclaim.scope), {})[aclaim.name] = real

    real_node_keys: set[str] = {k for k, c in node_winners.items() if c.alias is None}
    derived_keys: set[str] = set()

    def declared_contract(claim: NodeClaim) -> str | None:
        if claim.contract is not None:
            return claim.contract
        if claim.using is not None:
            prov = providers_by_name.get(claim.using)
            return prov.implements if prov else None
        return None

    scope_contract_index: dict[tuple[str, str], set[str]] = {}
    for scope, names in visible.items():
        for name, key in names.items():
            c = declared_contract(node_winners[key])
            if c is not None:
                scope_contract_index.setdefault((scope, c), set()).add(key)

    # ---- 1.3 provider selection (memoised; order-independent) ----
    provider_cache: dict[str, tuple[ProviderClaim | None, str | None]] = {}
    provider_diag_emitted: set[str] = set()

    def get_provider(ref: str) -> tuple[ProviderClaim | None, str | None]:
        if ref in provider_cache:
            return provider_cache[ref]
        claim = node_winners[ref]
        if claim.using is not None:
            prov = providers_by_name.get(claim.using)
            if prov is None:
                if ref not in provider_diag_emitted:
                    diags.append(Diagnostic("PROVIDER_UNKNOWN", ref, 1, (("provider", claim.using),)))
                    provider_diag_emitted.add(ref)
                result = (None, None)
            elif claim.contract is not None and prov.implements != claim.contract:
                if ref not in provider_diag_emitted:
                    diags.append(Diagnostic("PROVIDER_CONTRACT_MISMATCH", ref, 1))
                    provider_diag_emitted.add(ref)
                result = (None, None)
            else:
                result = (prov, "explicit-using")
        else:
            contract = claim.contract
            candidates = providers_by_contract.get(contract, []) if contract is not None else []
            if len(candidates) == 0:
                if ref not in provider_diag_emitted:
                    diags.append(Diagnostic("NO_PROVIDER", ref, 1))
                    provider_diag_emitted.add(ref)
                result = (None, None)
            elif len(candidates) > 1:
                if ref not in provider_diag_emitted:
                    diags.append(
                        Diagnostic(
                            "PROVIDER_AMBIGUOUS",
                            ref,
                            1,
                            evidence=tuple(("candidate", c) for c in candidates),
                        )
                    )
                    provider_diag_emitted.add(ref)
                result = (None, None)
            else:
                result = (providers_by_name[candidates[0]], "sole-implementation")
        provider_cache[ref] = result
        return result

    def resolved_contract_of(ref: str) -> str | None:
        claim = node_winners[ref]
        if claim.contract is not None:
            return claim.contract
        prov, _ = get_provider(ref)
        return prov.implements if prov else None

    working_bind: dict[str, dict[str, str]] = {}
    why_bindings: dict[str, dict[str, str]] = {}
    seams: list[Seam] = []

    def given_of(ref: str) -> Shape:
        prov, _ = get_provider(ref)
        token = resolved_contract_of(ref)
        contract_claim = contracts_by_token.get(token) if token else None
        return _union_shape(prov.gives, contract_claim.gives) if contract_claim else prov.gives

    def build_seam(consumer_ref: str, slot: str, need, target_ref: str) -> None:
        target_prov, _ = get_provider(target_ref)
        if target_prov is None:
            return
        given = given_of(target_ref)

        consumer_contract_token = resolved_contract_of(consumer_ref)
        consumer_contract_claim = contracts_by_token.get(consumer_contract_token) if consumer_contract_token else None
        expected = need.expected
        if consumer_contract_claim is not None:
            for n2 in consumer_contract_claim.needs:
                if n2.slot == slot:
                    expected = _union_shape(expected, n2.expected)
                    break
        if need.contract in shape_expectations_by_contract:
            expected = _union_shape(expected, shape_expectations_by_contract[need.contract])

        subject = f"{consumer_ref}#{slot}"
        diags.extend(shape_mismatches(subject, given, expected, 1, strict=strict_shapes))

        seams.append(
            Seam(
                consumer=consumer_ref,
                slot=slot,
                provider=target_ref,
                expected=tuple(sorted(m.name for m in expected.members)),
                given=tuple(sorted(m.name for m in given.members)),
            )
        )

    # ---- 1.4 slot binding ----
    depths: dict[str, int] = {k: 0 for k in real_node_keys}
    queue = sorted(real_node_keys)
    seen_queue: set[str] = set(queue)
    while queue:
        queue.sort()
        ref = queue.pop(0)
        claim = node_winners[ref]
        scope = effective_scope(claim.scope)
        prov, _why = get_provider(ref)
        if prov is None:
            continue
        node_bind = dict(claim.bind)
        wb = why_bindings.setdefault(ref, {})
        bd = working_bind.setdefault(ref, {})

        for need in sorted(prov.needs, key=lambda n: n.slot):
            slot = need.slot
            if slot in node_bind:
                refstr = node_bind[slot]
                rscope, rname = _parse_ref(refstr, scope)
                rscope = effective_scope(rscope)
                target_real = visible.get(rscope, {}).get(rname)
                if target_real is None:
                    diags.append(Diagnostic("BINDING_UNKNOWN", f"{ref}#{slot}", 1))
                    continue
                rkey = f"{rscope}.{rname}"
                was_alias = rkey in node_winners and node_winners[rkey].alias is not None
                target_declared = declared_contract(node_winners[target_real])
                if target_declared != need.contract:
                    diags.append(Diagnostic("BINDING_CONTRACT_MISMATCH", f"{ref}#{slot}", 1))
                    continue
                reason = "explicit"
                if slot in rebound_slots.get(ref, ()):
                    reason = "rebind"
                elif was_alias:
                    reason = "alias"
                bd[slot] = target_real
                wb[slot] = reason
                build_seam(ref, slot, need, target_real)
                continue

            candidates = scope_contract_index.get((scope, need.contract), set())
            if len(candidates) == 1:
                target_real = next(iter(candidates))
                bd[slot] = target_real
                wb[slot] = "sole-candidate-in-scope"
                build_seam(ref, slot, need, target_real)
                continue
            if len(candidates) > 1:
                diags.append(
                    Diagnostic(
                        "SLOT_AMBIGUOUS",
                        f"{ref}#{slot}",
                        1,
                        evidence=tuple(("candidate", c) for c in sorted(candidates)),
                    )
                )
                continue

            if depths[ref] + 1 > max_derivation_depth:
                diags.append(Diagnostic("DERIVATION_RUNAWAY", f"{ref}#{slot}", 1))
                continue
            dprov_candidates = providers_by_contract.get(need.contract, [])
            if len(dprov_candidates) == 0:
                diags.append(Diagnostic("SLOT_UNSATISFIED", f"{ref}#{slot}", 1))
                continue
            derived_name = f"{claim.name}.{slot}"
            derived_ref = f"{scope}.{derived_name}" if kind.scoped else derived_name
            if derived_ref not in node_winners:
                node_winners[derived_ref] = NodeClaim(
                    scope=scope,
                    name=derived_name,
                    contract=need.contract,
                    using=None,
                    bind=(),
                    config=(),
                    alias=None,
                    origin="",
                )
                real_node_keys.add(derived_ref)
                derived_keys.add(derived_ref)
                visible.setdefault(scope, {})[derived_name] = derived_ref
                scope_contract_index.setdefault((scope, need.contract), set()).add(derived_ref)
                depths[derived_ref] = depths[ref] + 1
                if derived_ref not in seen_queue:
                    queue.append(derived_ref)
                    seen_queue.add(derived_ref)
            if len(dprov_candidates) > 1:
                if derived_ref not in provider_diag_emitted:
                    diags.append(
                        Diagnostic(
                            "PROVIDER_AMBIGUOUS",
                            derived_ref,
                            1,
                            evidence=tuple(("candidate", c) for c in dprov_candidates),
                        )
                    )
                    provider_diag_emitted.add(derived_ref)
            bd[slot] = derived_ref
            wb[slot] = "derived"
            build_seam(ref, slot, need, derived_ref)

    # rebind on a slot the selected provider does not have
    for ref, slots in rebound_slots.items():
        if ref not in node_winners or node_winners[ref].alias is not None:
            continue
        prov, _ = get_provider(ref)
        if prov is None:
            continue
        provider_slots = {n.slot for n in prov.needs}
        for slot in slots:
            if slot not in provider_slots:
                diags.append(Diagnostic("REBIND_ORPHAN", f"{ref}#{slot}", 1))

    # ---- 1.5b a declared node no slot binds is still held to its contract's expectations (D-34) ----
    bound = {s.provider for s in seams}
    for ref in sorted(real_node_keys - derived_keys - bound):
        expected = shape_expectations_by_contract.get(resolved_contract_of(ref) or "")
        if expected is not None and get_provider(ref)[0] is not None:
            diags.extend(shape_mismatches(ref, given_of(ref), expected, 1))

    # ---- 1.6 target graph and order ----
    edges = frozenset((target, ref) for ref, binds in working_bind.items() for target in binds.values())
    cyc = graph.find_cycle(real_node_keys, edges)
    if cyc:
        diags.append(Diagnostic("CYCLE", cyc[0], 1, evidence=(("path", ",".join(cyc)),)))

    if diags:
        return None, tuple(sorted(diags, key=lambda d: (d.gate, d.code, d.subject)))

    construction_order = graph.toposort_kahn(real_node_keys, edges)

    nodes: list[PlannedNode] = []
    for ref in sorted(real_node_keys):
        claim = node_winners[ref]
        prov, why_provider = get_provider(ref)
        contract = claim.contract if claim.contract is not None else prov.implements
        nodes.append(
            PlannedNode(
                scope=effective_scope(claim.scope),
                name=claim.name,
                contract=contract,
                provider=prov.name,
                impl=prov.impl,
                derived=ref in derived_keys,
                config=tuple(sorted(claim.config)),
                bindings=tuple(sorted(working_bind.get(ref, {}).items())),
                why_provider=why_provider,
                why_bindings=tuple(sorted(why_bindings.get(ref, {}).items())),
                gives=given_of(ref),
            )
        )

    aliases = tuple(sorted(resolved_alias.items()))
    seams_sorted = tuple(sorted(seams, key=lambda s: (s.consumer, s.slot)))

    plan = TargetPlan(
        nodes=tuple(nodes),
        construction_order=construction_order,
        aliases=aliases,
        seams=seams_sorted,
    )
    return plan, ()


# ---------------------------------------------------------------- registration

CLAIM_TYPES = (CapabilityContractClaim, ProviderClaim, NodeClaim, BindingClaim, ShapeExpectationClaim)

CODES = frozenset(
    {
        "CONTRACT_CONFLICT",
        "PROVIDER_CONFLICT",
        "NAME_COLLISION",
        "ALIAS_UNRESOLVED",
        "ALIAS_CYCLE",
        "REBIND_ORPHAN",
        "PROVIDER_UNKNOWN",
        "PROVIDER_CONTRACT_MISMATCH",
        "NO_PROVIDER",
        "PROVIDER_AMBIGUOUS",
        "BINDING_UNKNOWN",
        "BINDING_CONTRACT_MISMATCH",
        "SLOT_AMBIGUOUS",
        "SLOT_UNSATISFIED",
        "DERIVATION_RUNAWAY",
        "CYCLE",
    }
)

CAPABILITY = Kind(
    name="capability",
    ref="contract-to-node",
    roles=frozenset({"needs"}),
    idempotent=True,
    permanent=True,
    reversible=False,
    realization="construct",
    evidence="shape",
    scoped=True,
    identity="scope-name",
)

RELATION = Relation(
    ref="contract-to-node",
    claim_types=CLAIM_TYPES,
    resolve=resolve_contract_to_node,
    codes=CODES,
)
