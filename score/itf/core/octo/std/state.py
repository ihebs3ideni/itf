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
"""Gate 2 — what must happen. From the goal states, pick the steps that deliver them (and what those
require), drop what is already observed, then order the steps so every state is still true when
something needs it: producers before consumers, destroyers before the producer they would undo.
Observed facts have probe evidence; assumed facts suppress producers too, but remain explicit in
the returned plan so callers can distinguish assertion from observation.
"""

from __future__ import annotations

import dataclasses
from typing import Iterable

from dataclasses import dataclass

from .. import graph
from ..diagnostics import Diagnostic, shape_mismatches
from ..kinds import Kind
from ..claims import Pairs
from ..plans import Edge
from ..precedence import resolve_group
from ..relations import Relation
from ..shapes import Need, Shape
from .capability import TargetPlan


# ---------------------------------------------------------------- init claims (Gate 2)


@dataclass(frozen=True)
class StateContractClaim:
    token: str  # the state this delivers
    impl: str = ""
    probe: str = ""  # "" = unprobed
    requires: frozenset[str] = frozenset()  # "token" (same scope) or "scope:token"
    invalidates: frozenset[str] = frozenset()  # same form
    also_delivers: frozenset[str] = frozenset()
    uses: tuple[Need, ...] = ()
    scope: str = ""  # "" = published template, instantiated per scope that needs it
    origin: str = ""

    def subject(self) -> str:
        return f"state:{self.token}"

    def to_json(self) -> dict:
        return {
            "token": self.token,
            "impl": self.impl,
            "probe": self.probe,
            "requires": sorted(self.requires),
            "invalidates": sorted(self.invalidates),
            "also_delivers": sorted(self.also_delivers),
            "uses": [n.to_json() for n in self.uses],
            "scope": self.scope,
            "origin": self.origin,
        }

    @classmethod
    def from_json(cls, data: dict) -> "StateContractClaim":
        return cls(
            token=data["token"],
            impl=data.get("impl", ""),
            probe=data.get("probe", ""),
            requires=frozenset(data.get("requires", ())),
            invalidates=frozenset(data.get("invalidates", ())),
            also_delivers=frozenset(data.get("also_delivers", ())),
            uses=tuple(Need.from_json(n) for n in data.get("uses", ())),
            scope=data.get("scope", ""),
            origin=data.get("origin", ""),
        )


@dataclass(frozen=True)
class GoalClaim:
    scope: str
    states: frozenset[str]
    origin: str = ""

    def subject(self) -> str:
        return f"{self.scope}:goal"

    def to_json(self) -> dict:
        return {"scope": self.scope, "states": sorted(self.states), "origin": self.origin}

    @classmethod
    def from_json(cls, data: dict) -> "GoalClaim":
        return cls(scope=data["scope"], states=frozenset(data.get("states", ())), origin=data.get("origin", ""))


@dataclass(frozen=True)
class RelationClaim:
    state: str  # token of the state contract amended
    adds_requires: frozenset[str] = frozenset()
    adds_invalidates: frozenset[str] = frozenset()
    scope: str = ""  # "" = every scope
    origin: str = ""

    def subject(self) -> str:
        return f"state:{self.state}"

    def to_json(self) -> dict:
        return {
            "state": self.state,
            "adds_requires": sorted(self.adds_requires),
            "adds_invalidates": sorted(self.adds_invalidates),
            "scope": self.scope,
            "origin": self.origin,
        }

    @classmethod
    def from_json(cls, data: dict) -> "RelationClaim":
        return cls(
            state=data["state"],
            adds_requires=frozenset(data.get("adds_requires", ())),
            adds_invalidates=frozenset(data.get("adds_invalidates", ())),
            scope=data.get("scope", ""),
            origin=data.get("origin", ""),
        )


@dataclass(frozen=True)
class AssumeClaim:
    """Treat `token` as already true in `scope` ("" = every scope) without running its producer.

    `owner` and `reason` are opaque payload, like `NodeClaim.config` (D-18): OCTO carries them
    through to the plan and never interprets them.
    """

    scope: str
    token: str
    owner: str = ""
    reason: str = ""
    origin: str = ""

    def to_json(self) -> dict:
        return {
            "scope": self.scope,
            "token": self.token,
            "owner": self.owner,
            "reason": self.reason,
            "origin": self.origin,
        }

    @classmethod
    def from_json(cls, data: dict) -> "AssumeClaim":
        return cls(
            scope=data["scope"],
            token=data["token"],
            owner=data.get("owner", ""),
            reason=data.get("reason", ""),
            origin=data.get("origin", ""),
        )


# ---------------------------------------------------------------- action plan (Gate 2 output)


@dataclass(frozen=True)
class PlannedStep:
    key: str  # first of `delivers`; identifies the step
    impl: str
    probe: str  # "" = unprobed
    delivers: tuple[str, ...]  # "scope:token", sorted; >1 when also_delivers or collapsed
    requires: tuple[str, ...]  # "scope:token", sorted
    invalidates: tuple[str, ...]  # "scope:token", sorted
    uses: Pairs  # ((slot, node ref), ...) — refs into the TargetPlan
    # ((state id, probe ref), ...) for each delivered state that has its own evidence; a collapsed
    # step keeps every contract's probe. Empty in plans written before per-state probes: then
    # `probe` vouches for every delivered state.
    probes: Pairs = ()

    def state_probes(self) -> Pairs:
        """((state id, probe ref), ...): which probe is evidence for which delivered state."""
        if self.probes:
            return self.probes
        return tuple((d, self.probe) for d in self.delivers) if self.probe else ()


@dataclass(frozen=True)
class ActionPlan:
    goals: tuple[str, ...]  # "scope:token", sorted
    observed_at_plan_time: tuple[str, ...]
    steps: tuple[PlannedStep, ...]  # in execution order
    edges: tuple[Edge, ...]
    unprobed: tuple[str, ...]  # step keys with probe == ""
    assumed: tuple[str, ...] = ()  # "scope:token", sorted — producer suppressed, no evidence (D-30)
    kinds: tuple[str, ...] = ()  # the kind set this plan was resolved under

    def to_json(self) -> dict:
        return {
            "goals": list(self.goals),
            "observed_at_plan_time": list(self.observed_at_plan_time),
            "assumed": list(self.assumed),
            "steps": [
                {
                    "key": s.key,
                    "impl": s.impl,
                    "probe": s.probe,
                    "probes": {k: v for k, v in s.probes},
                    "delivers": list(s.delivers),
                    "requires": list(s.requires),
                    "invalidates": list(s.invalidates),
                    "uses": {k: v for k, v in s.uses},
                }
                for s in self.steps
            ],
            "edges": [{"before": e.before, "after": e.after, "reason": e.reason, "state": e.state} for e in self.edges],
            "unprobed": list(self.unprobed),
            "kinds": list(self.kinds),
        }

    @classmethod
    def from_json(cls, data: dict) -> "ActionPlan":
        steps = tuple(
            PlannedStep(
                key=s["key"],
                impl=s["impl"],
                probe=s["probe"],
                delivers=tuple(s["delivers"]),
                requires=tuple(s["requires"]),
                invalidates=tuple(s["invalidates"]),
                uses=tuple(sorted(s["uses"].items())),
                probes=tuple(sorted(s.get("probes", {}).items())),
            )
            for s in data["steps"]
        )
        edges = tuple(
            Edge(before=e["before"], after=e["after"], reason=e["reason"], state=e["state"]) for e in data["edges"]
        )
        return cls(
            goals=tuple(data["goals"]),
            observed_at_plan_time=tuple(data["observed_at_plan_time"]),
            steps=steps,
            edges=edges,
            unprobed=tuple(data["unprobed"]),
            assumed=tuple(data.get("assumed", ())),
            kinds=tuple(data.get("kinds", ())),
        )


def _parse_state_ref(ref: str, default_scope: str) -> tuple[str, str]:
    if ":" in ref:
        scope, token = ref.split(":", 1)
        return scope, token
    return default_scope, ref


def resolve_condition_to_producer(
    kind: Kind,
    claims: Iterable,
    target: TargetPlan,
    *,
    precedence: tuple[str, ...] = (),
    observed_states: frozenset[str] = frozenset(),
    assumed_states: frozenset[str] = frozenset(),
    strict_shapes: bool = False,
) -> tuple[ActionPlan | None, tuple[Diagnostic, ...]]:
    # Gate 2 plans from the target plan, so a state can only be produced by actions whose `uses` slots the
    # target can fill; an action that needs a console on a target without one is reported, not skipped.
    # Planning works backwards from goals (what the recipe wants true), pulling in only the actions needed,
    # which is why an unrelated local action costs nothing unless a recipe relates a state to it.
    diags: list[Diagnostic] = []
    reported: set[tuple[str, str]] = set()

    def add_diag(code: str, subject: str, evidence: tuple = ()) -> None:
        if (code, subject) in reported:
            return
        reported.add((code, subject))
        diags.append(Diagnostic(code, subject, 2, evidence))

    if not kind.scoped:
        claims = [dataclasses.replace(c, scope="") if hasattr(c, "scope") else c for c in claims]
    state_claims = [c for c in claims if isinstance(c, StateContractClaim)]
    goal_claims = [c for c in claims if isinstance(c, GoalClaim)]
    relation_claims = [c for c in claims if isinstance(c, RelationClaim)]
    assume_claims = [c for c in claims if isinstance(c, AssumeClaim)]

    # ---- assumptions: a producer suppressed on the caller's word, never on evidence (D-30) ----
    assume_groups = _group_by_key(assume_claims, lambda c: (c.scope, c.token))
    assumed_scoped: set[str] = set()  # "scope:token", scope != ""
    assumed_global: set[str] = set()  # bare token, scope == ""
    for key in sorted(assume_groups):
        winner, conflict = resolve_group(assume_groups[key], precedence)
        if conflict:
            add_diag("ASSUMPTION_CONFLICT", f"state:{key[1]}")
            continue
        if winner.scope:
            assumed_scoped.add(f"{winner.scope}:{winner.token}")
        else:
            assumed_global.add(winner.token)
    assumed_scoped |= set(assumed_states)  # request-level: no claim needed, just the one call

    def is_assumed(scope: str, token: str) -> bool:
        return f"{scope}:{token}" in assumed_scoped or token in assumed_global

    def satisfied_without_action(state_id: str) -> bool:
        if state_id in observed_states:
            return True
        scope, token = _parse_state_ref(state_id, "")
        return is_assumed(scope, token)

    # ---- identity, override (templates scope="", instances scope!="") ----
    groups = _group_by_key(state_claims, lambda c: (c.scope, c.token))
    winners: dict[tuple[str, str], StateContractClaim] = {}
    for key in sorted(groups):
        winner, conflict = resolve_group(groups[key], precedence)
        winners[key] = winner
        if conflict:
            add_diag("STATE_CONFLICT", f"state:{key[1]}")

    templates = {token: c for (scope, token), c in winners.items() if scope == ""}
    overrides = {(scope, token): c for (scope, token), c in winners.items() if scope != ""}
    known_tokens = set(templates) | {t for (_, t) in overrides}

    # ---- relation merging ----
    relations_by_token: dict[str, list[RelationClaim]] = {}
    for rc in relation_claims:
        if rc.state not in known_tokens:
            add_diag("RELATION_ORPHAN", f"state:{rc.state}")
            continue
        relations_by_token.setdefault(rc.state, []).append(rc)

    def instantiate(scope: str, token: str) -> StateContractClaim | None:
        claim = overrides.get((scope, token))
        if claim is None:
            for (s, t), c in overrides.items():
                if s == scope and token in c.also_delivers:
                    claim = c
                    break
        if claim is None and token in templates:
            claim = dataclasses.replace(templates[token], scope=scope)
        if claim is None:
            for t, c in templates.items():
                if token in c.also_delivers:
                    claim = dataclasses.replace(c, scope=scope)
                    break
        if claim is None:
            return None
        if claim.scope != scope:
            claim = dataclasses.replace(claim, scope=scope)
        adds_req: frozenset[str] = frozenset()
        adds_inv: frozenset[str] = frozenset()
        for rc in relations_by_token.get(claim.token, ()):
            if rc.scope in ("", scope):
                adds_req |= rc.adds_requires
                adds_inv |= rc.adds_invalidates
        if adds_req or adds_inv:
            claim = dataclasses.replace(
                claim, requires=claim.requires | adds_req, invalidates=claim.invalidates | adds_inv
            )
        return claim

    # ---- action selection: transitive closure from goals ----
    instances: dict[tuple[str, str], StateContractClaim] = {}
    observed_only: set[tuple[str, str]] = set()
    goals: set[str] = set()
    todo: list[tuple[str, str]] = []
    wanted_by: dict[tuple[str, str], tuple[str, str] | None] = {}  # None: a goal
    for gc in goal_claims:
        for tok in gc.states:
            goals.add(f"{gc.scope}:{tok}")
            todo.append((gc.scope, tok))
            wanted_by[(gc.scope, tok)] = None

    seen_ok: set[tuple[str, str]] = set()
    seen_bad: set[tuple[str, str]] = set()
    while todo:
        todo.sort()
        item = todo.pop(0)
        if item in seen_ok or item in seen_bad:
            continue
        scope, token = item
        claim = instantiate(scope, token)
        if claim is None:
            if f"{scope}:{token}" in observed_states or is_assumed(scope, token):
                seen_ok.add(item)
                observed_only.add(item)
            else:
                add_diag("STATE_UNREACHABLE", f"state:{token}")
                seen_bad.add(item)
            continue
        primary_key = (scope, claim.token)
        seen_ok.add(item)
        seen_ok.add(primary_key)
        if primary_key not in instances:
            instances[primary_key] = claim
            for req in claim.requires:
                rscope, rtoken = _parse_state_ref(req, scope)
                wanted_by.setdefault((rscope, rtoken), (scope, claim.token))
                if (rscope, rtoken) not in seen_ok and (rscope, rtoken) not in seen_bad:
                    todo.append((rscope, rtoken))

    if diags:
        return None, tuple(sorted(diags, key=lambda d: (d.gate, d.code, d.subject)))

    # ---- bind `uses` against the target plan (per instance, in its own scope) ----
    resolved_uses: dict[tuple[str, str], tuple[tuple[str, str], ...]] = {}
    for key, claim in instances.items():
        scope, token = key
        uses_pairs = []
        for need in sorted(claim.uses, key=lambda n: n.slot):
            ref, ambiguous_candidates = _bind_use(target, scope, need)
            subject = f"{scope}:{token}#{need.slot}"
            if ref is None:
                if ambiguous_candidates:
                    add_diag("USES_AMBIGUOUS", subject, evidence=tuple(("candidate", c) for c in ambiguous_candidates))
                else:
                    add_diag(
                        "USES_UNSATISFIED",
                        subject,
                        evidence=_unsatisfied_evidence(target, scope, token, claim, need, wanted_by),
                    )
                continue
            for d in shape_mismatches(subject, target.node(ref).gives, need.expected, 2, strict=strict_shapes):
                add_diag(d.code, d.subject, d.evidence)
            uses_pairs.append((need.slot, ref))
        resolved_uses[key] = tuple(sorted(uses_pairs))

    if diags:
        return None, tuple(sorted(diags, key=lambda d: (d.gate, d.code, d.subject)))

    # ---- qualify requires/invalidates/delivers; collapse by (impl, uses) ----
    def qualify(raw: frozenset[str], scope: str) -> frozenset[str]:
        out = set()
        for r in raw:
            rscope, rtoken = _parse_state_ref(r, scope)
            out.add(f"{rscope}:{rtoken}")
        return frozenset(out)

    prelim = []
    for key, claim in sorted(instances.items()):
        scope, token = key
        delivers = frozenset({f"{scope}:{token}"} | {f"{scope}:{d}" for d in claim.also_delivers})
        prelim.append(
            {
                "instance_key": key,
                "impl": claim.impl,
                "probe": claim.probe,
                "delivers": delivers,
                "requires": qualify(claim.requires, scope),
                "invalidates": qualify(claim.invalidates, scope),
                "uses": resolved_uses[key],
            }
        )

    collapse_groups: dict[tuple[str, tuple], list[dict]] = {}
    for entry in prelim:
        collapse_key = (entry["impl"], entry["uses"])
        collapse_groups.setdefault(collapse_key, []).append(entry)

    steps_by_key: dict[str, dict] = {}
    for group in collapse_groups.values():
        delivers = frozenset().union(*(e["delivers"] for e in group))
        requires = frozenset().union(*(e["requires"] for e in group))
        invalidates = frozenset().union(*(e["invalidates"] for e in group))
        key = min(delivers)
        # Each contract's probe stays evidence for exactly the states that contract delivers.
        probes = {d: e["probe"] for e in group if e["probe"] for d in e["delivers"]}
        steps_by_key[key] = {
            "key": key,
            "impl": group[0]["impl"],
            "probe": probes.get(key) or next((e["probe"] for e in group if e["probe"]), ""),
            "probes": tuple(sorted(probes.items())),
            "delivers": delivers,
            "requires": requires,
            "invalidates": invalidates,
            "uses": group[0]["uses"],
        }

    # ---- observed_states pruning (with re-delivery) ----
    def is_observed(state_id: str) -> bool:
        return satisfied_without_action(state_id)

    # Fixed point: a pruned step is only re-delivered if an *active* step destroys its state.
    active_keys = {k for k, s in steps_by_key.items() if not all(is_observed(x) for x in s["delivers"])}
    changed = True
    while changed:
        changed = False
        for key in sorted(steps_by_key):
            if key in active_keys:
                continue
            step = steps_by_key[key]
            if any(step["delivers"] & steps_by_key[a]["invalidates"] for a in sorted(active_keys) if a != key):
                active_keys.add(key)
                changed = True
    active = {k: v for k, v in steps_by_key.items() if k in active_keys}

    # ---- edge derivation ----
    edges: list[Edge] = []
    edge_set: set[tuple[str, str]] = set()

    def add_edge(before: str, after: str, reason: str, state: str) -> None:
        edges.append(Edge(before=before, after=after, reason=reason, state=state))
        edge_set.add((before, after))

    keys_sorted = sorted(active)
    consumers: dict[str, list[str]] = {}
    for b in keys_sorted:
        for s in active[b]["requires"]:
            consumers.setdefault(s, []).append(b)
    for a in keys_sorted:
        # same order as iterating every b, then every shared state, both sorted
        for b, s in sorted((b, s) for s in active[a]["delivers"] for b in consumers.get(s, ()) if b != a):
            add_edge(a, b, "delivers-requires", s)

    cyc = graph.find_cycle(keys_sorted, frozenset(edge_set))
    if cyc:
        add_diag("STATE_CYCLE", cyc[0])
        return None, tuple(sorted(diags, key=lambda d: (d.gate, d.code, d.subject)))

    if "destroys" in kind.roles:
        conflict = _protect_causal_links(active, keys_sorted, goals, edge_set, add_edge)
        if conflict:
            add_diag("ORDER_AMBIGUOUS", min(conflict), evidence=(("between", " , ".join(sorted(conflict))),))
            return None, tuple(sorted(diags, key=lambda d: (d.gate, d.code, d.subject)))

    if diags:
        return None, tuple(sorted(diags, key=lambda d: (d.gate, d.code, d.subject)))

    order = graph.toposort_kahn(keys_sorted, frozenset(edge_set))

    steps = tuple(
        PlannedStep(
            key=active[k]["key"],
            impl=active[k]["impl"],
            probe=active[k]["probe"],
            delivers=tuple(sorted(active[k]["delivers"])),
            requires=tuple(sorted(active[k]["requires"])),
            invalidates=tuple(sorted(active[k]["invalidates"])),
            uses=active[k]["uses"],
            probes=tuple((d, ref) for d, ref in active[k].get("probes", ()) if d in active[k]["delivers"]),
        )
        for k in order
    )
    unprobed = tuple(sorted(k for k in order if active[k]["probe"] == ""))

    # Of every state this resolution touched, the ones taken on the caller's word rather than
    # observed or executed — visible so a plan never implies evidence that was never gathered.
    # A state re-delivered because an active step destroys it ran for real: it is not an assumption.
    touched_ids = {f"{s}:{t}" for s, t in seen_ok}
    delivered_by_active = frozenset().union(*(s["delivers"] for s in active.values())) if active else frozenset()
    assumed = tuple(
        sorted(x for x in touched_ids if is_assumed(*_parse_state_ref(x, "")) and x not in delivered_by_active)
    )

    plan = ActionPlan(
        goals=tuple(sorted(goals)),
        observed_at_plan_time=tuple(sorted(observed_states)),
        steps=steps,
        edges=tuple(edges),
        unprobed=unprobed,
        assumed=assumed,
    )
    return plan, ()


# Planner ordering needs more than dependency edges: an action that invalidates a state (a restart drops the
# connection) must not run between the action that delivers it and the step that relies on it. This is the
# classic STRIPS threat-resolution step, kept deterministic so plans are stable across runs.
def _protect_causal_links(active, keys, goals, edge_set, add_edge) -> tuple[str, str] | None:
    """Order every destroyer so no causal link it threatens is broken (STRIPS threat resolution).

    A link is (producer, state, consumer): the producer delivers the state and the consumer needs it
    to still hold — a step that requires it, or the end of the plan when it is a goal. A destroyer D
    of that state must run before the producer or after the consumer. Forced choices are applied to
    a fixed point; a free choice defaults to destroy-then-produce. Returns the conflicting pair when
    no consistent order exists.
    """
    producer: dict[str, str] = {}
    for k in keys:
        for s in sorted(active[k]["delivers"]):
            producer.setdefault(s, k)

    links: list[tuple[str | None, str, str | None]] = []
    for c in keys:
        for s in sorted(active[c]["requires"]):
            links.append((producer.get(s), s, c))
    for g in sorted(goals):
        if g in producer:
            links.append((producer[g], g, None))

    destroyers: dict[str, list[str]] = {}
    for d in keys:
        for s in active[d]["invalidates"]:
            destroyers.setdefault(s, []).append(d)
    open_threats: list[tuple[str, str | None, str | None, str]] = []
    for p, s, c in links:
        for d in destroyers.get(s, ()):
            if d not in (p, c):
                open_threats.append((d, p, c, s))

    # Reachability kept exact as edges are added, instead of recomputed after every decision.
    succ: dict[str, set[str]] = {k: set() for k in keys}
    for a, b in graph.reachable_pairs(keys, frozenset(edge_set)):
        succ[a].add(b)

    def connect(a: str, b: str, s: str) -> None:
        add_edge(a, b, "invalidates", s)
        targets = {b} | succ[b]
        for x in keys:
            if x == a or a in succ[x]:
                succ[x] |= targets

    while open_threats:
        undecided = []
        progressed = False
        for d, p, c, s in open_threats:
            before_ok = p is not None and d != p and d not in succ[p]
            after_ok = c is not None and c not in succ[d]
            if (p is not None and p in succ[d]) or (c is not None and d in succ[c]):
                continue
            if not before_ok and not after_ok:
                return (d, c if c is not None else p)
            if before_ok != after_ok:
                if before_ok:
                    connect(d, p, s)
                else:
                    connect(c, d, s)
                progressed = True
                break
            undecided.append((d, p, c, s))
        if progressed:
            continue
        if not undecided:
            return None
        d, p, c, s = undecided[0]
        connect(d, p, s)
        open_threats = undecided[1:]
    return None


def _group_by_key(claims, key_fn):
    groups: dict = {}
    for c in claims:
        groups.setdefault(key_fn(c), []).append(c)
    return groups


def _unsatisfied_evidence(target: TargetPlan, scope: str, token: str, claim, need, wanted_by) -> tuple:
    """What a reader needs to fix a missing `uses`: what was needed, by whom, why, and where it exists."""
    chain, key = [], (scope, token)
    while wanted_by.get(key) is not None and len(chain) < len(wanted_by):
        key = wanted_by[key]
        chain.append(f"{key[0]}:{key[1]}")
    elsewhere = sorted(n.ref for n in target.nodes if n.contract == need.contract and n.scope != scope)
    return tuple(
        sorted(
            {
                "action": claim.impl,
                "contract": need.contract,
                "elsewhere": ", ".join(elsewhere),
                "required_by": " <- ".join(chain),
                "scope": scope,
                "slot": need.slot,
            }.items()
        )
    )


def _bind_use(target: TargetPlan, scope: str, need) -> tuple[str | None, tuple[str, ...] | None]:
    """The four-step rule, restricted to Gate 2's `uses` variant: by-name, then sole
    candidate in scope. Returns (ref, None) on success, (None, ()) unsatisfied,
    (None, candidates) ambiguous."""
    names = target.names(scope)
    slot = need.slot
    if slot in names:
        node = target.node(f"{scope}.{slot}")
        if node.contract == need.contract:
            return target.resolve(f"{scope}.{slot}"), None

    candidates = set()
    for name in names:
        node = target.node(f"{scope}.{name}")
        if node.contract == need.contract:
            candidates.add(target.resolve(f"{scope}.{name}"))
    candidates = sorted(candidates)
    if len(candidates) == 1:
        return candidates[0], None
    if len(candidates) == 0:
        return None, ()
    return None, tuple(candidates)


# ---------------------------------------------------------------- registration

CLAIM_TYPES = (StateContractClaim, GoalClaim, RelationClaim, AssumeClaim)

CODES = frozenset(
    {
        "STATE_CONFLICT",
        "RELATION_ORPHAN",
        "USES_UNSATISFIED",
        "USES_AMBIGUOUS",
        "STATE_UNREACHABLE",
        "STATE_CYCLE",
        "ORDER_AMBIGUOUS",
        "ASSUMPTION_CONFLICT",
    }
)

STATE = Kind(
    name="state",
    ref="condition-to-producer",
    roles=frozenset({"needs", "produces", "destroys", "uses"}),
    idempotent=False,
    permanent=False,
    reversible=True,
    realization="invoke",
    evidence="probe",
    scoped=True,
    identity="token",
)

RELATION = Relation(
    ref="condition-to-producer",
    claim_types=CLAIM_TYPES,
    resolve=resolve_condition_to_producer,
    codes=CODES,
    edge_reasons=frozenset({"delivers-requires", "invalidates"}),
    upstream="contract-to-node",
)
