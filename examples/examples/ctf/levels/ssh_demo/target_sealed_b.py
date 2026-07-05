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
"""Sealed target B: an SSH endpoint with NO key link -- it just works.

The contrast with target A is a single line: this endpoint declares no token
requirement, so it resolves standalone and SSH is integrated without any key.
No token, no anonymous stand-in, no cross-plugin imports -- "don't declare the
requirement and it resolves without the dependency." The credential slot is
``None``, which the SSH plugin reads as anonymous.
"""

from __future__ import annotations

from ctf.contracts import provides

BOX = "ctf/target"
SSH_ENDPOINT = "ctf/net/ssh_endpoint"


@provides(BOX)
def sealed_box():
    """The sealed target -- present so the demo composes in LOOSE mode."""
    return "sealed-b"


@provides(SSH_ENDPOINT)
def open_endpoint():
    # No @requires: the endpoint is integrated with no key. Third slot is the
    # credential -> None means anonymous to the SSH plugin.
    return ("10.0.0.9", 22, None)


def pytest_ctf_setup(registry, config):
    registry.register(sealed_box)
    registry.register(open_endpoint)
