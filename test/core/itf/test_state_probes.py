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
"""An action delivering several states, each with its own probe (`probe_for`)."""

from __future__ import annotations

import pytest

from score.itf.core import ProbeFailed
from score.itf.core.session import NotReady, Session


@pytest.fixture
def session(tmp_path):
    session = Session(["link_recipe"], run_dir=tmp_path)
    session.resolve()
    yield session
    session.close()


def test_the_action_runs_once_for_both_states_and_keeps_both_probes(session):
    [step] = session._action_plan.steps
    assert step.delivers == ("main:peer.reachable", "main:session.open")
    assert dict(step.probes) == {
        "main:peer.reachable": "link_pack:peer_answers",
        "main:session.open": "link_pack:session_is_open",
    }
    session.bring_up()
    assert session.target.main.link.connects == 1
    assert session.target.main.states() == {"peer.reachable", "session.open"}


def test_each_state_is_observed_by_its_own_probe(session):
    session.bring_up()
    session.target.main.link.peer_answers = False
    assert session.target.main.probe() == {"session.open"}


def test_a_failing_extra_probe_names_its_state(session):
    session.target.main.link.break_reachability = True
    with pytest.raises(NotReady, match="probe for main:peer.reachable reports false") as failure:
        session.bring_up()
    assert isinstance(failure.value.__cause__, ProbeFailed)


def test_probe_for_must_name_an_also_delivered_state():
    from score.itf.core import delivers

    @delivers("a.state", name="probe_for_check.act", also_delivers=("b.state",))
    def act():
        pass

    with pytest.raises(TypeError, match="does not also_deliver"):
        act.probe_for("c.state")
