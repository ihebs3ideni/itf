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
"""render_target_html: a pure function, resolved plan -> one self-contained dark HTML document."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from score.itf.core.artifacts import write_artifacts
from score.itf.core.engine.report import _layers, render_target_html
from score.itf.core.octo import ActionPlan, PlannedNode, TargetPlan
from score.itf.core.session import Session


def _resolved_plans(tmp_path):
    session = Session(["shell_recipe"], run_dir=tmp_path).resolve()
    return session._target_plan, session._action_plan


def test_renders_without_raising_and_names_every_scope_and_node(tmp_path):
    target_plan, action_plan = _resolved_plans(tmp_path)

    out = render_target_html(target_plan, action_plan, title="demo")

    assert out.startswith("<!DOCTYPE html") or out.startswith("<html")
    for scope in target_plan.scopes():
        assert scope in out
    for node in target_plan.nodes:
        assert node.name in out


def test_tolerates_a_target_plan_with_no_action_plan_yet():
    """Gate 1 can resolve while Gate 2 fails; Session sets `_target_plan` before Gate 2 runs, and
    `write_artifacts` runs in `resolve()`'s `finally` block either way (docs/octo-kit/
    12-spec-itf-core.md section 9: artifacts are written "including after a failed gate")."""
    node = PlannedNode(
        scope="main",
        name="n",
        contract="c",
        provider="p",
        impl="i",
        derived=False,
        config=(),
        bindings=(),
        why_provider="sole-implementation",
        why_bindings=(),
    )
    target_plan = TargetPlan(nodes=(node,), construction_order=(node.ref,), aliases=(), seams=())

    out = render_target_html(target_plan, None, title="demo")

    assert out.startswith("<!DOCTYPE html")
    assert "n" in out


def test_write_artifacts_does_not_crash_when_gate_1_resolves_and_gate_2_fails(tmp_path):
    from score.itf.core.session import ResolutionFailed

    session = Session(["gate2_fail_recipe"], run_dir=tmp_path)
    with pytest.raises(ResolutionFailed) as excinfo:
        session.resolve()
    assert excinfo.value.gate == 2
    assert session._target_plan is not None
    assert session._action_plan is None
    assert (tmp_path / "target.html").exists()


def test_escapes_untrusted_names_instead_of_injecting_markup():
    payload = "<script>alert(1)</script>"
    node = PlannedNode(
        scope="main",
        name=payload,
        contract=payload,
        provider="prov",
        impl="impl",
        derived=False,
        config=(),
        bindings=(),
        why_provider="sole-implementation",
        why_bindings=(),
    )
    target_plan = TargetPlan(nodes=(node,), construction_order=(node.ref,), aliases=(), seams=())
    action_plan = ActionPlan(
        goals=(),
        observed_at_plan_time=(),
        steps=(),
        edges=(),
        unprobed=(),
        assumed=(),
    )

    out = render_target_html(target_plan, action_plan, title=payload)

    assert payload not in out
    assert "&lt;script&gt;" in out


def test_write_artifacts_creates_target_html_only_when_a_target_plan_exists(tmp_path):
    session = Session(["shell_recipe"], run_dir=tmp_path / "resolved").resolve()
    write_artifacts(tmp_path / "resolved", session)
    assert (tmp_path / "resolved" / "target.html").exists()

    unresolved = Session(["shell_recipe"], run_dir=tmp_path / "unresolved")
    write_artifacts(tmp_path / "unresolved", unresolved)
    assert not (tmp_path / "unresolved" / "target.html").exists()


def _node(name, contract="c", bindings=(), derived=False, scope="main"):
    return PlannedNode(
        scope=scope,
        name=name,
        contract=contract,
        provider="p",
        impl="m:f",
        derived=derived,
        config=(),
        bindings=bindings,
        why_provider="sole-implementation",
        why_bindings=tuple((slot, "derived" if derived else "explicit") for slot, _ in bindings),
    )


def _embedded_items(out: str) -> dict:
    start = out.index('id="itf-data">') + len('id="itf-data">')
    return json.loads(out[start : out.index("</script>", start)])["items"]


def test_layers_nest_capabilities_to_any_depth():
    children = {"a": [("x", "b")], "b": [("y", "c")], "c": [("z", "d")], "e": [("x", "c")]}
    layer, roots = _layers(["a", "b", "c", "d", "e"], children)

    assert sorted(roots) == ["a", "e"]
    assert layer == {"a": 1, "e": 1, "b": 2, "c": 3, "d": 4}


def test_layers_terminate_on_a_cycle():
    layer, _ = _layers(["a", "b"], {"a": [("x", "b")], "b": [("y", "a")]})
    assert set(layer) == {"a", "b"}


def test_embedded_data_describes_slots_and_cannot_close_the_script_element():
    breakout = "</script><script>alert(1)</script>"
    leaf = _node("leaf", contract="net.thing")
    mid = _node("mid.leaf", bindings=(("leaf", "main.leaf"),), derived=True)
    top = _node(breakout, bindings=(("dep", "main.mid.leaf"),))
    target_plan = TargetPlan(nodes=(leaf, mid, top), construction_order=(), aliases=(), seams=())

    out = render_target_html(target_plan, None)

    assert breakout not in out
    items = _embedded_items(out)
    assert items[f"n|main.{breakout}"]["title"] == breakout
    assert items[f"n|main.{breakout}"]["slots"][0]["label"] == "main.mid.leaf"
    assert items["n|main.mid.leaf"]["derived"] is True
    assert items["n|main.mid.leaf"]["consumed_by"][0]["slot"] == "dep"
    assert [t["label"] for t in items["t|main"]["top_level"]] == [breakout]


def test_state_status_reflects_the_run_report(tmp_path):
    target_plan, action_plan = _resolved_plans(tmp_path)
    first, *rest = action_plan.steps
    report = SimpleNamespace(executed=(first.key,), skipped=tuple(s.key for s in rest))

    items = _embedded_items(render_target_html(target_plan, action_plan, run_report=report))

    assert items[f"s|{first.key}"]["status"] == "ran"
    for s in rest:
        assert items[f"s|{s.key}"]["status"] == "held"
