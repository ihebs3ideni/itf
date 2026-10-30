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
"""P4: realization, bring-up, checks, teardown, unwind (docs/octo-kit/21-acceptance.md A-4.*)."""

from __future__ import annotations

import pytest

from score.itf.core import octo
from score.itf.core.engine.bringup import ExecutionError, Observation, ProbeFailed, execute, observe
from score.itf.core.engine.collect import collect_init, collect_setup
from score.itf.core.engine.publish import publish
from score.itf.core.engine.realize import RealizationError, Realization
from score.itf.core.engine.registry import register
from score.itf.core.session import PRECEDENCE, NotReady, Session


def _resolve(policies):
    registry = register(policies)
    catalog = publish(registry)
    setup_claims = collect_setup(registry, catalog) | frozenset(catalog.providers)
    target_res = octo.resolve_target(setup_claims, precedence=PRECEDENCE)
    assert target_res.ok(), target_res.diagnostics
    init_claims = collect_init(registry, catalog, target_res.plan) | frozenset(catalog.actions)
    return registry, catalog, target_res.plan, init_claims


def test_a_4_1_lazy_construction_in_binding_order(tmp_path):
    _, _, target_plan, _ = _resolve(["shell_recipe"])
    realization = Realization(target_plan)
    assert realization.construction_order == ()
    shell = realization.get("main.shell")
    assert realization.construction_order == ("main.world", "main.shell")
    assert shell.world is realization.get("main.world")


def test_a_4_2_inspection_never_constructs(tmp_path):
    """Resolving may itself realize nodes a probe `uses` (allowed, per the spec's probing-before-
    Gate-2 note); what must never construct is `Target`'s own inspection surface."""
    session = Session(["shell_recipe"], run_dir=tmp_path)
    session.resolve()
    before = session._realization.construction_order
    target = session.target.main
    target.tokens()
    target.has("itf.capabilities.exec.shell")
    target.names()
    target.states()
    target.plan()
    repr(target)
    assert session._realization.construction_order == before


def test_a_4_3_alias_fetches_identical_object(tmp_path):
    session = Session(["two_scope_recipe"], run_dir=tmp_path)
    session.resolve()
    session.bring_up()
    assert session.target.a.world is session.target.b.world
    session.close()


def test_a_4_4_dry_run_constructs_nothing_and_catches_typo():
    _, _, target_plan, _ = _resolve(["shell_recipe"])
    calls = []

    def spy_resolver(impl):
        calls.append(impl)
        return lambda **kw: None

    realization = Realization(target_plan, resolver=spy_resolver)
    realization.resolve_all()
    assert realization.construction_order == ()
    assert calls  # every node impl was resolved

    def typo_resolver(impl):
        raise ModuleNotFoundError(f"no such module for {impl}")

    bad_realization = Realization(target_plan, resolver=typo_resolver)
    with pytest.raises(ModuleNotFoundError):
        bad_realization.resolve_all()


def test_a_4_5_unwind_dismantles_only_what_was_built_and_tolerates_absence(tmp_path):
    """'spare_shell' is never referenced by any step's `uses`, so it is never constructed and
    unwind must tolerate its absence rather than trying to dismantle it."""
    session = Session(["shell_recipe_unused_node"], run_dir=tmp_path)
    session.resolve()
    session.bring_up()
    session.close()
    assert "main.spare_shell" not in session._realization.construction_order
    assert "main.spare_shell" not in session._unwind_report.dismantled
    assert "main.shell" in session._unwind_report.dismantled
    assert session._unwind_report.errors == ()


def test_a_4_6_a_failing_action_is_called_exactly_once(tmp_path):
    import boom_pack

    boom_pack.CALLS.clear()
    session = Session(["boom_recipe"], run_dir=tmp_path)
    session.resolve()
    with pytest.raises(NotReady):
        session.bring_up()
    session.close()
    assert boom_pack.CALLS == [1]


def test_a_4_7_observe_never_assumes_an_unprobed_state(tmp_path):
    _, _, target_plan, init_claims = _resolve(["unprobed_recipe"])
    full = octo.resolve_actions(init_claims, target_plan, precedence=PRECEDENCE, observed_states=frozenset())
    realization = Realization(target_plan)
    observation = observe(full.plan, realization)
    assert "main:mystery_state" not in observation.holds
    assert "main:mystery_state" in full.plan.unprobed


def test_a_4_8_probed_step_skips_on_observation_unprobed_step_never_skips(tmp_path):
    _, _, target_plan, init_claims = _resolve(["shell_recipe"])
    full = octo.resolve_actions(init_claims, target_plan, precedence=PRECEDENCE, observed_states=frozenset())
    realization = Realization(target_plan)
    observation = Observation(frozenset({"main:itf.states.network.reachable"}), ())
    report = execute(full.plan, realization, observation)
    assert "main:itf.states.network.reachable" in report.skipped
    assert "main:itf.states.network.reachable" not in report.executed

    _, _, up, uc = _resolve(["unprobed_recipe"])
    ufull = octo.resolve_actions(uc, up, precedence=PRECEDENCE, observed_states=frozenset())
    urealization = Realization(up)
    uobservation = Observation(frozenset({"main:mystery_state"}), ())
    ureport = execute(ufull.plan, urealization, uobservation)
    assert "main:mystery_state" not in ureport.skipped
    assert "main:mystery_state" in ureport.executed


def test_a_4_9_a_lying_probe_raises_probe_failed(tmp_path):
    session = Session(["liar_recipe"], run_dir=tmp_path)
    session.resolve()
    with pytest.raises(NotReady) as exc_info:
        session.bring_up()
    assert "lie_state" in str(exc_info.value)
    session.close()


def test_a_4_10_every_verify_impl_runs_and_essential_failure_blocks_readiness(tmp_path):
    session = Session(["checks_fail_recipe"], run_dir=tmp_path)
    session.resolve()
    with pytest.raises(NotReady):
        session.bring_up()
    names = {c.name for c in session._check_results}
    assert names == {"main.always_false", "main.always_true"}
    oks = {c.name: c.ok for c in session._check_results}
    assert oks["main.always_false"] is False
    assert oks["main.always_true"] is True
    assert session._ready is False
    session.close()


def test_a_4_11_teardown_hooks_independent_one_raising_does_not_stop_the_next(tmp_path):
    session = Session(["two_teardowns_recipe"], run_dir=tmp_path)
    session.resolve()
    session.bring_up()
    session.close()
    results = dict((n, ok) for n, ok, _ in session._teardown_results)
    assert any(not ok for ok in results.values())
    assert any(ok for ok in results.values())


@pytest.mark.parametrize(
    "policies",
    [
        ["shell_recipe"],
        ["boom_recipe"],
        ["checks_fail_recipe"],
    ],
)
def test_a_4_12_teardown_and_unwind_run_after_every_outcome(tmp_path, policies):
    session = Session(list(policies), run_dir=tmp_path / policies[0])
    session.resolve()
    try:
        session.bring_up()
    except NotReady:
        pass
    session.close()
    run_dir = tmp_path / policies[0]
    for name in ("claims.json", "plan.json", "diagnostics.txt", "gating.json", "run.json", "unwind.json"):
        assert (run_dir / name).exists()
    assert session._unwind_report is not None
