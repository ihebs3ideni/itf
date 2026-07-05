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
"""SSH-over-key demo (fully mocked, LOOSE mode via a target anchor).

One reusable SSH plugin serves both sealed targets. The difference is declared
by the *targets themselves*, in contract strings only -- no target imports
another plugin, and no target picks a credential provider:

    pytest                       # sealed_a: its endpoint @requires ctf/sec/token
                                 #           -> deploy token-42 -> integrate ssh
    pytest --ssh-target=sealed_b # sealed_b: its endpoint has no key link
                                 #           -> ssh integrates with no token

The token plugin is reusable and keyed on a ``ctf/sec/token_request`` fact: it
resolves only when a target published that fact. On the keyless target it is
simply unavailable (loose mode) and nothing requires it. There is no anonymous
provider -- a keyless endpoint just carries a ``None`` credential.
"""

from __future__ import annotations

import importlib

pytest_plugins = ["ctf.pytest_plugin", "plugins.capability_gate"]

# Reusable, target-independent plugins (registered programmatically to avoid
# pytest's assertion-rewrite warning on already-imported modules). Neither the
# SSH capability nor the token deployer is tied to a specific target.
_REUSABLE = [
    "plugins.capabilities.ssh",
    "plugins.security.token",
]

_TARGETS = {
    "sealed_a": "target_sealed_a",
    "sealed_b": "target_sealed_b",
}


def pytest_addoption(parser):
    parser.addoption(
        "--ssh-target",
        action="store",
        default="sealed_a",
        choices=sorted(_TARGETS),
        help="Which sealed target to compose (sealed_a needs a token, sealed_b does not).",
    )


def pytest_configure(config):
    name = config.getoption("--ssh-target")
    for module_name in [*_REUSABLE, _TARGETS[name]]:
        module = importlib.import_module(module_name)
        if not config.pluginmanager.is_registered(module):
            config.pluginmanager.register(module, module_name)
