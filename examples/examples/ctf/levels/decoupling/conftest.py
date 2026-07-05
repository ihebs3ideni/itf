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
"""Decoupling demo: target, capability, and scenario as THREE separate plugins.

    target_box.py       (Plugin A)  publishes ctf/target        -- the TARGET
    capability_shell.py (Plugin B)  publishes ctf/cap/exec       -- the CAPABILITY
    echo_scenario.py    (Plugin C)  publishes ctf/scenario/echo  -- the SCENARIO

Pretend each plugin ships from a DIFFERENT repository: the only import any of
them shares is core ``ctf``. None imports another's code -- they are linked
solely by contract *strings*.

This conftest plays the INTEGRATOR (the product repo): it composes the three
independent plugins by *name* and asks the DUT for capabilities by *contract
string*. It, too, never imports a plugin's internals -- registration is by
module name, resolution is by contract. The engine resolves
target -> exec -> echo purely from the ``@requires`` graph.
"""

from __future__ import annotations

import importlib

import pytest

pytest_plugins = ["ctf.pytest_plugin"]

# Three independent plugins, as if pip-installed from three separate repos. Order
# does not matter -- the @requires graph decides bring-up order, not this list.
_PLUGINS = ["target_box", "capability_shell", "echo_scenario"]


def pytest_configure(config):
    for name in _PLUGINS:
        module = importlib.import_module(name)
        if not config.pluginmanager.is_registered(module):
            config.pluginmanager.register(module, name)


@pytest.fixture
def shell(dut):
    """``ctf/cap/exec`` -- provided by Plugin B over Plugin A's target."""
    return dut.require("ctf/cap/exec")


@pytest.fixture
def echo(dut):
    """``ctf/scenario/echo`` -- provided by Plugin C over the exec capability."""
    return dut.require("ctf/scenario/echo")
