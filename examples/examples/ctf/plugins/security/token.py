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
"""Token-deployment plugin (mocked) -- a *lifecycle* dependency.

Unlike a plain value, a token must be **deployed** before it is usable and
**revoked** afterwards. This plugin is a generic credential provisioner: it
deploys the ONE specific token id it is asked for -- ``ctf/sec/token_request`` --
not "all tokens". The requested id is a descriptor published upstream (by the
target or the level), so the same plugin serves any target: hand it an id and it
deploys exactly that.

Deployment/revocation are observable via the module-level ``DEPLOYED`` ledger and
print statements, so the example can show the engine running deployment *before*
anything that requires the token, and revocation on teardown.
"""

from __future__ import annotations

from ctf.contracts import provides, requires

#: A deployed, valid credential.
CONTRACT = "ctf/sec/token"

#: Descriptor naming which token id to deploy (the parameter).
REQUEST = "ctf/sec/token_request"

#: Mock "vault": ids currently deployed. Lets tests/examples observe the effect.
DEPLOYED: list[str] = []


class DeployedToken:
    def __init__(self, token_id: str) -> None:
        self.token_id = token_id
        self.valid = True


@provides(CONTRACT)
@requires(REQUEST)
def deploy_token(token_id: str):
    print(f"[token] deploying token {token_id!r}")
    DEPLOYED.append(token_id)
    credential = DeployedToken(token_id)
    try:
        yield credential  # token is live for everything that requires it
    finally:
        credential.valid = False
        DEPLOYED.remove(token_id)
        print(f"[token] revoked token {token_id!r}")


def pytest_ctf_setup(registry, config):
    # Reusable and target-independent: registered unconditionally. It resolves
    # only for a target that published a ``ctf/sec/token_request`` fact; on a
    # target that asks for no key, ``ctf/sec/token`` is simply unavailable (loose
    # mode) and nothing requires it.
    registry.register(deploy_token)
