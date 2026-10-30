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
from score.itf.core import hookimpl


pytest_plugins = ["fake_shell.plugin"]


@hookimpl
def itf_setup(ctx):
    ctx.add("world", using="fake_shell.world")
    ctx.add("shell", "itf.capabilities.exec.shell", using="fake_shell.session", bind={"world": "world"})
    ctx.scope("dev3").add("other", "world.handle", using="fake_shell.world")


@hookimpl
def itf_init(ctx):
    # dev3 has no itf.capabilities.exec.shell; the root's must not be borrowed implicitly.
    ctx.scope("dev3").goal("itf.states.shell.open")
