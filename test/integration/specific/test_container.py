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
"""Containers only: selected wherever the platform offers a `container` (the docker pack)."""

import score.itf as itf


@itf.requires("platform", shape=["container"])
@itf.requires("command")
def test_the_composition_volume_is_mounted(target):
    assert target.command.exec("ls /extra/mount")[0] == 0


@itf.requires("platform", shape=["container"])
@itf.requires("command")
def test_renew_starts_from_a_clean_container(target):
    target.command.exec("touch /tmp/marker")
    old_id = target.platform.container.id
    target.renew("platform")
    assert target.platform.container.id != old_id
    assert target.command.exec("test -f /tmp/marker")[0] != 0
