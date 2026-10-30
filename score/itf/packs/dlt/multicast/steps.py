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
from typing import Protocol

from score.itf.core import delivers


class Receiver(Protocol):
    def subscribe(self) -> None: ...
    def active(self) -> bool: ...


@delivers("itf.states.logs.active", name="dlt.join_multicast", uses={"logs": "itf.capabilities.observe.logs"})
def join_multicast(logs: Receiver) -> None:
    logs.subscribe()


@join_multicast.probe
def is_joined(logs: Receiver) -> bool:
    return logs.active()
