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
"""Conflict examples: what happens when plugins do not cooperate.

These tests intentionally create bad ecosystems and assert CTF's fail-fast
errors, so behavior stays explicit and deterministic.
"""

from __future__ import annotations

import pytest

from ctf.contracts import provides
from ctf.errors import DuplicateProviderError, StepCollisionError
from ctf.registry import Registry
from ctf.steps import Policy, StepRegistry


def test_duplicate_provider_contract_is_rejected():
    registry = Registry()

    @provides("demo/cap/conflict")
    def provider_a():
        return "a"

    @provides("demo/cap/conflict")
    def provider_b():
        return "b"

    registry.register(provider_a)
    with pytest.raises(DuplicateProviderError) as excinfo:
        registry.register(provider_b)

    message = str(excinfo.value)
    assert "demo/cap/conflict" in message
    assert "already provided" in message


def test_unique_step_point_collision_is_rejected():
    steps = StepRegistry()
    steps.declare("ctf_compress_artifacts", Policy.UNIQUE)

    def gzip_handler(ctx):
        return "gzip"

    def zstd_handler(ctx):
        return "zstd"

    steps.add("ctf_compress_artifacts", gzip_handler, name="gzip_handler")
    steps.add("ctf_compress_artifacts", zstd_handler, name="zstd_handler")

    with pytest.raises(StepCollisionError) as excinfo:
        steps.validate()

    message = str(excinfo.value)
    assert "ctf_compress_artifacts" in message
    assert "UNIQUE" in message
    assert "gzip_handler" in message
    assert "zstd_handler" in message


def test_fanout_point_allows_multiple_handlers():
    steps = StepRegistry()
    seen = []

    def gzip_handler(ctx):
        seen.append("gzip")

    def zstd_handler(ctx):
        seen.append("zstd")

    steps.add("ctf_collect", gzip_handler, name="gzip_handler")
    steps.add("ctf_collect", zstd_handler, name="zstd_handler")

    # Built-in ctf_collect is FANOUT, so no collision.
    steps.validate()
    assert seen == []
