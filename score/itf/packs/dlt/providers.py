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
"""Entrypoint providers for DLT over a TCP stream."""

from collections.abc import Iterator
from score.itf.core import capability

from .stream import DltReceiver, EndpointLike, StreamConfig


@capability("observe.logs", label="stream")
def make_stream(endpoint: EndpointLike, config: StreamConfig) -> Iterator[DltReceiver]:
    stream = DltReceiver(
        endpoint,
        ecu_id=config.get("ecu_id", ""),
        buffer=config.get("buffer", 4096),
        connect_timeout=config.get("connect_timeout", 60.0),
    )
    yield stream
    stream.close()
