# *******************************************************************************
# Copyright (c) 2025 Contributors to the Eclipse Foundation
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
def test_local_fixture_has_correct_value(fixture42):
    assert 42 == fixture42


def test_dut_is_available(dut):
    assert dut is not None


def test_dut_exposes_target_anchor_by_default(dut):
    assert "ctf/target" in dut.provides()
