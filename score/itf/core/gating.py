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
"""`@itf.requires` and gating tests against the plan (docs/octo-kit/12-spec-itf-core.md §5)."""

from __future__ import annotations

from dataclasses import dataclass

from .engine.scopes import ROOT

_MARK = "__itf_requirements__"


@dataclass(frozen=True)
class Requirement:
    token: str
    shape: tuple[str, ...] | None = None
    scope: str | None = None


def requires(token: str, shape=None, scope: str | None = None):
    req = Requirement(token, tuple(shape) if shape else None, scope)

    def deco(func):
        existing = getattr(func, _MARK, ())
        setattr(func, _MARK, existing + (req,))
        return func

    return deco


def get_requirements(func) -> tuple[Requirement, ...]:
    return getattr(func, _MARK, ())


@dataclass(frozen=True)
class GatingDecision:
    selected: bool
    reason: str = ""


# Gating reads the plan, never a live target: a test is deselected before anything is built, with a reason
# that names what the target has. This is what lets one suite run against many recipes.
def evaluate(requirement: Requirement, target_plan, scope: str, provider_gives: dict) -> GatingDecision:
    label = "target" if scope == ROOT else f"target.{scope}"
    tokens = target_plan.tokens(scope)
    if requirement.token not in tokens:
        return GatingDecision(
            False,
            f"{label} lacks {requirement.token!r}; has {', '.join(tokens) or '(nothing)'}",
        )
    if requirement.shape:
        # Several nodes may fill the token (a container's files and SFTP's): one offering the shape is enough.
        shortfalls = []
        for name in target_plan.names(scope):
            node = target_plan.node(f"{scope}.{name}")
            if node.contract != requirement.token:
                continue
            gives = provider_gives.get(node.provider)
            have = {m.name for m in gives.members} if gives else set()
            missing = [m for m in requirement.shape if m not in have]
            if not missing:
                return GatingDecision(True)
            shortfalls.append(missing)
        missing = min(shortfalls, key=len, default=list(requirement.shape))
        return GatingDecision(
            False,
            f"{label} offers {requirement.token!r} without member(s): {', '.join(missing)}",
        )
    return GatingDecision(True)
