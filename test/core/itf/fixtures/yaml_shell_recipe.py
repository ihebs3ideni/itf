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
from score.itf.core import hookimpl, load_init, load_setup
import os

pytest_plugins = ["fake_shell.plugin"]

DEFAULT_CONFIG = """
setup:
  nodes:
    - {name: world, using: fake_shell.world}
    - {name: shell, contract: itf.capabilities.exec.shell, using: fake_shell.session, bind: {world: world}}
init:
  goals: [itf.states.shell.open, itf.states.image.present]
"""


def _config() -> str:
    # The same `load_setup`/`load_init` entry point serves a CLI flag (handed off through this env
    # var by the pytest adapter), an env var set directly, or this recipe's own default — whichever
    # is present, it is still just a string reaching the same translator (D-31).
    return os.environ.get("ITF_CONFIG") or DEFAULT_CONFIG


@hookimpl
def itf_setup(ctx):
    load_setup(ctx, _config())


@hookimpl
def itf_init(ctx):
    load_init(ctx, _config())
