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

from .logs import LogStream


@delivers(
    "itf.states.logs.active",
    name="sim.subscribe_logs",
    requires=("itf.states.platform.up",),
    uses={"logs": "itf.capabilities.observe.logs"},
)
def subscribe_logs(logs: LogStream) -> None:
    logs.subscribe()


@subscribe_logs.probe
def is_stream_active(logs: LogStream) -> bool:
    return logs._live()
