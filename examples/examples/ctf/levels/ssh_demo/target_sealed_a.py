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
"""Sealed target A: an SSH endpoint whose access is *linked* to a deployed key.

This target imports nothing from other plugins -- it names every contract by its
string and defines its OWN endpoint provider. Two facts and one provider:

* ``ctf/sec/token_request = "token-42"`` -- a fact: which key this box needs.
* ``ctf/target``                          -- the sealed box itself (the anchor).
* ``ctf/net/ssh_endpoint``                -- the endpoint, declared with a
  ``@requires(ctf/sec/token)`` link. The endpoint is only *integrated* once the
  key is deployed, so the graph runs: deploy token-42 -> endpoint -> ssh -> run.

The SSH capability plugin never learns about tokens; it just requires an
endpoint. The credential rides through the endpoint value, so exec runs as the
deployed identity. The token/exec coupling lives here, expressed only by
contract strings.
"""

from __future__ import annotations

from ctf.contracts import provides, requires
from ctf.descriptor import Descriptor

BOX = "ctf/target"
SSH_ENDPOINT = "ctf/net/ssh_endpoint"
TOKEN = "ctf/sec/token"
TOKEN_REQUEST = "ctf/sec/token_request"


@provides(BOX)
def sealed_box():
    """The sealed target -- present so the demo composes in LOOSE mode."""
    return "sealed-a"


@provides(SSH_ENDPOINT)
@requires(TOKEN)
def authenticated_endpoint(credential):
    # Declaring the token requirement HERE is the link: the endpoint cannot be
    # integrated until the key is deployed. The credential travels with the
    # endpoint so the SSH plugin can connect as the deployed identity.
    return ("10.0.0.5", 22, credential)


def pytest_ctf_setup(registry, config):
    registry.add_descriptor(Descriptor(TOKEN_REQUEST, value="token-42"))
    registry.register(sealed_box)
    registry.register(authenticated_endpoint)
