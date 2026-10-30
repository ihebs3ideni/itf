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


pytest_plugins = ["fake_shell.plugin", "teardown_recorder_pack", "teardown_raiser_pack"]


@hookimpl
def itf_setup(ctx):
    main = ctx.scope("main")
    main.add("world", using="fake_shell.world")
    main.add("shell", "itf.capabilities.exec.shell", using="fake_shell.session", bind={"world": "world"})


@hookimpl
def itf_init(ctx):
    ctx.scope("main").goal("itf.states.shell.open")
