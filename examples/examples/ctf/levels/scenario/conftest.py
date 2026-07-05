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
"""Scenario level: drive a *derived* scenario over any target.

The ``ctf/scenario/echo`` scenario is composed from ``ctf/cap/exec`` -- it is not
a target primitive. These tests depend only on the scenario contract; the active
``--ctf-target`` decides what shell backs it:

    pytest                          # default: mock (in-process, no deps)
    pytest --ctf-target=subprocess  # run on the host
    pytest --ctf-target=docker      # run in a container

A target that publishes no shell would leave the scenario unresolvable and its
tests would skip -- decided by the graph, not by hand-wired gating.
"""

from __future__ import annotations

import importlib

import pytest

from ctf import get_dut

from plugins.scenarios import echo as scenario_echo

pytest_plugins = ["ctf.pytest_plugin", "plugins.capability_gate"]

_TARGETS = {
    "mock": "plugins.targets.mock",
    "subprocess": "plugins.targets.subprocess",
    "docker": "plugins.targets.docker",
}

# The derived scenario, always registered. It requires ``ctf/cap/exec``; on a
# shell-less target it is unresolvable and its tests skip. Registered
# programmatically because the scenarios package imports eagerly, which would
# otherwise trip pytest's assertion-rewrite.
_ALWAYS = ["plugins.scenarios.echo"]


def pytest_addoption(parser):
    parser.addoption(
        "--ctf-target",
        action="store",
        default="mock",
        choices=sorted(_TARGETS),
        help="Which target backs the target-agnostic scenario tests.",
    )


def pytest_configure(config):
    name = config.getoption("--ctf-target")
    for module_name in [_TARGETS[name], *_ALWAYS]:
        module = importlib.import_module(module_name)
        if not config.pluginmanager.is_registered(module):
            config.pluginmanager.register(module, module_name)


@pytest.fixture
def echo(dut):
    """``ctf/scenario/echo`` -- derived; present only when the target has a shell."""
    if not dut.available(scenario_echo.CONTRACT):
        pytest.skip(
            f"composed target does not publish scenario {scenario_echo.CONTRACT!r}"
        )
    return dut.require(scenario_echo.CONTRACT)
