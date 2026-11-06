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

A requirement can also sit on a test class (`@itf.requires` on the class; subclasses inherit it), on a module
(`itf_requires = itf.requires(...)`, or a list of them) or on a package (the same line in its `__init__.py`). A
test needs every requirement on it and above it.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from .engine.publish import split_major
from .engine.scopes import ROOT

_MARK = "__itf_requirements__"
MODULE_ATTR = "itf_requires"  # a module's or a package's requirements


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
    return Requires(Requirement(role, name, tuple(shape) if shape else None, scope, major))


@dataclass(frozen=True)
class Requires:
    """What `itf.requires(...)` returns: a decorator for a test function or class, and the value of a module's
    or a package's `itf_requires`."""

    requirement: Requirement

    def __call__(self, test):
        setattr(test, _MARK, getattr(test, _MARK, ()) + (self.requirement,))
        return test


def get_requirements(func) -> tuple[Requirement, ...]:
    return getattr(func, _MARK, ())


def requirements_of(func, cls=None, module=None) -> tuple[Requirement, ...]:
    """Every requirement a test has: its packages' (outermost first), its module's, its class's, its own."""
    found: list[Requirement] = []
    if module is not None:
        parts = module.__name__.split(".")
        for i in range(1, len(parts)):
            found += _module_requirements(sys.modules.get(".".join(parts[:i])))
        found += _module_requirements(module)
    if cls is not None:
        found += getattr(cls, _MARK, ())
    found += get_requirements(func) if func is not None else ()
    return tuple(dict.fromkeys(found))


def _module_requirements(module) -> list[Requirement]:
    value = getattr(module, MODULE_ATTR, ()) if module is not None else ()
    items = value if isinstance(value, (list, tuple)) else [value]
    if not all(isinstance(item, Requires) for item in items):
        raise TypeError(f"{module.__name__}.{MODULE_ATTR} must be itf.requires(...) or a list of them, got {value!r}")
    return [item.requirement for item in items]


@dataclass(frozen=True)
class GatingDecision:
    selected: bool
    reason: str = ""


def _wrong_contract(requirement: Requirement, node, where: str, factory_majors) -> str | None:
    if requirement.contract is None or node.contract == requirement.contract:
        return None
    return f"{where} ({node.provider}) is {node.contract!r}, the test requires {requirement.contract!r}"


def _wrong_major(requirement: Requirement, node, where: str, factory_majors) -> str | None:
    offered = (factory_majors or {}).get(node.provider)
    if requirement.major is None or offered is None or offered == requirement.major:
        return None
    return f"{where} ({node.provider}) offers @{offered}, the test requires @{requirement.major}"


def _missing_members(requirement: Requirement, node, where: str, factory_majors) -> str | None:
    have = {m.name for m in node.gives.members}
    missing = [m for m in requirement.shape or () if m not in have]
    return f"{where} ({node.provider}) lacks member(s): {', '.join(missing)}" if missing else None


def evaluate(requirement: Requirement, target_plan, scope: str, factory_majors: dict | None = None) -> GatingDecision:
    label = "target" if scope == ROOT else f"target.{scope}"
    role = requirement.role
    names = target_plan.names(scope)
    if role not in names:
        return GatingDecision(False, f"{label} has no role {role!r}; roles: {', '.join(names) or '(none)'}")
    node = target_plan.node(f"{scope}.{role}")
    for rule in (_wrong_contract, _wrong_major, _missing_members):
        reason = rule(requirement, node, f"{label}.{role}", factory_majors)
        if reason is not None:
            return GatingDecision(False, reason)
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
