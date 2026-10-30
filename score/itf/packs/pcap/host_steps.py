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
"""Capture on an interface the host already has (a bench bridge): no platform prerequisite, so it
can record a target's whole boot. Same capture object as steps.py; load one of the two."""

from typing import Protocol

from score.itf.core import delivers


class Capture(Protocol):
    def start(self) -> None: ...
    def running(self) -> bool: ...


@delivers(
    "itf.states.capture.running",
    name="tcpdump.start_host_capture",
    uses={"capture": "itf.capabilities.observe.capture"},
)
def start_host_capture(capture: Capture) -> None:
    capture.start()


@start_host_capture.probe
def is_host_capture_running(capture: Capture) -> bool:
    return capture.running()
