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
from collections.abc import Iterator

from score.itf.core import provides


class World:
    """The fake bench: everything a probe or an action can observe or change."""

    def __init__(self):
        self.reachable = False
        self.session_open = False
        self.image_present = False
        self.log: list[str] = []


@provides("world.handle", name="fake_shell.world")
def make_world(config):
    return World()


class Session:
    def __init__(self, world: World):
        self.world = world

    def run(self, cmd: str) -> str:
        self.world.log.append(cmd)
        return f"ran:{cmd}"

    def close(self) -> None:
        self.world.log.append("closed")


@provides("itf.capabilities.exec.shell", name="fake_shell.session", needs={"world": "world.handle"})
def make_session(world, config) -> Iterator[Session]:
    shell = Session(world)
    yield shell
    shell.close()
