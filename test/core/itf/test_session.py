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
"""One run: resolve, bring up, use, close."""

import kv_hooks
import kv_parts
import pytest
import recording_parts

from score.itf.core import NotReady, ResolutionFailed, Session, compose

TARGET = """
capabilities:
  store: local.store
  view: local.view
goals:
  - state: kv.ready
  - state: kv.seeded
    by: local.seed_a
"""


@pytest.fixture(autouse=True)
def events():
    kv_parts.EVENTS.clear()
    return kv_parts.EVENTS


def run(tmp_path, target=TARGET, roots=(kv_parts,), **options):
    return Session(list(roots), target=target, run_dir=tmp_path / "run", **options)


def test_bring_up_runs_the_actions_in_dependency_order_and_close_unwinds(tmp_path, events):
    session = run(tmp_path, reuse="fresh").resolve()
    assert events == []  # resolving constructs nothing when nothing is probed
    session.bring_up()
    assert events == ["store built", "seed_a", "ready"]
    assert session.target.view.read("seeded") == "a"
    assert session.target.store.name == "mem"
    session.close()
    assert events[-1] == "store closed"


def test_the_target_is_a_handle_of_roles(tmp_path):
    session = run(tmp_path).resolve()
    assert session.target.names() == ("store", "view")
    assert session.target.has("view") and not session.target.has("shell")
    assert "kv.view" in session.target.tokens()
    with pytest.raises(AttributeError, match="no role or scope 'shell'"):
        session.target.shell


def test_hooks_of_the_project_run_after_bring_up_and_before_unwind(tmp_path, events):
    session = run(tmp_path, roots=(kv_parts, kv_hooks)).resolve()
    session.bring_up()
    assert session._check_results[0].ok
    store = session.target.store
    session.close()
    assert store.get("teardown") == "store, view"  # the teardown hook ran while the target still lived
    assert events[-1] == "store closed"


def test_probes_make_a_second_run_reuse_what_holds(tmp_path, events):
    session = run(tmp_path).resolve()
    session.bring_up()
    done = len(events)
    session.reach("kv.ready")  # everything holds: nothing runs again
    assert events[done:] == []
    session.close()


def test_a_failing_action_is_not_ready_and_the_report_names_the_action(tmp_path):
    session = run(tmp_path, "capabilities:\n  store: local.store\ngoals:\n  - kv.broken\n").resolve()
    with pytest.raises(NotReady) as error:
        session.bring_up()
    assert "the store refused" in str(error.value.failure.render())
    session.close()


def test_a_plan_only_session_does_not_bring_up(tmp_path, events):
    session = run(tmp_path, plan_only=True).resolve()
    with pytest.raises(RuntimeError, match="plan_only"):
        session.bring_up()
    assert events == []


def test_resolution_failure_carries_the_gate_and_the_rendered_diagnostics(tmp_path):
    with pytest.raises(ResolutionFailed) as error:
        run(tmp_path, "capabilities:\n  view: local.view\n").resolve()
    assert error.value.gate == 1 and error.value.phase == "capabilities"
    assert "Gate 1" in error.value.rendered


def test_plans_print_roles_factory_labels_and_contract_names(tmp_path):
    session = run(tmp_path, plan_only=True).resolve()
    plan = session.target.plan()
    labels = [n["label"] for n in plan["target"]["nodes"]]
    assert labels == ["store (local.store)", "view (local.view)"]
    assert plan["target"]["nodes"][0]["contract"] == "kv.store"
    assert [s["delivers"] for s in plan["action"]["steps"]] == [["kv.seeded"], ["kv.ready"]]
    assert [s["by"] for s in plan["action"]["steps"]] == ["local.seed_a", "local.ready"]


def test_compose_is_a_context_manager(tmp_path, events):
    with compose([kv_parts], target=TARGET, run_dir=tmp_path / "run") as session:
        assert session.target.store.get("seeded") == "a"
    assert events[-1] == "store closed"


def test_score_itf_session_is_the_core_session_and_definitions_are_handed_in_when_wanted(tmp_path):
    import score.itf as itf

    assert itf.Session is Session
    without = itf.Session([kv_parts], target=TARGET, plan_only=True, run_dir=tmp_path / "run").resolve()
    assert without.definitions == {} and without.warnings == ()
    from score.itf.core.adapters.definitions import definitions

    handed = itf.Session(
        [kv_parts], target=TARGET, plan_only=True, run_dir=tmp_path / "run2", definitions=definitions()
    ).resolve()
    assert handed.definitions == definitions()


def test_the_session_is_read_through_public_accessors(tmp_path):
    session = run(tmp_path).resolve()
    assert session.target_plan.nodes and session.catalog.factories
    assert session.action_plan.steps and session.observed == frozenset()
    session.bring_up()
    assert session.observed
    session.close()


@pytest.mark.parametrize("option, value", [("gating", "strict"), ("reuse", "always"), ("on_exit", "stay")])
def test_the_modes_are_validated(option, value):
    with pytest.raises(ValueError, match=f"{option} is one of"):
        Session(**{option: value})


def test_a_deprecated_contract_in_the_definitions_warns(tmp_path):
    from score.itf.core.gating import Definition

    definitions = {"kv.store": Definition("kv.store", 1, "deprecated", "kv.map")}
    session = run(tmp_path, plan_only=True, definitions=definitions).resolve()
    assert any("kv.store" in w and "deprecated" in w and "kv.map" in w for w in session.warnings)


REC = "capabilities:\n  thing: local.thing\ngoals:\n  - rec.ready\n"


@pytest.fixture
def calls():
    recording_parts.CALLS.clear()
    recording_parts.HOLDS[:] = [False]
    return recording_parts.CALLS


def test_resolve_is_a_pure_plan_it_probes_and_builds_nothing(tmp_path, calls):
    recording_parts.HOLDS[:] = [True]
    session = run(tmp_path, target=REC, roots=(recording_parts,)).resolve()
    assert calls == []
    assert [s.impl.rpartition(":")[2] for s in session.action_plan.steps] == ["make_ready"]
    session.select({"some_test": ()})
    assert calls == []


def test_bring_up_probes_first_and_runs_only_what_does_not_hold(tmp_path, calls):
    recording_parts.HOLDS[:] = [True]
    session = run(tmp_path, target=REC, roots=(recording_parts,)).resolve()
    session.bring_up()
    assert "run" not in calls and "probe" in calls
    assert session.action_plan.steps == ()  # the delta: what holds is not planned again
    session.close()


def test_bring_up_runs_an_action_whose_probe_says_no(tmp_path, calls):
    session = run(tmp_path, target=REC, roots=(recording_parts,)).resolve()
    session.bring_up()
    assert calls.index("probe") < calls.index("run")
    session.close()


def test_renew_delivers_again_what_an_earlier_reach_delivered(tmp_path, events):
    session = run(tmp_path, target="capabilities:\n  store: local.store\n").resolve()
    session.bring_up()
    session.reach("kv.audited")
    assert events.count("audit") == 1
    session.renew("store")
    assert events.count("audit") == 2  # the goal reached earlier is a goal of the delta too
    assert events.count("store built") == 2
    session.close()


def test_discard_dismantles_a_role_and_the_next_reach_builds_it_afresh(tmp_path, events):
    session = run(tmp_path, target="capabilities:\n  store: local.store\n").resolve()
    session.bring_up()
    session.reach("kv.audited")
    old = session.target.store
    session.discard("store")
    assert events.count("store built") == 1 and events.count("audit") == 1  # nothing rebuilt or reached yet
    fresh = session.target.store  # a new object the caller may adjust before reaching
    assert fresh is not old
    session.reach("kv.audited")
    assert events.count("audit") == 2  # the old evidence was forgotten, so the action runs again
    session.close()
