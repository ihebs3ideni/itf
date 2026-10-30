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
"""An offline two-device bench built only from sim variants: what the real packs' recipes look like,
with nothing to start, connect to or capture."""

from score.itf.core import hookimpl

pytest_plugins = [
    "score.itf.packs.docker.sim.plugin",
    "score.itf.packs.ssh.sim.plugin",
    "score.itf.packs.dlt.sim.plugin",
    "score.itf.packs.pcap.sim.plugin",
    "score.itf.packs.net.plugin",
]


@hookimpl
def itf_setup(ctx):
    ctx.add("capture", "itf.capabilities.observe.capture", using="sim.capture")
    for name in ("gw", "adas"):
        device = ctx.scope(name)
        device.add("platform", "itf.capabilities.platform.instance", using="sim.platform", config={"name": name})
        device.add("command", "itf.capabilities.exec.command", using="sim.exec")
        device.add(
            "endpoint",
            "itf.capabilities.descriptor.endpoint",
            using="static.endpoint",
            config={"host": "127.0.0.1", "port": 22},
        )
        device.add(
            "creds", "itf.capabilities.descriptor.credentials", using="password.credentials", config={"user": "root"}
        )
        device.add("shell", "itf.capabilities.exec.shell", using="sim.shell")
        device.alias("capture", ".capture")
    ctx.scope("gw").add("logs", "itf.capabilities.observe.logs", using="sim.logs")


@hookimpl
def itf_init(ctx):
    ctx.goal("itf.states.capture.running")
    ctx.scope("gw").goal("itf.states.shell.open", "itf.states.logs.active")
    ctx.scope("adas").goal("itf.states.shell.open")
