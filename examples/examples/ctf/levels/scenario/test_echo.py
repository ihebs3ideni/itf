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
"""Target-agnostic scenario tests.

Nothing here mentions docker, mock or subprocess. Each test depends on the
``ctf/scenario/echo`` contract; the active ``--ctf-target`` decides what shell
backs the derived scenario.
"""

from __future__ import annotations


def test_echo_round_trip(echo):
    assert echo.send(b"hello scenario") == b"hello scenario"


def test_echo_empty_payload(echo):
    assert echo.send(b"") == b""


def test_echo_preserves_spaces(echo):
    payload = b"two  spaces and trailing "
    assert echo.send(payload) == payload
