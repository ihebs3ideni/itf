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
"""The original QEMU target: the legacy API with SSH, SFTP and ping from the recipe's nodes."""

from .core import LegacyTarget

QEMU_CAPABILITIES = {"exec", "file_transfer", "restart", "ssh", "sftp"}


class QemuTarget(LegacyTarget):
    def __init__(self, view):
        super().__init__(view, QEMU_CAPABILITIES)
