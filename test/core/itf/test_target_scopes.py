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
"""One target per session: a root scope addressed as `target.x`, device scopes as `target.dev.x`,
and no fallback from a device to the root."""

from __future__ import annotations

import json

import pytest

from score.itf.core import gating as itf_gating
from score.itf.core.engine.contexts import InitContext, SetupContext
from score.itf.core.engine.publish import publish
from score.itf.core.engine.registry import register
from score.itf.core.engine.scopes import ROOT, InvalidScopeName, display, display_json
from score.itf.core.session import ResolutionFailed, Session, TargetNameClash


@pytest.fixture
def session(tmp_path):
    s = Session(["root_scope_recipe"], run_dir=tmp_path)
    s.resolve()
    s.bring_up()
    yield s
    s.close()


def test_root_nodes_are_target_attributes_and_devices_are_scopes(session):
    target = session.target
    assert target.scopes() == ("dev1", "dev2")
    assert (target.scope, target.dev1.scope) == (None, "dev1")
    assert target.has("itf.capabilities.exec.shell")
    assert target.shell is not target.dev1.shell
    assert target.dev1.world is target.world  # dev1 aliased ".world": one object


def test_a_device_never_falls_back_to_the_root(session):
    with pytest.raises(AttributeError, match=r"target\.dev2 has no 'shell'"):
        session.target.dev2.shell
    with pytest.raises(AttributeError, match="nodes: .*shell.*scopes: dev1, dev2"):
        session.target.nope
    with pytest.raises(KeyError, match="device scope, not a node: use target.dev1"):
        session.target.get("dev1")


def test_planning_never_borrows_a_root_node_for_a_device(tmp_path):
    with pytest.raises(ResolutionFailed) as exc_info:
        Session(["no_fallback_recipe"], run_dir=tmp_path).resolve()
    assert {(d.code, d.subject) for d in exc_info.value.diagnostics} == {
        ("USES_UNSATISFIED", "dev3:itf.states.shell.open#shell"),
    }


def test_a_missing_use_names_the_contract_the_reason_and_where_it_exists(tmp_path):
    with pytest.raises(ResolutionFailed) as exc_info:
        Session(["no_fallback_recipe"], run_dir=tmp_path).resolve()
    text = display(exc_info.value.rendered)
    assert (
        "scope 'dev3' has no 'itf.capabilities.exec.shell' node, and reaching dev3:itf.states.shell.open needs one"
        in text
    )
    assert "Needed by: fake_shell.steps:open_session, slot 'shell'" in text
    assert "Why: dev3:itf.states.shell.open is a goal" in text
    assert "Exists in: .shell" in text
    assert "ctx.scope('dev3').alias('shell', '.shell')" in text
    html = (tmp_path / "target.html").read_text()
    assert "Gate 2 · itf_init failed" in html and "1 error(s)" in html
    assert 'class="item state blocked" data-id="s|dev3:itf.states.shell.open"' in html
    assert 'class="item node missing" data-id="n|dev3.shell!missing"' in html
    assert "WANTED · NOT PLANNED" in html and "missing:" in html
    assert "itf.capabilities.exec.shell" in html


def test_the_suggested_alias_resolves(tmp_path):
    Session(["no_fallback_fixed_recipe"], run_dir=tmp_path).resolve()


def test_a_root_node_named_like_a_device_scope_is_rejected(tmp_path):
    with pytest.raises(TargetNameClash, match="target.dev1 is both a root node and a device scope"):
        Session(["name_clash_recipe"], run_dir=tmp_path).resolve()


@pytest.mark.parametrize("name", ["dev-1", "_hidden", "target", "", "class", "plan", "scopes"])
def test_scope_names_must_be_attribute_names(name):
    ctx = SetupContext("policy", publish(register(["root_scope_recipe"])))
    with pytest.raises(InvalidScopeName):
        ctx.scope(name)


def test_references_must_be_strings():
    ctx = SetupContext("policy", publish(register(["root_scope_recipe"])))
    with pytest.raises(TypeError, match="reference must be a string"):
        ctx.alias("world", 42)


def test_display_rewrites_root_refs_only():
    assert display(f"{ROOT}.x {ROOT}:t {ROOT} dev{ROOT}.x {ROOT}x") == f".x :t target dev{ROOT}.x {ROOT}x"
    assert display_json({"config": {"path": f"/tmp/{ROOT}/f"}, "ref": f"{ROOT}.x"}) == {
        "config": {"path": f"/tmp/{ROOT}/f"},
        "ref": ".x",
    }


def test_top_level_init_verbs_address_the_root_scope_only():
    ctx = InitContext("policy", publish(register(["root_scope_recipe"])), None)
    ctx.goal("itf.states.shell.open")
    ctx.relate("itf.states.shell.open", requires=(":itf.states.network.reachable", "dev1:itf.states.network.reachable"))
    ctx.assume("itf.states.network.reachable")
    goal, relation, assumption = ctx._claims
    assert (goal.scope, relation.scope, assumption.scope) == (ROOT, ROOT, ROOT)
    assert relation.adds_requires == {f"{ROOT}:itf.states.network.reachable", "dev1:itf.states.network.reachable"}


def test_requires_without_scope_gates_on_the_root(session):
    decisions = session.select(
        {
            "root": (itf_gating.Requirement("itf.capabilities.exec.shell"),),
            "root_missing": (itf_gating.Requirement("nonexistent.token"),),
            "dev1": (itf_gating.Requirement("itf.capabilities.exec.shell", scope="dev1"),),
            "dev2": (itf_gating.Requirement("itf.capabilities.exec.shell", scope="dev2"),),
            "nope": (itf_gating.Requirement("itf.capabilities.exec.shell", scope="nope"),),
        }
    )
    assert decisions["root"].selected and decisions["dev1"].selected
    assert (
        not decisions["dev2"].selected and "target.dev2 lacks 'itf.capabilities.exec.shell'" in decisions["dev2"].reason
    )
    assert decisions["root_missing"].reason.startswith("target lacks 'nonexistent.token'")
    assert decisions["nope"].reason == "target has no scope 'nope'"
    gating = json.loads((session.run_dir / "gating.json").read_text())
    assert {g["test"] for g in gating} == {"root", "root_missing", "dev1", "dev2", "nope"}


def test_reach_takes_root_and_device_state_refs(session):
    session.target.world.session_open = False
    report = session.reach("itf.states.shell.open")
    assert f"{ROOT}:itf.states.shell.open" in report.executed
    report = session.target.dev1.reach("itf.states.shell.open")
    assert report.executed == ()  # shares the root's world: everything already holds
    assert "itf.states.shell.open" in session.target.dev1.states()
    assert session.reach("itf.states.shell.open").executed == ()  # a repeated reach is a no-op
    with pytest.raises(KeyError, match="target has no scope 'typo'"):
        session.reach("typo:itf.states.shell.open")


def test_plan_json_is_shaped_like_the_target(session):
    session.close()
    plan = json.loads((session.run_dir / "plan.json").read_text())
    target = plan["target"]
    assert {n["name"] for n in target["nodes"]} == {"world", "shell"}
    assert set(target["scopes"]) == {"dev1", "dev2"}
    assert target["aliases"] == {"dev1.world": ".world"}
    for name in ("plan.json", "run.json", "unwind.json", "gating.json", "diagnostics.txt"):
        assert ROOT not in (session.run_dir / name).read_text(), name
