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
from score.itf.core import delivers


@delivers("itf.states.network.reachable", name="fake_shell.become_reachable", uses={"world": "world.handle"})
def become_reachable(world):
    world.reachable = True


@become_reachable.probe
def is_reachable(world):
    return world.reachable


@delivers(
    "itf.states.shell.open",
    name="fake_shell.open_session",
    requires=("itf.states.network.reachable",),
    uses={"shell": "itf.capabilities.exec.shell"},
)
def open_session(shell):
    shell.run("connect")
    shell.world.session_open = True


@open_session.probe
def is_session_open(shell):
    return shell.world.session_open


@delivers(
    "itf.states.image.present",
    name="fake_shell.reimage",
    requires=("itf.states.network.reachable",),
    invalidates=("itf.states.shell.open",),
    uses={"shell": "itf.capabilities.exec.shell"},
)
def reimage(shell):
    shell.run("reimage")
    shell.world.image_present = True
    shell.world.session_open = False


@reimage.probe
def has_image(shell):
    return shell.world.image_present
