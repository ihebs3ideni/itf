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
"""Capability gating: auto-skip tests whose DUT lacks required capabilities."""

from __future__ import annotations

import functools

import pytest


def requires_capabilities(*capabilities: str, device: str | None = None):
    """Decorator: skip the test if the DUT lacks any of the named capabilities.

    Accepts aliases (``"shell"``) or full contract strings (``"itf/cap/exec"``).
    Alias resolution happens via the DUT's alias table — no hardcoded map needed.

    Args:
        *capabilities: One or more capability names (aliases or contracts).
        device: Optional device scope. If set, checks availability on
            ``dut[device]`` instead of the root assembly::

                @requires_capabilities("ssh", device="safety")
                def test_safety_remote(dut):
                    ssh = dut["safety"]["ssh"]
                    ...
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            dut = kwargs.get("dut")
            if dut is None:
                for arg in args:
                    if hasattr(arg, "available") and hasattr(arg, "require"):
                        dut = arg
                        break

            # Resolve the target scope (root or device proxy)
            scope = dut
            if dut is not None and device is not None:
                if device not in dut.devices():
                    pytest.skip(f"DUT has no device '{device}'")
                scope = dut[device]

            missing = []
            for cap in capabilities:
                if scope is None or not scope.available(cap):
                    missing.append(cap)

            if missing:
                where = f" on device '{device}'" if device else ""
                pytest.skip(f"DUT missing capabilities{where}: {tuple(missing)}")

            return func(*args, **kwargs)

        return wrapper

    return decorator
