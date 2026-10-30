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
from dataclasses import dataclass, field

from score.itf.core import hookimpl, provides

CONFIG = {"host": "localhost", "token": "private-value"}
EXTRA_CONFIG = None
CONSTRUCTED = []


@dataclass(frozen=True)
class ClientConfig:
    host: str
    port: int = 8000
    token: str | None = field(default=None, metadata={"sensitive": True})


@provides("widget.client", name="fixture.client", config_schema=ClientConfig)
def client(config):
    CONSTRUCTED.append(config)
    return object()


@hookimpl
def itf_setup(ctx):
    ctx.scope("main").add("client", "widget.client", using="fixture.client", config=CONFIG)
    if EXTRA_CONFIG is not None:
        ctx.scope("other").add("client", "widget.client", using="fixture.client", config=EXTRA_CONFIG)
