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
"""Run each definition's conformance checks against the capability factories of given compositions.

`run_conformance(targets, definitions, roots, overrides)` brings every composition up (it is the caller's choice
of target: a simulated one stands in for hardware), runs every check of the contract each role fulfils against
the role's object, and takes the target down again. A check that raises `Skip`, or whose required members the
role does not offer, is skipped with the reason; checks that disrupt the platform run last, and the goals are
reached again after them. `not_run(catalog, definitions, results)` lists the factories fulfilling a contract
with checks that no result covers: which ones could not be run, and why.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass

from .conformance import Skip, all_checks


@dataclass(frozen=True)
class Result:
    target: str
    role: str
    factory: str
    contract: str
    check: str
    status: str  # pass | fail | skip
    detail: str = ""


def run_conformance(targets, definitions, roots=(), overrides=()) -> list[Result]:
    from score.itf.core import Session
    from score.itf.core.engine.scopes import ROOT

    checks = all_checks(definitions)
    results: list[Result] = []
    for target in targets:
        label = getattr(target, "describe", lambda: str(target))()
        with tempfile.TemporaryDirectory(prefix="itf-conformance-") as run_dir:
            session = Session(roots, target=target, overrides=overrides, run_dir=run_dir)
            try:
                session.resolve()
                session.bring_up()
                cases = []
                for node in session._target_plan.nodes:
                    offered = {m.name for m in node.gives.members}
                    for item in checks.get(node.contract, ()):
                        cases.append((item.disruptive, node, item, offered))
                cases.sort(key=lambda c: c[0])  # stable: disruptive checks last
                for disruptive, node, item, offered in cases:
                    where = f"{node.scope}." if node.scope != ROOT else ""
                    role, scope = node.name, node.scope
                    base = dict(
                        target=label,
                        role=f"{where}{role}",
                        factory=node.provider,
                        contract=node.contract,
                        check=item.name,
                    )
                    missing = [m for m in item.shape if m not in offered]
                    if missing:
                        results.append(Result(**base, status="skip", detail=f"does not offer {', '.join(missing)}"))
                        continue
                    view = session.target if scope == ROOT else getattr(session.target, scope)
                    try:
                        item(view.get(role))
                        results.append(Result(**base, status="pass"))
                    except Skip as exc:
                        results.append(Result(**base, status="skip", detail=str(exc)))
                    except Exception as exc:  # noqa: BLE001 - an AssertionError, or whatever the factory raised
                        results.append(Result(**base, status="fail", detail=f"{type(exc).__name__}: {exc}"))
                    finally:
                        if disruptive:
                            session.reach()
            finally:
                session.close()
    return results


def not_run(catalog, definitions, results) -> list[str]:
    """`label (contract): reason` for each factory with checks to run that no target exercised."""
    checks = all_checks(definitions)
    covered = {r.factory for r in results}
    return [
        f"{f.label} ({f.contract}): no target given contains it"
        for f in sorted(catalog.factories.values(), key=lambda f: f.label)
        if f.contract in checks and f.label not in covered
    ]
