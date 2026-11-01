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
"""itf_target: a valid composition becomes plan JSON at build time; an invalid one fails with ITF's diagnostics."""

import json
import os
import subprocess
from pathlib import Path


def _plan() -> dict:
    return json.loads(Path(os.environ["OK_PLAN"]).read_text(encoding="utf-8"))


def _run(tmp_path, target, *packs):
    out = tmp_path / "failing.plan.json"
    args = [os.environ["PLANNER"], "--target", os.environ[target], "--out", str(out)]
    for pack in packs:
        args += ["--pack", pack]
    return subprocess.run(args, capture_output=True, text=True), out


def test_plan_has_the_target_and_the_action_plan():
    plan = _plan()
    assert set(plan) == {"target", "action", "assumptions"}
    assert plan["target"] and plan["action"]


def test_plan_names_the_roles_and_their_factories():
    target = _plan()["target"]
    providers = {node["name"]: node["provider"] for node in target["nodes"]}
    assert providers == {"command": "sim.docker_exec", "platform": "sim.docker_platform"}


def test_plan_orders_the_steps_that_bring_the_goal_up():
    steps = _plan()["action"]["steps"]
    assert [step["delivers"] for step in steps] == [["platform.up"]]
    assert steps[0]["impl"] == "score.itf.packs.sim.docker.steps:start_platform"
    assert steps[0]["uses"] == {"platform": "platform"}


def test_plan_file_is_deterministic():
    text = Path(os.environ["OK_PLAN"]).read_text(encoding="utf-8")
    assert text == json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"


def test_a_composition_that_does_not_resolve_fails_with_rendered_diagnostics(tmp_path):
    run, out = _run(tmp_path, "NO_STORE", "sim")
    assert run.returncode == 1
    assert "plan failed at gate 1" in run.stderr
    assert "command (sim.docker_exec) needs a 'platform.instance' for its slot 'platform'" in run.stderr
    assert "Candidates: sim.docker_platform" in run.stderr
    assert not out.exists()


def test_a_factory_from_a_pack_that_is_not_in_packs_fails(tmp_path):
    run, out = _run(tmp_path, "OUTSIDE", "sim")
    assert run.returncode == 1
    assert "not in the itf_target's packs" in run.stderr and "local.platform" in run.stderr
    assert not out.exists()
    run, _ = _run(tmp_path, "OUTSIDE", "sim", "local")
    assert run.returncode == 0
