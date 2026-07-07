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
"""Tests that generate artifacts for the compression lifecycle plugin."""

from __future__ import annotations


def test_exec_generates_a_report(shell):
    code, out = shell.execute("echo -n artifact-one")
    assert code == 0
    assert out == b"artifact-one"


def test_second_report(shell):
    code, out = shell.execute("echo -n artifact-two")
    assert code == 0
    assert out == b"artifact-two"


def test_collect_hook_has_data(ctf_kernel):
    names = ctf_kernel.artifacts.names()
    assert any(name.startswith("test-report:") for name in names)
