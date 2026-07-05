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
"""Docker-specific behaviour (would not run on a mock/subprocess target)."""

from __future__ import annotations

from conftest import CONTAINER_EXTRA_MNT_PATH


def test_container_runs(shell):
    code, out = shell.execute("echo -n docker-specific")
    assert code == 0
    assert out == b"docker-specific"


def test_network_identity(network):
    assert network.ip().count(".") == 3
    assert network.gateway().count(".") == 3


def test_extra_mount_listed(shell):
    code, _ = shell.execute(f"ls -al {CONTAINER_EXTRA_MNT_PATH}")
    assert code == 0, "Extra volume not mounted!"


def test_extra_mount_content(shell):
    # This level's conftest.py lives in the mounted directory.
    code, out = shell.execute(f"cat {CONTAINER_EXTRA_MNT_PATH}/conftest.py")
    assert code == 0
    assert b"CONTAINER_EXTRA_MNT_PATH" in out
