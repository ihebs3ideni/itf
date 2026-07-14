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

import pytest

from score.itf.core.ctf.contracts import provides
from score.itf.core.ctf.errors import DuplicateProviderError
from score.itf.core.ctf.registry import Registry
from score.itf.core.ctf.target import TARGET_ANCHOR
from score.itf.core import itf_plugin


def test_ctf_registry_rejects_duplicate_provider():
    registry = Registry()

    @provides("demo/cap/conflict")
    def provider_a():
        return "a"

    @provides("demo/cap/conflict")
    def provider_b():
        return "b"

    registry.register(provider_a)
    with pytest.raises(DuplicateProviderError):
        registry.register(provider_b)


def test_itf_plugin_registers_fallback_target_when_missing():
    registry = Registry()

    itf_plugin.pytest_itf_declare(registry, config=None)

    assert registry.has(TARGET_ANCHOR)
    # Fallback provider is a skip-producing function, not a target object.
    assert registry.provider(TARGET_ANCHOR).name == "_no_target"


def test_itf_plugin_does_not_override_existing_target_provider():
    registry = Registry()

    @provides(TARGET_ANCHOR)
    def concrete_target():
        return object()

    registry.register(concrete_target)
    itf_plugin.pytest_itf_declare(registry, config=None)

    assert registry.provider(TARGET_ANCHOR).name == "concrete_target"
