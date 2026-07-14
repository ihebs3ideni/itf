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
"""Project-level conftest: register DUT aliases for test readability.

Tests in this directory use short, domain-level names (``dut["shell"]``)
instead of raw contract strings (``dut.require("itf/cap/exec")``).

The alias hook runs after DECLARE (graph is resolved) but before INIT,
so all contracts are known and aliases are ready before any test code runs.
"""

import pytest

# Ensure ITF lifecycle hooks are registered (provides hookspecs + dut fixture).
# In a Bazel py_itf_test this is handled by the rule; for standalone pytest
# invocations, explicit registration is needed.
pytest_plugins = [
    "score.itf.core.itf_plugin",
    "score.itf.plugins.targets.fixtures",
]


@pytest.hookimpl
def pytest_itf_aliases(dut, config):
    """Map project-level vocabulary to ITF contract strings."""
    dut.alias("shell", "itf/cap/exec")
    dut.alias("file_transfer", "itf/cap/file_transfer")
    dut.alias("restart", "itf/cap/restart")
    dut.alias("ssh", "itf/cap/ssh")
    dut.alias("sftp", "itf/cap/sftp")
    dut.alias("ping", "itf/cap/ping")
    dut.alias("ip", "itf/net/ip_address")
    dut.alias("target", "ctf/target")
