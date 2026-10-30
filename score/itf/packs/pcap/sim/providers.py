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
"""In-memory capture provider, for offline runs."""

from score.itf.core import provides

from .capture import CaptureConfig, SimCapture


@provides("itf.capabilities.observe.capture", name="sim.capture", config_schema=CaptureConfig)
def make_capture(config: dict) -> SimCapture:
    return SimCapture(config.get("interface", "eth0"))
