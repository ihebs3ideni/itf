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
"""The test uses the top of a three-plugin chain, oblivious to the target.

Plugin A makes the target, Plugin B implements the exec capability over it,
Plugin C derives echo from exec -- and the test only ever names contracts.
"""

from __future__ import annotations


def test_capability_runs_on_the_decoupled_target(shell):
    # Plugin B's exec capability, backed by Plugin A's target. The test never
    # mentions Box, target_box, or capability_shell.
    code, out = shell.execute("echo -n hello from a separate capability plugin")
    assert code == 0
    assert out == b"hello from a separate capability plugin"


def test_scenario_derives_from_the_capability(echo):
    # Plugin C's scenario, over Plugin B's capability, over Plugin A's target.
    assert echo.send(b"three plugins, one contract chain") == (
        b"three plugins, one contract chain"
    )
