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
"""run.json reports probe count/time per phase, and drift: a re-probe disagreeing with execution."""

from __future__ import annotations

import json

from score.itf.core.engine.realize import default_resolver
from score.itf.core.session import Session


def _run(tmp_path, resolver=None):
    session = Session(["shell_recipe"], run_dir=tmp_path, resolver=resolver)
    session.resolve()
    session.bring_up()
    session.reach("main:itf.states.shell.open")
    session.close()
    return session, json.loads((tmp_path / "run.json").read_text())


def test_probes_are_counted_per_phase(tmp_path):
    session, run = _run(tmp_path)
    probes = run["probes"]
    assert set(probes) == {
        "before_bring_up",
        "bring_up",
        "after_bring_up",
        "reach_before",
        "reach_verify",
        "after_reach",
        "unwind",
    }
    n = len([s for s in session._full_plan.steps if s.probe])
    assert probes["before_bring_up"]["count"] == n  # nothing holds: everything probed
    assert probes["bring_up"]["count"] == n  # each executed step verified once
    assert probes["after_bring_up"]["count"] == n
    assert probes["reach_verify"]["count"] == 0  # all held: nothing executed
    assert all(p["ms"] >= 0 and p["runs"] == 1 for p in probes.values())
    assert run["drift"] == []

    session.target.main.probe("itf.states.shell.open")
    assert session._probe_stats["target_probe"]["count"] == 1


def test_an_undeclared_side_effect_is_reported_as_drift(tmp_path, caplog):
    def resolver(ref):
        fn = default_resolver(ref)
        if getattr(fn, "__name__", "") != "open_session":
            return fn

        def open_and_break(shell):  # also drops itf.states.image.present, undeclared
            fn(shell)
            shell.world.image_present = False

        return open_and_break

    _, run = _run(tmp_path, resolver)
    assert run["drift"][0] == {"phase": "after_bring_up", "dropped": ["main:itf.states.image.present"], "appeared": []}
    assert any("drift after_bring_up" in r.getMessage() for r in caplog.records)
