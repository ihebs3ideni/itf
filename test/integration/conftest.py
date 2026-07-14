# *******************************************************************************
# Copyright (c) 2025-2026 Contributors to the Eclipse Foundation
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
"""Integration test conftest — loads ITF plugin and target/capability plugins.

The target plugin is selected by the --docker-image or --qemu-config options.
Capability plugins (ping, ssh) are always loaded; they auto-skip if their
required contracts aren't available.

This conftest demonstrates how a product conftest composes the DUT:
1. Load the ITF plugin (core lifecycle)
2. Load target plugin(s) (Docker, QEMU, mock — only one active per run)
3. Load capability plugins (ping, ssh — auto-skip if deps missing)
4. Load generic fixtures (exec_interface, etc.)
5. Optionally customize via pytest_itf_declare (e.g. extra volumes)
"""

import os

import pytest
from score.itf.core.ctf.contracts import provides, requires

# ITF core (provides dut fixture + phased lifecycle)
pytest_plugins = [
    "score.itf.core.itf_plugin",
    # Target plugins (only one active per run based on CLI options)
    "score.itf.plugins.targets.docker.plugin",
    # Capability plugins (shared, auto-skip if deps missing)
    "score.itf.plugins.capabilities.ping.plugin",
    # Generic fixtures (exec_interface, file_transfer_interface, restart_interface)
    "score.itf.plugins.targets.fixtures",
    # Utility plugins (observability)
    "score.itf.plugins.utility.dashboard.plugin",
    "score.itf.plugins.utility.logger.plugin",
    # Domain plugins (persistence)
    "score.itf.plugins.domain.sqlite_logger.plugin",
]


# ---------------------------------------------------------------------------
# Product-level DUT customization: add extra volume mount for tests
# ---------------------------------------------------------------------------
CONTAINER_EXTRA_MNT_PATH = "/extra/mount/directory"
CONTROL_ANCHOR = "ctf/target/control"


@provides(CONTROL_ANCHOR)
@requires("itf/cap/exec")
def control_anchor(exec_capability):
    """Anchor-level control requirement for suites that need command execution."""
    return exec_capability


@pytest.hookimpl(trylast=True)
def pytest_itf_declare(registry, config):
    """Customize Docker config: mount the test directory into the container."""
    from score.itf.plugins.targets.docker.plugin import DOCKER_CONFIG_CONTRACT

    existing = registry.descriptor(DOCKER_CONFIG_CONTRACT)
    if existing is not None:
        existing.value["volumes"] = {
            os.path.dirname(os.path.abspath(__file__)): {
                "bind": CONTAINER_EXTRA_MNT_PATH,
                "mode": "rw",
            }
        }
    registry.register(control_anchor)


@pytest.fixture()
def fixture42():
    yield 42
