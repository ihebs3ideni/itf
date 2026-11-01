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
"""Providers for DLT over UDP multicast."""

from collections.abc import Iterator
from score.itf.core import capability

from .receiver import MulticastConfig, MulticastDltReceiver


@capability("observe.logs", label="multicast")
def make_multicast(config: MulticastConfig) -> Iterator[MulticastDltReceiver]:
    receiver = MulticastDltReceiver(
        config["sources"],
        port=config.get("port", 3490),
        dlt_file=config.get("dlt_file"),
        buffer=config.get("buffer", 100000),
        stop_timeout=config.get("stop_timeout", 2.0),
    )
    try:
        yield receiver
    finally:
        receiver.close()
