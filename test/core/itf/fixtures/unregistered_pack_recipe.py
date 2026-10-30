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
"""D-28 violation: calls a pack it never registered, bypassing the planner entirely (A-3.9)."""

from score.itf.core import hookimpl
from fake_kv_alt.providers import make_store  # illegal: fake_kv_alt is a contributor


pytest_plugins = ["fake_kv.plugin"]


@hookimpl
def itf_setup(ctx):
    ctx.scope("main").add("store", using="fake_kv.memory_store")


@hookimpl
def itf_verify(session):
    make_store({})
