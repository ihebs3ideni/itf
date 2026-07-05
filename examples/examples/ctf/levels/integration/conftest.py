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
"""Integration level: verify CTF composes and drives *any* target correctly.

These tests are target-agnostic -- they depend only on ``ctf/cap/*`` contracts.
Which target backs them is chosen at runtime with ``--ctf-target``:

    pytest                          # default: mock (in-process, no deps)
    pytest --ctf-target=subprocess  # run on the host
    pytest --ctf-target=docker      # run in a container

The same tests pass on every target; a capability a target does not publish
(e.g. ``ctf/cap/network`` on mock/subprocess) makes the requiring test skip.
"""

from __future__ import annotations

import importlib

pytest_plugins = ["ctf.pytest_plugin", "plugins.capability_gate"]

_TARGETS = {
    "mock": "plugins.targets.mock",
    "subprocess": "plugins.targets.subprocess",
    "docker": "plugins.targets.docker",
}

# Infrastructure + derived capabilities, always registered. The derived ping
# capability is declared unconditionally: on a target that publishes no network
# identity it is simply unresolvable, so the engine records it unavailable (loose
# mode) and its tests skip -- no self-gating. Registered programmatically (not via
# pytest_plugins) because the capabilities package imports them eagerly, which
# would otherwise trip pytest's assertion-rewrite.
_ALWAYS = ["plugins.host", "plugins.capabilities.ping"]


def pytest_addoption(parser):
    parser.addoption(
        "--ctf-target",
        action="store",
        default="mock",
        choices=sorted(_TARGETS),
        help="Which target backs the target-agnostic integration tests.",
    )


def pytest_configure(config):
    name = config.getoption("--ctf-target")
    for module_name in [_TARGETS[name], *_ALWAYS]:
        module = importlib.import_module(module_name)
        if not config.pluginmanager.is_registered(module):
            config.pluginmanager.register(module, module_name)
