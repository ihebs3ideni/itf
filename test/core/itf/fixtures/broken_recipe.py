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
from score.itf.core import hookimpl


pytest_plugins = ["fake_kv.plugin"]


@hookimpl
def itf_setup(ctx):
    ctx.scope("main").add("store", using="no.such.provider")


@hookimpl
def itf_init(ctx):
    ctx.scope("main").goal("kv_seeded")
