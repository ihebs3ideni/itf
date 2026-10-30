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
"""The sim variants compose like the real packs: offline, two devices, a shared capture."""

import pytest

from score.itf.core.session import Session


@pytest.fixture
def session(tmp_path):
    session = Session(["sim_recipe"], run_dir=tmp_path)
    session.resolve()
    session.bring_up()
    yield session
    session.close()


def test_every_goal_holds_after_bring_up(session):
    assert session.target.states() == {"itf.states.capture.running"}
    assert session.target.gw.states() >= {"itf.states.shell.open", "itf.states.logs.active", "itf.states.platform.up"}
    assert "itf.states.shell.open" in session.target.adas.states()


def test_devices_are_separate_and_share_the_aliased_capture(session):
    gw, adas = session.target.gw, session.target.adas
    assert gw.platform is not adas.platform
    assert gw.capture is adas.capture is session.target.capture
    gw.shell.run("hello")
    assert gw.platform.log == ["hello"] and adas.platform.log == []


def test_logs_see_what_the_platform_logged(session):
    session.target.gw.command.exec("event")
    assert "event" in session.target.gw.logs.lines()


def test_a_platform_restart_kills_the_session_and_reach_reopens_it(session):
    gw = session.target.gw
    gw.platform.restart()
    with pytest.raises(RuntimeError, match="dead"):
        gw.shell.run("x")
    gw.reach("itf.states.shell.open")
    assert gw.shell.run("again") == "ok:again"


def test_renew_rebuilds_a_device_platform_and_everything_bound_to_it(session):
    old_platform, old_shell = session.target.gw.platform, session.target.gw.shell
    session.target.gw.renew("platform")
    assert session.target.gw.platform is not old_platform and session.target.gw.shell is not old_shell
    assert "itf.states.shell.open" in session.target.gw.states()
    assert session.target.adas.platform is not None
