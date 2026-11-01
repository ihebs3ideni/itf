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
"""`@itf.requires` and gating tests against the plan.

A test asks for a role: `@itf.requires("command")` means the target has a role `command`; `contract=` and
`shape=` narrow it: `@itf.requires("command", contract="exec.command", shape=["exec"])`. The test then uses
`target.command`. A test is deselected, before anything is built, with a reason naming what the target has:
the role is missing, it has another contract, or it lacks members. Which role names a project uses is the
project's convention; `itf contracts check` can enforce it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .engine.publish import split_major
from .engine.scopes import ROOT

_MARK = "__itf_requirements__"


@dataclass(frozen=True)
class Requirement:
    role: str
    contract: str | None = None
    shape: tuple[str, ...] | None = None
    scope: str | None = None
    major: int | None = None


@dataclass(frozen=True)
class Definition:
    """What a session may know about a defined contract, handed in (the engine never needs it)."""

    contract: str
    version: int | None = None
    stability: str = "stable"  # experimental | stable | deprecated
    replaced_by: str | None = None


def requires(role: str, contract: str | None = None, shape=None, scope: str | None = None):
    """The test needs the role `role` of the target (`target.<role>`), optionally of `contract` (with `@<major>`)
    and offering the members in `shape`; `scope` names a scope instead of the root."""
    if not isinstance(role, str) or not role:
        raise TypeError("@itf.requires takes a role name, for example @itf.requires('command')")
    if isinstance(shape, str):
        raise TypeError("shape is a list of member names, not a string")
    name, major = split_major(contract) if contract else (None, None)
    req = Requirement(role, name, tuple(shape) if shape else None, scope, major)

    def deco(func):
        setattr(func, _MARK, getattr(func, _MARK, ()) + (req,))
        return func

    return deco


def get_requirements(func) -> tuple[Requirement, ...]:
    return getattr(func, _MARK, ())


@dataclass(frozen=True)
class GatingDecision:
    selected: bool
    reason: str = ""


def evaluate(requirement: Requirement, target_plan, scope: str, factory_majors: dict | None = None) -> GatingDecision:
    label = "target" if scope == ROOT else f"target.{scope}"
    role = requirement.role
    names = target_plan.names(scope)
    if role not in names:
        return GatingDecision(False, f"{label} has no role {role!r}; roles: {', '.join(names) or '(none)'}")
    node = target_plan.node(f"{scope}.{role}")
    if requirement.contract is not None and node.contract != requirement.contract:
        return GatingDecision(
            False, f"{label}.{role} ({node.provider}) is {node.contract!r}, the test requires {requirement.contract!r}"
        )
    if requirement.major is not None:
        offered = (factory_majors or {}).get(node.provider)
        if offered is not None and offered != requirement.major:
            return GatingDecision(
                False, f"{label}.{role} ({node.provider}) offers @{offered}, the test requires @{requirement.major}"
            )
    if requirement.shape:
        have = {m.name for m in node.gives.members}
        missing = [m for m in requirement.shape if m not in have]
        if missing:
            return GatingDecision(False, f"{label}.{role} ({node.provider}) lacks member(s): {', '.join(missing)}")
    return GatingDecision(True)


def deprecations(target_plan, definitions: dict | None) -> list[str]:
    """Plan-time warnings: a role's contract is defined as deprecated (only when definitions are loaded)."""
    found = []
    for node in target_plan.nodes:
        definition = (definitions or {}).get(node.contract)
        if definition is not None and definition.stability == "deprecated":
            use = f"; use {definition.replaced_by!r}" if definition.replaced_by else ""
            found.append(f"role {node.name} ({node.provider}) is {node.contract!r}, which is deprecated{use}")
    return found
