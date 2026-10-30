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
"""`assume()`: a policy or a request treats a state as already true, without running its producer
(docs/octo-kit/21-acceptance.md A-3.13, A-5.15; docs/octo-kit/30-decisions.md D-30)."""

from __future__ import annotations

import pytest

from score.itf.core.engine.contexts import InitContext, SetupContext, WrongPhase
from score.itf.core.engine.publish import publish
from score.itf.core.engine.registry import register
from score.itf.core.session import Session


def test_a_3_13_assume_is_itf_init_only():
    registry = register(["shell_recipe"])
    catalog = publish(registry)

    setup_ctx = SetupContext("policy", catalog)
    with pytest.raises(WrongPhase):
        setup_ctx.scope("main").assume("itf.states.network.reachable")
    with pytest.raises(WrongPhase):
        setup_ctx.assume("itf.states.network.reachable")

    init_ctx = InitContext("policy", catalog, None)
    init_ctx.scope("main").assume("itf.states.network.reachable", owner="lab", reason="managed externally")
    claim = next(iter(init_ctx._claims))
    assert (claim.scope, claim.token, claim.owner, claim.reason) == (
        "main",
        "itf.states.network.reachable",
        "lab",
        "managed externally",
    )


def test_a_3_13_policy_level_assume_suppresses_the_producer_action(tmp_path):
    session = Session(["assume_recipe"], run_dir=tmp_path)
    session.resolve()
    assert "main:itf.states.network.reachable" not in {s.key for s in session._action_plan.steps}
    assert "main:itf.states.network.reachable" in session._action_plan.assumed

    session.bring_up()
    assert "main:itf.states.network.reachable" not in session._run_report.executed
    assert session.target.main.world.session_open is True
    session.close()


def test_a_3_13_policy_level_assume_is_recorded_with_owner_and_reason(tmp_path):
    session = Session(["assume_recipe"], run_dir=tmp_path)
    session.resolve()
    entries = {e["state"]: e for e in session._assumed}
    assert entries["main:itf.states.network.reachable"]["owner"] == "lab_platform"
    assert "lab fixture" in entries["main:itf.states.network.reachable"]["reason"]
    assert entries["main:itf.states.network.reachable"]["origin"] == "conftest"
    session.close()


def test_a_5_15_reach_assume_bypasses_a_dependency_action_for_one_call(tmp_path):
    session = Session(["shell_recipe"], run_dir=tmp_path)
    session.resolve()
    session.bring_up()

    world = session.target.main.world
    world.reachable = False  # simulate drift: a probe would now find this false
    world.session_open = False

    report = session.reach(
        "main:itf.states.shell.open",
        assume=("main:itf.states.network.reachable",),
        owner="tester",
        reason="already probed by hand",
    )
    assert "main:itf.states.network.reachable" not in report.executed
    assert "main:itf.states.shell.open" in report.executed

    entries = {e["state"]: e for e in session._assumed}
    assert entries["main:itf.states.network.reachable"] == {
        "state": "main:itf.states.network.reachable",
        "owner": "tester",
        "reason": "already probed by hand",
        "origin": "request",
    }
    session.close()


def test_a_5_15_reach_without_assume_still_runs_the_dependency(tmp_path):
    session = Session(["shell_recipe"], run_dir=tmp_path)
    session.resolve()
    session.bring_up()

    world = session.target.main.world
    world.reachable = False
    world.session_open = False

    report = session.target.main.reach("itf.states.shell.open")
    assert "main:itf.states.network.reachable" in report.executed
    session.close()
