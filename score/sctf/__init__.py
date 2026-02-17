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
"""SCTF — Software Component Test Framework.

Provides a Docker-based execution environment for running compiled binaries
inside OCI containers as part of Bazel test targets.

Public API::

    from score.sctf.environment import Environment, ProcessHandle, DockerEnvironment
    from score.sctf.exception import SctfRuntimeError
"""

from score.sctf.environment import Environment, ProcessHandle, DockerEnvironment
from score.sctf.exception import SctfRuntimeError
