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
"""D-28 violation hidden inside a hook body (A-3.9)."""

from score.itf.core import hookimpl


pytest_plugins = ["fake_kv.plugin"]


@hookimpl
def itf_setup(ctx):
    from fake_kv import providers  # illegal even though it only runs at setup time

    ctx.scope("main").add("store", using=providers.__name__)
