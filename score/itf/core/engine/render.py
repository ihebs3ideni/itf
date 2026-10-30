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
"""One template per OCTO diagnostic code (docs/octo-kit/11-spec-itf-engine.md §11).

`CODES` is the closed set (`score.itf.core.octo.CODES`: core codes plus every standard relation's); a test enumerates it against `TEMPLATES`
so a code with no template fails the build (A-3.6).
"""

from __future__ import annotations

from ..octo.diagnostics import Diagnostic
from .scopes import ROOT, display


def _evidence(d: Diagnostic) -> dict:
    return dict(d.evidence)


def _t(summary: str, fix: str):
    def render_one(d: Diagnostic) -> str:
        ev = _evidence(d)
        return f"{d.subject}: {summary.format(d=d, ev=ev)}\n  Fix: {fix.format(d=d, ev=ev)}"

    return render_one


def _uses_unsatisfied(d: Diagnostic) -> str:
    ev = _evidence(d)
    if "contract" not in ev:
        return (
            f"{d.subject}: the action at '{d.subject}' needs a capability the target plan does not have\n"
            "  Fix: add the needed node in this scope, or bind it explicitly"
        )
    scope, slot, contract = ev["scope"], ev["slot"], ev["contract"]
    state = d.subject.split("#", 1)[0]
    where = "the root scope" if scope == ROOT else f"scope '{scope}'"
    why = f"{state} is required by {ev['required_by']} (a goal)" if ev.get("required_by") else f"{state} is a goal"
    verb = "ctx" if scope == ROOT else f"ctx.scope('{scope}')"
    lines = [
        f"{d.subject}: {where} has no '{contract}' node, and reaching {state} needs one",
        f"  Needed by: {ev['action']}, slot '{slot}' (uses={{'{slot}': '{contract}'}})",
        f"  Why: {why}",
    ]
    if ev.get("elsewhere"):
        lines.append(f"  Exists in: {ev['elsewhere']}")
        lines.append(
            f"  Fix: share one into this scope, {verb}.alias('{slot}', "
            f"'{ev['elsewhere'].split(', ')[0]}'); or add a '{contract}' node here; "
            f"or drop {state} from this scope's goals"
        )
    else:
        lines.append(
            f"  Fix: add a node in this scope, {verb}.add('{slot}', '{contract}', using=...); "
            f"or drop {state} from this scope's goals"
        )
    return "\n".join(lines)


TEMPLATES = {
    "CONTRACT_CONFLICT": _t(
        "two contracts claim the token '{d.subject}' at the same precedence",
        "declare ctx.contract('{d.subject}', ...) once, or give one claim a higher origin",
    ),
    "PROVIDER_CONFLICT": _t(
        "two providers publish the name '{d.subject}'",
        "rename one provider's name=; provider names must be unique per session",
    ),
    "NAME_COLLISION": _t(
        "two claims collide on '{d.subject}' with no precedence to break the tie",
        "give one of them a higher origin, or use scope.rebind(...) to change one wire",
    ),
    "ALIAS_UNRESOLVED": _t(
        "alias '{d.subject}' points at a node that does not exist",
        "check the target of scope.alias(name, 'scope.name'); the target must be add()-ed somewhere",
    ),
    "ALIAS_CYCLE": _t(
        "alias '{d.subject}' is part of a cycle of aliases",
        "break the cycle: an alias must eventually resolve to a real scope.add(...) node",
    ),
    "REBIND_ORPHAN": _t(
        "scope.rebind('{d.subject}') targets a node that was never scope.add()-ed",
        "add the node first, or remove the rebind",
    ),
    "PROVIDER_UNKNOWN": _t(
        "using='{d.subject}' names a provider nobody published",
        "check the provider's name=, and that its pack is listed in pytest_plugins",
    ),
    "PROVIDER_CONTRACT_MISMATCH": _t(
        "using='{d.subject}' implements a different contract than the node declares",
        "match scope.add(name, contract, using=...) so contract equals the provider's implements",
    ),
    "NO_PROVIDER": _t(
        "no provider implements the contract needed at '{d.subject}'",
        "publish or select a provider for this contract with using=",
    ),
    "PROVIDER_AMBIGUOUS": _t(
        "more than one provider implements the contract needed at '{d.subject}'",
        "name one explicitly: scope.add(name, contract, using='<provider name>')",
    ),
    "BINDING_UNKNOWN": _t(
        "scope.rebind names a slot '{d.subject}' the node does not have",
        "check the provider's needs= for the correct slot name",
    ),
    "BINDING_CONTRACT_MISMATCH": _t(
        "the node bound to slot '{d.subject}' does not satisfy the slot's contract",
        "bind the slot to a node of the expected contract, via bind={{'slot': 'scope.name'}}",
    ),
    "SLOT_AMBIGUOUS": _t(
        "two candidates fill slot '{d.subject}': {ev}",
        "name one: scope.add(name, contract, using=..., bind={{'slot': '<one of the candidates>'}})",
    ),
    "SLOT_UNSATISFIED": _t(
        "slot '{d.subject}' has no candidate in scope and none could be derived",
        "add a node of the needed contract in this scope, or bind={{'slot': 'scope.name'}} explicitly",
    ),
    "DERIVATION_RUNAWAY": _t(
        "deriving a node for '{d.subject}' exceeded max_derivation_depth",
        "add the missing node explicitly instead of relying on derivation",
    ),
    "CYCLE": _t(
        "a construction cycle passes through '{d.subject}'",
        "break the cycle: one of these bindings must point elsewhere",
    ),
    "STATE_CONFLICT": _t(
        "two state contracts claim the token '{d.subject}' at the same precedence",
        "choose one by name: ctx.state('{d.subject}', using='<action name>')",
    ),
    "RELATION_ORPHAN": _t(
        "scope.relate('{d.subject}', ...) amends a state contract nobody published",
        "check the state token, or publish/select it first with ctx.state(...)",
    ),
    "USES_UNSATISFIED": _uses_unsatisfied,
    "USES_AMBIGUOUS": _t(
        "more than one node could fill the action's use at '{d.subject}': {ev}",
        "name the node explicitly with scope.rebind or scope.add(bind=...)",
    ),
    "STATE_UNREACHABLE": _t(
        "the state '{d.subject}' cannot be reached: no action delivers it and it was not observed",
        "publish or select an action delivering this state: ctx.state('{d.subject}', using=...)",
    ),
    "STATE_CYCLE": _t(
        "a temporal cycle passes through '{d.subject}'",
        "one of these requires/invalidates relations must be removed with scope.relate(...)",
    ),
    "ORDER_AMBIGUOUS": _t(
        "two actions mutually invalidate each other's state near '{d.subject}' with no derivable order",
        "add a third-party relation: scope.relate(state, requires=(...)) to break the tie",
    ),
    "ASSUMPTION_CONFLICT": _t(
        "two assume() declarations for '{d.subject}' disagree at the same precedence",
        "give one a higher origin, or align their owner=/reason= so they are identical",
    ),
    "SHAPE_MISSING_MEMBER": _t(
        "the seam at '{d.subject}' is missing member(s): {ev}",
        "either the provider's gives= must include them, or lower the consumer's expect(...) shape",
    ),
    "SHAPE_SIGNATURE_DRIFT": _t(
        "the seam at '{d.subject}' has a signature mismatch: {ev}",
        "align the provider's gives= signature with the consumer's expect(...) shape",
    ),
    "SHAPE_PROTOCOL_MISSING": _t(
        "the seam at '{d.subject}' does not satisfy the expected protocol: {ev}",
        "have the provider's gives= declare the protocol, or lower the consumer's expect(...) shape",
    ),
    "SHAPE_UNDECLARED": _t(
        "the seam at '{d.subject}' declares no shape under strict_shapes=True",
        "wrap the need in expect(contract, shape), naming at least the members this consumer relies on",
    ),
    "CLAIM_WRONG_GATE": _t(
        "a claim for '{d.subject}' was offered to the wrong gate",
        "capability claims (contract/add/alias/rebind) belong to itf_setup; state claims "
        "(goal/relate/state) belong to itf_init",
    ),
    "UNKNOWN_KIND": _t(
        "a '{d.subject}' was offered to the planner, but no registered contract kind owns that claim type",
        "only ctx verbs produce claims; pass claims from score.itf.core.octo, or register the kind that owns it",
    ),
    "RELATION_FAILED": _t(
        "the planner for '{d.subject}' contracts failed instead of answering: {ev}",
        "this is a defect in that kind's relation, not in your recipe; report it with the evidence above",
    ),
}


def render(diagnostics, *, gate: int, hook: str) -> str:
    lines = [f"Gate {gate} · {hook}"]
    for d in diagnostics:
        template = TEMPLATES.get(d.code)
        if template is None:
            lines.append(f"{d.subject}: {d.code} (no template)")
        else:
            lines.append(template(d))
    return display("\n".join(lines))
