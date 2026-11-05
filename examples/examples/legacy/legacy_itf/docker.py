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
"""The original Docker target: the legacy API plus `get_ip`, `get_gateway` and the container."""

from .core import LegacyTarget

DOCKER_CAPABILITIES = {"exec", "file_transfer", "restart"}


class DockerTarget(LegacyTarget):
    def __init__(self, view):
        super().__init__(view, DOCKER_CAPABILITIES)
        self.platform = view.platform

    @property
    def container(self):
        return self.platform.container

    def __getattr__(self, name):
        if name in ("platform", "view") or name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.platform.container, name)

    def get_ip(self, network=None):
        return self.platform.ip(network)

    def get_gateway(self, network=None):
        return self.platform.gateway(network)
