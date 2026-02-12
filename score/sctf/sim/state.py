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
from enum import Enum

# pylint: disable=invalid-name


# TODO: >2< State enum classes is about 1 too many!
class State:
    """Represents the enum values used for application state reporting"""

    Running = 0
    Terminating = 1


class ApplicationState(Enum):
    """Represents the enum values used for application state reporting"""

    Running = 0
    Terminating = 1
