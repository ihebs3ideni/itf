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
"""`renew`: rebuild nodes from scratch mid-session and reach every goal again through the planner."""

from __future__ import annotations

import pytest

from score.itf.core.session import Session


@pytest.fixture
def session(tmp_path):
    session = Session(["shell_recipe"], run_dir=tmp_path)
    session.resolve()
    session.bring_up()
    yield session
    session.close()


def test_renew_rebuilds_the_node_and_every_node_bound_to_it(session):
    old_world, old_shell = session.target.main.world, session.target.main.shell

    session.target.main.renew("world")

    world, shell = session.target.main.world, session.target.main.shell
    assert world is not old_world and shell is not old_shell
    assert old_world.log[-1] == "closed", "the old shell's teardown ran"
    assert world.session_open and world.image_present, "the goals were reached again on the new objects"


def test_renew_does_not_trust_a_probe_that_reads_state_outside_the_dismantled_node(session):
    world = session.target.main.world
    world.log.clear()

    session.target.main.renew("shell")

    # The world survives and still says the session is open, but that evidence was produced
    # through the dismantled shell: its producers run again, in planner order.
    assert session.target.main.world is world
    assert world.log == ["closed", "reimage", "connect"]


def test_renew_leaves_unrelated_nodes_alone(session):
    world = session.target.main.world
    world.log.clear()
    shell = session.target.main.shell

    session.renew("main.shell")

    assert session.target.main.world is world
    assert session.target.main.shell is not shell


def test_renew_of_an_unknown_node_raises_before_dismantling_anything(session):
    shell = session.target.main.shell
    with pytest.raises(KeyError, match="no node"):
        session.target.main.renew("nope")
    assert session.target.main.shell is shell


def test_renew_is_a_reserved_handle_member(session):
    assert "renew" in dir(type(session.target.main))
