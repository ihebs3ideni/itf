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

from .stream import DltReceiver


@delivers(
    "itf.states.logs.active",
    name="dlt.subscribe_stream",
    requires=("itf.states.platform.up",),
    uses={"logs": "itf.capabilities.observe.logs"},
)
def subscribe_stream(logs: DltReceiver) -> None:
    logs.subscribe()


@subscribe_stream.probe
def is_stream_active(logs: DltReceiver) -> bool:
    return logs._live()
