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
"""dlt-receive providers. Constructing one starts nothing: `dlt.start_receive` (steps.py) does."""

from collections.abc import Iterator
from score.itf.core import provides

from .tool import DltReceive, Endpoint, ReceiveConfig


@provides("itf.capabilities.observe.logs", name="dlt.receive", config_schema=ReceiveConfig)
def make_receive(config: dict) -> Iterator[DltReceive]:
    receive = DltReceive(config)
    yield receive
    receive.close()


@provides(
    "itf.capabilities.observe.logs",
    name="dlt.receive_tcp",
    config_schema=ReceiveConfig,
    gives=("subscribe", "close", "active", "path", "record", "lines", "filter", "window"),
    needs={"endpoint": "itf.capabilities.descriptor.endpoint"},
)
def make_receive_tcp(endpoint: Endpoint, config: dict) -> Iterator[DltReceive]:
    receive = DltReceive(config, endpoint)
    yield receive
    receive.close()
