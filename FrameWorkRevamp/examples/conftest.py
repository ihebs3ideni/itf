"""Ecosystem activation + thin fixture adapters.

In a real deployment, each plugin below is a separately-installed package that
advertises itself via a ``pytest11`` entry point, so pytest discovers it with no
central list at all. Here, for an in-repo runnable demo, we activate the same
plugins explicitly.

The key point: this file only declares *which* plugins are present in the
environment. It does NOT wire them together -- the engine composes the DUT by
resolving contracts across whatever plugins happen to be active.
"""

from __future__ import annotations

import importlib

import pytest

# Independent plugins. Reordering this list does not change composition:
# the engine resolves by contract, not by registration order.
ECOSYSTEM_PLUGINS = [
    "examples.ecosystem.target_ecu",
    "examples.ecosystem.capability_doip",
    "examples.ecosystem.capability_uds",
    "examples.ecosystem.capability_ssh",
    "examples.ecosystem.lifecycle_artifacts",
]


def pytest_configure(config):
    for name in ECOSYSTEM_PLUGINS:
        module = importlib.import_module(name)
        if not config.pluginmanager.is_registered(module):
            config.pluginmanager.register(module, name)


# --- thin fixture adapters (could themselves live in an adapter plugin) ---
@pytest.fixture
def uds(dut):
    return dut.require("uds/client")


@pytest.fixture
def ssh(dut):
    return dut.require("ssh/client")
