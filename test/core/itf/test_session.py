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
"""P5: session, targets, gating, artifacts (docs/octo-kit/21-acceptance.md A-5.*)."""

from __future__ import annotations

import json

import pytest

from score.itf.core import gating as itf_gating
from score.itf.core.engine.bringup import Observation, execute, observe
from score.itf.core.engine.collect import collect_setup
from score.itf.core.engine.publish import publish
from score.itf.core.engine.realize import Realization
from score.itf.core.engine.registry import register
from score.itf.core import octo
from score.itf.core.session import PRECEDENCE, NotReady, ResolutionFailed, Session, describe


def test_a_5_1_gate_failure_is_one_rendered_error(tmp_path):
    session = Session(["broken_recipe"], run_dir=tmp_path)
    with pytest.raises(ResolutionFailed) as exc_info:
        session.resolve()
    exc = exc_info.value
    assert exc.gate == 1
    assert exc.hook == "itf_setup"
    assert "Gate 1 · itf_setup" in exc.rendered


def test_a_5_2_deselection_precedes_construction(tmp_path):
    session = Session(["shell_recipe"], run_dir=tmp_path)
    session.resolve()
    before = session._realization.construction_order
    reqs = (itf_gating.Requirement("nonexistent.token", scope="main"),)
    decisions = session.select({"test_x": reqs})
    assert decisions["test_x"].selected is False
    assert session._realization.construction_order == before  # select() itself builds nothing


def test_a_5_3_deselection_reason_names_token_and_scope_contents(tmp_path):
    session = Session(["shell_recipe"], run_dir=tmp_path)
    session.resolve()
    reqs = (itf_gating.Requirement("nonexistent.token", scope="main"),)
    decisions = session.select({"test_x": reqs})
    reason = decisions["test_x"].reason
    assert "nonexistent.token" in reason
    assert "itf.capabilities.exec.shell" in reason


def test_a_5_4_strict_gating_is_a_session_option(tmp_path):
    session = Session(["shell_recipe"], run_dir=tmp_path, gating="fail")
    assert session.gating == "fail"


def test_a_5_5_one_resolution_shared_alias_is_one_object(tmp_path):
    session = Session(["two_scope_recipe"], run_dir=tmp_path)
    session.resolve()
    session.bring_up()
    assert session.target.a.world is session.target.b.world
    session.close()


def test_a_5_6_reach_probes_replans_and_executes_the_delta(tmp_path):
    session = Session(["shell_recipe"], run_dir=tmp_path)
    session.resolve()
    session.bring_up()
    world = session.target.main.world
    assert world.image_present and world.session_open
    report = session.reach("main:itf.states.shell.open")
    assert report.executed == () and report.skipped == ()  # already true; nothing to do
    session.close()


def test_a_5_7_six_artifacts_always_written(tmp_path):
    for policies in (["shell_recipe"], ["broken_recipe"]):
        run_dir = tmp_path / policies[0]
        session = Session(list(policies), run_dir=run_dir)
        try:
            session.resolve()
            session.bring_up()
            session.close()
        except ResolutionFailed:
            pass
        for name in ("claims.json", "plan.json", "diagnostics.txt", "gating.json", "run.json", "unwind.json"):
            assert (run_dir / name).exists(), f"{policies}: missing {name}"


def test_a_5_8_observed_states_come_from_probing_not_dry_run(tmp_path):
    registry = register(["shell_recipe"])
    catalog = publish(registry)
    setup_claims = collect_setup(registry, catalog) | frozenset(catalog.providers)
    target_res = octo.resolve_target(setup_claims, precedence=PRECEDENCE)
    from score.itf.core.engine.collect import collect_init

    init_claims = collect_init(registry, catalog, target_res.plan) | frozenset(catalog.actions)
    full = octo.resolve_actions(init_claims, target_res.plan, precedence=PRECEDENCE, observed_states=frozenset())
    realization = Realization(target_res.plan)
    world = realization.get("main.world")
    world.reachable = True  # the bench is already partly up
    observation = observe(full.plan, realization)
    delta = octo.resolve_actions(init_claims, target_res.plan, precedence=PRECEDENCE, observed_states=observation.holds)
    delivered = {d for s in delta.plan.steps for d in s.delivers}
    assert "main:itf.states.network.reachable" not in delivered


def test_a_5_9_ready_requires_probed_goals_and_essential_checks(tmp_path):
    session = Session(["shell_recipe"], run_dir=tmp_path)
    session.resolve()
    session.bring_up()
    assert session._ready is True
    session.close()

    session2 = Session(["unprobed_recipe"], run_dir=tmp_path / "unprobed")
    session2.resolve()
    assert "main:mystery_state" in session2._action_plan.unprobed


def test_a_5_10_an_unreferenced_module_contributes_nothing(tmp_path):
    session = Session(["fake_kv_recipe"], run_dir=tmp_path)
    session.resolve()
    assert "unreferenced_pack" not in session._registry.origins
    assert "ghost" not in session._target_plan.scopes()


def test_a_5_11_plan_only_builds_nothing(tmp_path):
    result = describe(["shell_recipe"], run_dir=tmp_path)
    assert result.target_plan is not None
    assert result.action_plan.observed_at_plan_time == ()


def test_a_5_12_fresh_reuse_runs_every_action_even_if_it_holds(tmp_path):
    session = Session(["shell_recipe"], run_dir=tmp_path, reuse="fresh")
    session.resolve()
    session.bring_up()
    executed = set(session._run_report.executed)
    assert {
        "main:itf.states.network.reachable",
        "main:itf.states.image.present",
        "main:itf.states.shell.open",
    } <= executed
    session.close()


def test_a_5_13_keep_skips_unwind(tmp_path):
    session = Session(["shell_recipe"], run_dir=tmp_path, on_exit="keep")
    session.resolve()
    session.bring_up()
    session.close()
    assert session._unwind_report.kept is True
    assert session._unwind_report.dismantled == ()


def test_a_5_14_a_declared_unresolvable_node_fails_under_every_option(tmp_path):
    for kwargs in (
        {},
        {"plan_only": True},
        {"reuse": "fresh"},
        {"strict_shapes": True},
    ):
        session = Session(["broken_recipe"], run_dir=tmp_path / repr(kwargs), **kwargs)
        with pytest.raises(ResolutionFailed):
            session.resolve()
