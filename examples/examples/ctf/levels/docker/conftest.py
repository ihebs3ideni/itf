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
"""Docker-specific level: the docker target is fixed and always present.

Unlike the integration level, this level pins the docker target statically (so
its CLI options are registered) and tests behaviour that is meaningful only for
docker -- the bind mount and the container's network identity.
"""

from __future__ import annotations

import os

pytest_plugins = [
    "ctf.pytest_plugin",
    "plugins.capability_gate",
    "plugins.targets.docker",
]

#: Where this level directory is bind-mounted inside the container.
CONTAINER_EXTRA_MNT_PATH = "/extra/mount/directory"


def pytest_configure(config):
    # Bind-mount this directory into the container so the extra-mount test can
    # see its own files, unless the user overrode the mount on the CLI.
    if not config.getoption("--ctf-docker-mount"):
        this_dir = os.path.dirname(os.path.abspath(__file__))
        config.option.ctf_docker_mount = [f"{this_dir}:{CONTAINER_EXTRA_MNT_PATH}"]
